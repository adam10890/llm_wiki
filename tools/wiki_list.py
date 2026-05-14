"""
wiki_list — list every wiki visible to the current agent.

Shows each wiki's name, scope, sensitivity, absolute path, access grants,
and a few stats (page count, last log entry, existence of graphify output).
Used by agents to orient themselves at the start of any wiki-related task.
"""

import os
from datetime import datetime

try:
    from ._base import WikiToolBase, WikiRegistry, Response, files
except ImportError:
    # Agent Zero v1.10+ loads tool files via importlib.spec_from_file_location
    # without a package context, breaking relative imports. Fall back to absolute.
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    from _base import WikiToolBase, WikiRegistry, Response, files  # type: ignore


class WikiList(WikiToolBase):
    """List all wikis registered in the SharedBrain vault."""

    async def execute(self, **kwargs):
        verbose = bool(self.args.get("verbose", False))

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
                    "No SharedBrain vault configured.\n"
                    "Either:\n"
                    "  1. Set `shared_vault.enabled: true` and `shared_vault.path: <abs path>` "
                    "in the llm_wiki plugin config, or\n"
                    "  2. Open a project that has a registry.yaml at its root.\n"
                    "\n"
                    "Legacy single-wiki mode is still available — just call wiki_ingest / wiki_query / wiki_lint "
                    "in a project with a wiki_raw/ and wiki/ directory."
                ),
                break_loop=False,
            )

        wikis = registry.list_wikis()
        if not wikis:
            return Response(
                message=(
                    f"Vault root: {registry.vault_root}\n"
                    "registry.yaml found but contains no `wikis:` entries. Add some."
                ),
                break_loop=False,
            )

        parts = [
            f"## SharedBrain — Wikis",
            f"**Vault root:** `{registry.vault_root}`",
            f"**Your agent id:** `{registry.agent_id}`",
            f"**Your grants:** read={registry._grants().get('read', [])}  write={registry._grants().get('write', [])}",
            "",
            f"| Name | Scope | Sensitivity | R/W | Default? | Pages | Path |",
            f"|---|---|---|---|---|---|---|",
        ]

        for w in wikis:
            r = "R" if registry.can_read(w["name"]) else "-"
            wr = "W" if registry.can_write(w["name"]) else "-"
            ok = "✓" if w["exists"] else "✗ missing"
            default = "★" if w["default_for_ingest"] else ""
            page_count = self._count_pages(registry, w) if w["exists"] else 0
            parts.append(
                f"| `{w['name']}` | {w['scope']} | {w['sensitivity']} | {r}{wr} | {default} | {page_count} {ok} | `{w['path']}` |"
            )

        parts.append("")
        parts.append(f"**Total wikis:** {len(wikis)}")
        parts.append(f"**Readable by you:** {len(registry.readable_wikis())}")
        parts.append(f"**Writable by you:** {len(registry.writable_wikis())}")

        if verbose:
            parts.append("")
            parts.append("### Descriptions")
            for w in wikis:
                parts.append(f"- **{w['name']}** ({w['scope']}) — {w['description']}")
                if w["tags"]:
                    parts.append(f"  tags: {', '.join(w['tags'])}")

            # Also show recent log entries from the default wiki
            default = registry.default_ingest_wiki()
            if default and default["exists"]:
                paths = registry.wiki_paths(default)
                if os.path.isfile(paths["log"]):
                    try:
                        log_content = files.read_file(paths["log"])
                        tail = "\n".join(log_content.splitlines()[-20:])
                        parts.append("")
                        parts.append(f"### Recent log entries in `{default['name']}`")
                        parts.append("```")
                        parts.append(tail)
                        parts.append("```")
                    except Exception:
                        pass

        return Response(message="\n".join(parts), break_loop=False)

    def _count_pages(self, registry: WikiRegistry, wiki: dict) -> int:
        paths = registry.wiki_paths(wiki)
        wiki_dir = paths["wiki_dir"]
        if not os.path.isdir(wiki_dir):
            return 0
        count = 0
        exclude = {"index.md", "log.md"}
        for root, _, fnames in os.walk(wiki_dir):
            for f in fnames:
                if f.endswith(".md") and f not in exclude:
                    count += 1
        return count



# A0 v1.10 module loader picks the last alphabetically-ordered class that subclasses Tool;
# remove the imported base from the module namespace so it picks the concrete tool defined here.
del WikiToolBase
