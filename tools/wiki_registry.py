"""
wiki_registry — central resolver for the multi-wiki SharedBrain layout.

A single vault can host multiple independent Karpathy-style wikis, each with
its own wiki_raw/ + wiki/ structure. This module:

  1. Locates the vault root (from plugin config or project_dir).
  2. Parses the registry (registry.yaml at the vault root) that lists every
     named wiki, its absolute path, scope, sensitivity, and access grants.
  3. Resolves a wiki name to an absolute path.
  4. Enforces per-agent read/write access control.
  5. Provides iteration over readable/writable wikis for fan-out queries.

Zero external dependencies — uses a tiny stdlib YAML subset parser so the
plugin keeps its "no pip install needed" promise. If a real yaml library is
available it's used transparently.

The registry file format is documented in SharedBrain/registry.yaml.
"""

import os
import json
import subprocess
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# YAML emit helpers
# ---------------------------------------------------------------------------

def _yaml_quote(s: str) -> str:
    """Quote a scalar for YAML output. Uses double quotes, escapes embedded
    quotes and backslashes. Leaves simple bareword scalars unquoted only when
    they're clearly safe — for paths and descriptions we always quote."""
    if s is None:
        return '""'
    s = str(s)
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# Minimal YAML loader (falls back to real pyyaml if available)
# ---------------------------------------------------------------------------

def _load_yaml(text: str) -> Dict[str, Any]:
    """Load YAML. Prefer pyyaml if installed; otherwise use a tiny parser
    that handles the subset we need (mappings, sequences, scalars, comments,
    quoted strings). Not a full YAML implementation — registry.yaml only
    uses the subset this handles."""
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except Exception:
        pass
    return _tiny_yaml_parse(text)


