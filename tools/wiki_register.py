"""
wiki_register — register a new wiki at runtime without editing registry.yaml by hand.

Validates the path, creates the standard wiki_raw/ + wiki/ skeleton if missing,
appends the entry to registry.yaml, and reloads the in-memory registry. Requires
the user to ALREADY have a write grant to modify the registry — otherwise the
tool refuses and tells the user to edit registry.yaml manually.

The new wiki's access grants are NOT auto-added to `grants:`. The tool prints
the exact YAML snippet to paste into registry.yaml so the user stays in control.
"""

import os

try:
    from ._base import WikiToolBase, WikiRegistry, Response
except ImportError:
    # Agent Zero v1.10+ loads tool files via importlib.spec_from_file_location
    # without a package context, breaking relative imports. Fall back to absolute.
    import os as _os, sys as _sys
    _here = _os.path.dirname(_os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)
    from _base import WikiToolBase, WikiRegistry, Response  # type: ignore


VALID_SCOPES = {"shared", "self", "personal", "project", "reference", "external"}
VALID_SENSITIVITIES = {"public", "internal", "private", "secret"}


class WikiRegister(WikiToolBase):
    """Register a new wiki in the SharedBrain registry."""

    async def execute(self, **kwargs):
        name = (self.args.get("name") or "").strip()
        path = (self.args.get("path") or "").strip()
        scope = (self.args.get("scope") or "").strip()
        title = (self.args.get("title") or "").strip()
        description = (self.args.get("description") or "").strip()
        sensitivity = (self.args.get("sensitivity") or "internal").strip()
        tags_arg = self.args.get("tags", [])
        default_for_ingest = bool(self.args.get("default_for_ingest", False))
        create_skeleton = bool(self.args.get("create_skeleton", True))

        # Normalize tags
        if isinstance(tags_arg, str):
            tags = [t.strip() for t in tags_arg.split(",") if t.strip()]
        elif isinstance(tags_arg, list):
            tags = [str(t).strip() for t in tags_arg if str(t).strip()]
        else:
            tags = []

        # ---------- validation ----------
        errors = []
        if not name:
            errors.append("`name` is required (snake_case identifier)")
        elif not name.replace("_", "").isalnum():
            errors.append("`name` must be snake_case (letters, digits, underscores only)")
        if not path:
            errors.append("`path` is required (absolute or vault-relative)")
        if scope and scope not in VALID_SCOPES:
            errors.append(f"`scope` must be one of {sorted(VALID_SCOPES)}")
        if sensitivity not in VALID_SENSITIVITIES:
            errors.append(f"`sensitivity` must be one of {sorted(VALID_SENSITIVITIES)}")
        if errors:
            return Response(message="Validation errors:\n- " + "\n- ".join(errors),
                            break_loop=False)

        if not scope:
            scope = "project"

        config = self._get_config()
        agent_id = self._get_agent_id()
        project_dir = self._get_project_dir()

        registry = WikiRegistry.from_config(
            plugin_config=config,
            agent_id=agent_id,
            fallback_project_dir=project_dir,
        )
        if registry is None:
            return Response(
                message=(
                    "No SharedBrain vault configured. Set shared_vault.enabled=true and "
                    "shared_vault.path=<abs path> in the plugin config first."
                ),
                break_loop=False,
            )

        # Resolve path: absolute stays absolute; relative is rooted at vault
        abs_path = path if os.path.isabs(path) else os.path.join(registry.vault_root, path)
        abs_path = os.path.normpath(abs_path)

        # ---------- create skeleton ----------
        if create_skeleton:
            try:
                os.makedirs(os.path.join(abs_path, "wiki_raw"), exist_ok=True)
                os.makedirs(os.path.join(abs_path, "wiki", "concepts"), exist_ok=True)
                os.makedirs(os.path.join(abs_path, "wiki", "entities"), exist_ok=True)
                os.makedirs(os.path.join(abs_path, "wiki", "sources"), exist_ok=True)
                os.makedirs(os.path.join(abs_path, "wiki", "queries"), exist_ok=True)
                index_path = os.path.join(abs_path, "wiki", "index.md")
                log_path = os.path.join(abs_path, "wiki", "log.md")
                if not os.path.isfile(index_path):
                    with open(index_path, "w", encoding="utf-8") as f:
                        f.write(f"# {title or name} — Index\n\n_No pages yet._\n")
                if not os.path.isfile(log_path):
                    with open(log_path, "w", encoding="utf-8") as f:
                        f.write(f"# {title or name} — Log\n\n")
            except Exception as e:
                return Response(
                    message=f"Failed to create skeleton at {abs_path}: {e}",
                    break_loop=False,
                )

        # ---------- append to registry.yaml ----------
        entry = {
            "name": name,
            "title": title or name.replace("_", " ").title(),
            "path": path,  # write path as user supplied (preserves relative form)
            "scope": scope,
            "description": description,
            "tags": tags,
            "sensitivity": sensitivity,
            "default_for_ingest": default_for_ingest,
        }
        result = registry.append_wiki_entry(entry)
        if not result["ok"]:
            return Response(
                message=f"Could not update registry.yaml: {result['reason']} (path: {result['path']})",
                break_loop=False,
            )

        # ---------- suggest grants snippet ----------
        grants_snippet = (
            f"grants:\n"
            f"  {agent_id}:\n"
            f"    read:  [..., {name}]\n"
            f"    write: [..., {name}]\n"
        )

        # ---------- auto-commit ----------
        git_note = ""
        commit = registry.git_commit_after(
            op="REGISTER",
            wiki_name=name,
            message=f"register new wiki at {abs_path}",
            paths=None,
        )
        if commit["committed"]:
            git_note = f"\n**Committed:** {commit['sha']}"
        elif not commit["ok"]:
            git_note = f"\n**Git commit failed:** {commit['reason']}"

        msg = (
            f"## Registered wiki `{name}`\n"
            f"- **path:** `{abs_path}`\n"
            f"- **scope:** {scope}  **sensitivity:** {sensitivity}\n"
            f"- **skeleton created:** {create_skeleton}\n"
            f"- **registry updated:** {result['path']}"
            f"{git_note}\n\n"
            "### Next step — grant yourself access\n"
            "The tool did NOT auto-modify `grants:` (access control stays in human "
            "hands). Edit `registry.yaml` and add `{name}` to the appropriate agent's "
            "read/write lists, for example:\n\n"
            f"```yaml\n{grants_snippet}```\n"
            "Then run `wiki_list` to confirm."
        ).replace("{name}", name)

        return Response(message=msg, break_loop=False)



# A0 v1.10 module loader picks the last alphabetically-ordered class that subclasses Tool;
# remove the imported base from the module namespace so it picks the concrete tool defined here.
del WikiToolBase