def _tiny_yaml_parse(text: str) -> Dict[str, Any]:
    """Tiny YAML subset parser: mappings, lists, scalars, block style only.
    Indentation-sensitive. Handles # comments and basic quoted scalars."""
    lines = []
    for raw in text.splitlines():
        # Strip comments (but not inside quoted strings — naive handling)
        in_str = False
        quote = ""
        cleaned_chars = []
        for ch in raw:
            if not in_str and ch == "#":
                break
            if ch in ('"', "'"):
                if not in_str:
                    in_str = True
                    quote = ch
                elif quote == ch:
                    in_str = False
                    quote = ""
            cleaned_chars.append(ch)
        cleaned = "".join(cleaned_chars).rstrip()
        if cleaned.strip() == "":
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        lines.append((indent, cleaned.lstrip(" ")))

    def parse_scalar(s: str) -> Any:
        s = s.strip()
        if s == "":
            return ""
        if s == "true":
            return True
        if s == "false":
            return False
        if s == "null" or s == "~":
            return None
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1]
        # Try int/float
        try:
            if "." not in s:
                return int(s)
            return float(s)
        except ValueError:
            pass
        # Flow list [a, b, c]
        if s.startswith("[") and s.endswith("]"):
            inner = s[1:-1].strip()
            if not inner:
                return []
            return [parse_scalar(x) for x in _split_flow(inner)]
        return s

    def _split_flow(s: str) -> List[str]:
        out = []
        depth = 0
        buf = ""
        in_q = False
        q = ""
        for ch in s:
            if not in_q and ch in ('"', "'"):
                in_q = True
                q = ch
                buf += ch
            elif in_q and ch == q:
                in_q = False
                buf += ch
            elif not in_q and ch == "[":
                depth += 1
                buf += ch
            elif not in_q and ch == "]":
                depth -= 1
                buf += ch
            elif not in_q and depth == 0 and ch == ",":
                out.append(buf.strip())
                buf = ""
            else:
                buf += ch
        if buf.strip():
            out.append(buf.strip())
        return out

    def parse_block(i: int, base_indent: int) -> Tuple[Any, int]:
        # Return (value, next_line_index)
        if i >= len(lines):
            return None, i
        indent, content = lines[i]
        if indent < base_indent:
            return None, i

        # List block
        if content.startswith("- "):
            items = []
            while i < len(lines):
                indent, content = lines[i]
                if indent < base_indent:
                    break
                if indent != base_indent or not content.startswith("- "):
                    break
                item_content = content[2:]
                # Item may be a scalar or the first key of an inline mapping
                if ":" in item_content and not item_content.startswith('"'):
                    # Mapping item: e.g. "- name: foo"
                    key, _, val = item_content.partition(":")
                    key = key.strip()
                    val_stripped = val.strip()
                    item_map: Dict[str, Any] = {}
                    if val_stripped == "":
                        # Nested block follows
                        sub, i_next = parse_block(i + 1, base_indent + 2)
                        if isinstance(sub, dict):
                            item_map[key] = None  # placeholder, overwritten below
                            # But actually sub holds *all* keys at that indent,
                            # including key itself if we're wrong. Re-parse properly:
                            item_map = sub
                        else:
                            item_map[key] = sub
                        i = i_next
                    else:
                        item_map[key] = parse_scalar(val_stripped)
                        i += 1
                        # Continue reading additional keys at base_indent + 2
                        while i < len(lines):
                            indent2, content2 = lines[i]
                            if indent2 <= base_indent:
                                break
                            if content2.startswith("- "):
                                break
                            k2, _, v2 = content2.partition(":")
                            k2 = k2.strip()
                            v2s = v2.strip()
                            if v2s == "":
                                sub, i_next = parse_block(i + 1, indent2 + 2)
                                item_map[k2] = sub
                                i = i_next
                            else:
                                item_map[k2] = parse_scalar(v2s)
                                i += 1
                    items.append(item_map)
                else:
                    items.append(parse_scalar(item_content))
                    i += 1
            return items, i

        # Mapping block
        mapping: Dict[str, Any] = {}
        while i < len(lines):
            indent, content = lines[i]
            if indent < base_indent:
                break
            if indent > base_indent:
                break
            if content.startswith("- "):
                break
            if ":" not in content:
                i += 1
                continue
            key, _, val = content.partition(":")
            key = key.strip()
            val_stripped = val.strip()
            if val_stripped == "":
                sub, i_next = parse_block(i + 1, base_indent + 2)
                mapping[key] = sub
                i = i_next
            else:
                mapping[key] = parse_scalar(val_stripped)
                i += 1
        return mapping, i

    result, _ = parse_block(0, 0)
    return result if isinstance(result, dict) else {}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEFAULT_GRANTS = {
    "read": ["*"],
    "write": [],
}


class WikiRegistry:
    """Resolves vault root, parses registry.yaml, enforces access control."""

    def __init__(self, vault_root: str, registry_data: Dict[str, Any], agent_id: str,
                 plugin_config: Optional[Dict[str, Any]] = None):
        self.vault_root = os.path.abspath(vault_root)
        self.data = registry_data or {}
        self.agent_id = agent_id or "unknown_agent"
        self.plugin_config = plugin_config or {}

    # ---------- construction helpers ----------

    @classmethod
    def from_config(cls, plugin_config: Dict[str, Any], agent_id: str,
                    fallback_project_dir: Optional[str] = None) -> Optional["WikiRegistry"]:
        """Build a registry from plugin config. Returns None if no vault root
        could be resolved (caller falls back to legacy single-wiki mode)."""
        shared_cfg = (plugin_config or {}).get("shared_vault", {}) or {}
        vault_root = shared_cfg.get("path", "") or ""
        enabled = bool(shared_cfg.get("enabled", False))

        if not enabled:
            # Allow auto-detection: if fallback_project_dir contains a registry.yaml,
            # treat project_dir as a single-wiki mode fallback (legacy).
            if fallback_project_dir and os.path.isfile(
                os.path.join(fallback_project_dir, "registry.yaml")
            ):
                vault_root = fallback_project_dir
            else:
                return None
        elif not vault_root:
            # Enabled but no path given — try auto-detect
            vault_root = cls._autodetect_vault(fallback_project_dir)
            if not vault_root:
                return None

        vault_root = os.path.expanduser(vault_root)
        if not os.path.isdir(vault_root):
            return None

        reg_path = os.path.join(vault_root, "registry.yaml")
        data: Dict[str, Any] = {}
        if os.path.isfile(reg_path):
            try:
                with open(reg_path, "r", encoding="utf-8") as f:
                    data = _load_yaml(f.read())
            except Exception:
                data = {}

        return cls(vault_root, data, agent_id, plugin_config=plugin_config)

    @staticmethod
    def _autodetect_vault(project_dir: Optional[str]) -> str:
        """Walk upward from project_dir looking for registry.yaml. Also probes
        a sibling SharedBrain/ directory — the default layout for Adam's setup
        where SharedBrain/ lives next to usr/ in the Agent Zero install root."""
        candidates: List[str] = []
        if project_dir:
            candidates.append(project_dir)
            parent = os.path.dirname(project_dir)
            if parent and parent != project_dir:
                candidates.append(parent)
                gp = os.path.dirname(parent)
                if gp and gp != parent:
                    candidates.append(gp)

        for base in list(candidates):
            sib = os.path.join(base, "SharedBrain")
            if os.path.isfile(os.path.join(sib, "registry.yaml")):
                return sib

        for base in candidates:
            if os.path.isfile(os.path.join(base, "registry.yaml")):
                return base

        return ""

    # ---------- wiki resolution ----------

    def list_wikis(self) -> List[Dict[str, Any]]:
        """Return every wiki in the registry, with absolute paths resolved."""
        wikis = self.data.get("wikis", []) or []
        out = []
        for w in wikis:
            if not isinstance(w, dict):
                continue
            name = w.get("name")
            path = w.get("path", "")
            if not name or not path:
                continue
            abs_path = path if os.path.isabs(path) else os.path.join(self.vault_root, path)
            abs_path = os.path.normpath(abs_path)
            out.append({
                "name": name,
                "title": w.get("title", name),
                "path": abs_path,
                "scope": w.get("scope", "shared"),
                "description": w.get("description", ""),
                "tags": w.get("tags", []) or [],
                "sensitivity": w.get("sensitivity", "internal"),
                "default_for_ingest": bool(w.get("default_for_ingest", False)),
                "exists": os.path.isdir(abs_path),
            })
        return out

    def get_wiki(self, name: str) -> Optional[Dict[str, Any]]:
        for w in self.list_wikis():
            if w["name"] == name:
                return w
        return None

    def default_ingest_wiki(self) -> Optional[Dict[str, Any]]:
        wikis = self.list_wikis()
        for w in wikis:
            if w["default_for_ingest"]:
                return w
        # fallback to first
        return wikis[0] if wikis else None

    # ---------- access control ----------

    def _grants(self) -> Dict[str, List[str]]:
        grants_all = self.data.get("grants", {}) or {}
        return grants_all.get(self.agent_id, DEFAULT_GRANTS)

    def _matches(self, name: str, allowed: List[str]) -> bool:
        if not allowed:
            return False
        if "*" in allowed:
            return True
        return name in allowed

    def can_read(self, wiki_name: str) -> bool:
        return self._matches(wiki_name, self._grants().get("read", []))

    def can_write(self, wiki_name: str) -> bool:
        return self._matches(wiki_name, self._grants().get("write", []))

    def readable_wikis(self) -> List[Dict[str, Any]]:
        return [w for w in self.list_wikis() if self.can_read(w["name"])]

    def writable_wikis(self) -> List[Dict[str, Any]]:
        return [w for w in self.list_wikis() if self.can_write(w["name"])]

    # ---------- query config ----------

    def query_config(self) -> Dict[str, Any]:
        q = self.data.get("query", {}) or {}
        return {
            "default_scope": q.get("default_scope", "all_readable"),
            "max_wikis_per_query": int(q.get("max_wikis_per_query", 6)),
            "max_pages_per_wiki": int(q.get("max_pages_per_wiki", 15)),
            "namespaced_citations": bool(q.get("namespaced_citations", True)),
        }

    # ---------- paths ----------

    def wiki_paths(self, wiki: Dict[str, Any]) -> Dict[str, str]:
        root = wiki["path"]
        return {
            "root": root,
            "raw_dir": os.path.join(root, "wiki_raw"),
            "wiki_dir": os.path.join(root, "wiki"),
            "index": os.path.join(root, "wiki", "index.md"),
            "log": os.path.join(root, "wiki", "log.md"),
            "graphify": os.path.join(root, "graphify-out"),
        }

    # ---------- coverage indicators ----------

    def coverage_config(self) -> Dict[str, Any]:
        """Whether the ingest/query pipeline should use coverage tags."""
        cov = (self.plugin_config or {}).get("coverage", {}) or {}
        return {
            "enabled": bool(cov.get("enabled", True)),
            "tags": cov.get("tags", ["high", "medium", "low"]),
        }

    # ---------- git auto-commit ----------

    def git_config(self) -> Dict[str, Any]:
        g = (self.plugin_config or {}).get("git", {}) or {}
        return {
            "auto_commit": bool(g.get("auto_commit", False)),
            "commit_prefix": g.get("commit_prefix", "[llm_wiki]"),
            "committer_name": g.get("committer_name", "") or self.agent_id,
            "committer_email": g.get("committer_email", "llm-wiki@sharedbrain.local"),
        }

    def is_git_repo(self) -> bool:
        """True if the vault root is inside a git working tree."""
        try:
            rc = subprocess.run(
                ["git", "-C", self.vault_root, "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=5,
            )
            return rc.returncode == 0 and rc.stdout.strip() == "true"
        except Exception:
            return False

    def git_commit_after(self, op: str, wiki_name: str, message: str,
                         paths: Optional[List[str]] = None) -> Dict[str, Any]:
        """Stage changes and commit them to the vault repo.

        Returns a result dict: {ok: bool, committed: bool, reason: str, sha: str}.
        Silent no-op (ok=True, committed=False) if:
          - git.auto_commit is disabled, or
          - git is not available, or
          - the vault is not a git repo, or
          - there are no changes to commit.

        This helper is best-effort: it never raises, and never pushes."""
        gcfg = self.git_config()
        if not gcfg["auto_commit"]:
            return {"ok": True, "committed": False, "reason": "auto_commit disabled", "sha": ""}
        if not self.is_git_repo():
            return {"ok": True, "committed": False, "reason": "not a git repo", "sha": ""}

        env = os.environ.copy()
        env.setdefault("GIT_AUTHOR_NAME", gcfg["committer_name"])
        env.setdefault("GIT_AUTHOR_EMAIL", gcfg["committer_email"])
        env.setdefault("GIT_COMMITTER_NAME", gcfg["committer_name"])
        env.setdefault("GIT_COMMITTER_EMAIL", gcfg["committer_email"])

        try:
            if paths:
                subprocess.run(
                    ["git", "-C", self.vault_root, "add", "--"] + paths,
                    capture_output=True, text=True, timeout=15, env=env,
                )
            else:
                subprocess.run(
                    ["git", "-C", self.vault_root, "add", "-A"],
                    capture_output=True, text=True, timeout=15, env=env,
                )

            # Nothing staged? -> no commit
            diff = subprocess.run(
                ["git", "-C", self.vault_root, "diff", "--cached", "--quiet"],
                capture_output=True, text=True, timeout=5, env=env,
            )
            if diff.returncode == 0:
                return {"ok": True, "committed": False, "reason": "no changes", "sha": ""}

            full_msg = f"{gcfg['commit_prefix']} [{op}] {wiki_name}: {message} (by {self.agent_id})"
            commit = subprocess.run(
                ["git", "-C", self.vault_root, "commit", "-m", full_msg,
                 "--no-verify", "--no-gpg-sign"],
                capture_output=True, text=True, timeout=15, env=env,
            )
            if commit.returncode != 0:
                return {"ok": False, "committed": False,
                        "reason": commit.stderr.strip() or "commit failed", "sha": ""}

            rev = subprocess.run(
                ["git", "-C", self.vault_root, "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5, env=env,
            )
            return {
                "ok": True, "committed": True, "reason": "ok",
                "sha": rev.stdout.strip() if rev.returncode == 0 else "",
            }
        except Exception as e:
            return {"ok": False, "committed": False, "reason": str(e), "sha": ""}

    # ---------- registry mutation (wiki_register) ----------

    def append_wiki_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Append a new wiki block to registry.yaml on disk.

        We do NOT round-trip the parsed data (the tiny parser would lose
        comments and formatting); we append a new YAML block as text after
        the existing `wikis:` section. Returns {ok, reason, path}."""
        reg_path = os.path.join(self.vault_root, "registry.yaml")
        if not os.path.isfile(reg_path):
            return {"ok": False, "reason": f"registry.yaml not found at {reg_path}",
                    "path": reg_path}

        required = ["name", "path", "scope", "sensitivity"]
        for k in required:
            if not entry.get(k):
                return {"ok": False, "reason": f"missing required field: {k}", "path": reg_path}

        # Guard against dupes
        if self.get_wiki(entry["name"]):
            return {"ok": False, "reason": f"wiki `{entry['name']}` already registered",
                    "path": reg_path}

        try:
            with open(reg_path, "r", encoding="utf-8") as f:
                original = f.read()
        except Exception as e:
            return {"ok": False, "reason": f"read error: {e}", "path": reg_path}

        # Build a pretty YAML block that matches the style of the existing file.
        tags = entry.get("tags", []) or []
        tag_str = "[" + ", ".join(tags) + "]" if tags else "[]"
        block_lines = [
            "",
            f"  - name: {entry['name']}",
            f"    title: {_yaml_quote(entry.get('title') or entry['name'])}",
            f"    path: {_yaml_quote(entry['path'])}",
            f"    scope: {entry['scope']}",
            f"    description: {_yaml_quote(entry.get('description', ''))}",
            f"    tags: {tag_str}",
            f"    sensitivity: {entry['sensitivity']}",
            f"    default_for_ingest: {'true' if entry.get('default_for_ingest') else 'false'}",
        ]
        new_block = "\n".join(block_lines) + "\n"

        # Insert after the last existing wiki entry and before the `grants:` section
        # to keep the file well-structured. Simplest heuristic: insert just before
        # the `# ----` comment block that separates wikis: from grants:, or before
        # a line that starts with 'grants:' at column 0.
        marker_idx = original.find("\ngrants:")
        if marker_idx >= 0:
            # Find the comment block (if any) that precedes it
            # Walk backward from marker_idx to find the nearest blank line
            insert_at = marker_idx
            # Look for the sentinel "# ---" banner preceding grants:
            banner = original.rfind("\n# ----", 0, marker_idx)
            if banner >= 0:
                insert_at = banner
            updated = original[:insert_at] + new_block + original[insert_at:]
        else:
            # Fallback: append to end
            updated = original.rstrip() + "\n" + new_block

        try:
            with open(reg_path, "w", encoding="utf-8") as f:
                f.write(updated)
        except Exception as e:
            return {"ok": False, "reason": f"write error: {e}", "path": reg_path}

        # Refresh in-memory view
        try:
            with open(reg_path, "r", encoding="utf-8") as f:
                self.data = _load_yaml(f.read()) or {}
        except Exception:
            pass

        return {"ok": True, "reason": "added", "path": reg_path}

    # ---------- summary / debug ----------

    def summary(self) -> str:
        lines = [
            f"Vault root: {self.vault_root}",
            f"Agent id:   {self.agent_id}",
            f"Grants:     read={self._grants().get('read', [])} write={self._grants().get('write', [])}",
            f"Wikis ({len(self.list_wikis())}):",
        ]
        for w in self.list_wikis():
            r = "R" if self.can_read(w["name"]) else "-"
            wr = "W" if self.can_write(w["name"]) else "-"
            ok = "\u2713" if w["exists"] else "\u2717"
            lines.append(
                f"  [{r}{wr}] {ok} {w['name']:<20} {w['scope']:<10} \u2014 {w['description'][:60]}"
            )
        return "\n".join(lines)
