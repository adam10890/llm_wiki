"""
wiki_ingest — compile a raw source into a named wiki.

Multi-wiki aware: accepts an optional `wiki` argument to target a specific
wiki in the SharedBrain registry. Falls back to legacy per-project mode
(project_dir + wiki_raw/ + wiki/) if no registry is configured.

Access control: refuses to write to a wiki the agent doesn't have write grant
on, per registry.yaml → grants.<agent_id>.write.
"""

import os
import json
from datetime import datetime

try:
    from ._base import WikiToolBase, WikiRegistry, Response, files
except ImportError:
    # Agent Zero v1.10+ loads tool files via importlib.spec_from_file_location
    # without a package context, breaking relative imports. Fall back to absolute.
    import os as _os, sys as _sys
    _here = _os.path.dirname(_os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)
    from _base import WikiToolBase, WikiRegistry, Response, files  # type: ignore


class WikiIngest(WikiToolBase):
    """Ingest a raw source document into a wiki (multi-wiki aware)."""

    async def execute(self, **kwargs):
        # Accept common synonyms for source_path and wiki name
        source_path = ""
        for key in ("source_path", "source", "path", "file", "filename"):
            val = self.args.get(key)
            if isinstance(val, str) and val.strip():
                source_path = val.strip()
                break

        focus = self.args.get("focus", "") or ""

        wiki_name = ""
        for key in ("wiki", "wiki_name", "target", "wikis"):
            val = self.args.get(key)
            if isinstance(val, str) and val.strip():
                wiki_name = val.strip()
                break
            if isinstance(val, list) and val:
                wiki_name = str(val[0]).strip()
                break

        config = self._get_config()
        agent_id = self._get_agent_id()
        project_dir = self._get_project_dir()

        registry = WikiRegistry.from_config(
            plugin_config=config,
            agent_id=agent_id,
            fallback_project_dir=project_dir,
        )

        # ---------------- multi-wiki mode ----------------
        if registry is not None:
            # Resolve target wiki
            if wiki_name:
                target = registry.get_wiki(wiki_name)
                if target is None:
                    available = ", ".join(w["name"] for w in registry.list_wikis())
                    return Response(
                        message=f"Wiki `{wiki_name}` not found in registry.\nAvailable: {available}",
                        break_loop=False,
                    )
            else:
                target = registry.default_ingest_wiki()
                if target is None:
                    return Response(
                        message="No default wiki configured. Set `default_for_ingest: true` on one wiki in registry.yaml, "
                                "or pass the `wiki` argument explicitly.",
                        break_loop=False,
                    )

            if not target["exists"]:
                return Response(
                    message=f"Wiki `{target['name']}` is registered but the directory does not exist: {target['path']}",
                    break_loop=False,
                )

            # Access control
            if not registry.can_write(target["name"]):
                return Response(
                    message=(
                        f"Agent `{agent_id}` does not have WRITE access to wiki `{target['name']}`.\n"
                        f"Grants: {registry._grants()}\n"
                        f"To fix: update `registry.yaml` → `grants.{agent_id}.write` to include `{target['name']}`."
                    ),
                    break_loop=False,
                )

            paths = registry.wiki_paths(target)
            return await self._do_ingest(
                source_path=source_path,
                focus=focus,
                raw_dir=paths["raw_dir"],
                wiki_dir=paths["wiki_dir"],
                index_path=paths["index"],
                log_path=paths["log"],
                graphify_dir=paths["graphify"],
                wiki_name=target["name"],
                agent_id=agent_id,
                config=config,
            )

        # ---------------- legacy per-project mode ----------------
        if not project_dir:
            return Response(
                message=(
                    "No active project and no SharedBrain vault configured.\n"
                    "Either:\n"
                    "  1. Open a project with wiki_raw/ + wiki/, or\n"
                    "  2. Set shared_vault.enabled=true and shared_vault.path=<abs path> in plugin config."
                ),
                break_loop=False,
            )

        raw_dir = os.path.join(project_dir, self._cfg(config, "raw_dir", "wiki_raw"))
        wiki_dir = os.path.join(project_dir, self._cfg(config, "wiki_dir", "wiki"))
        index_path = os.path.join(wiki_dir, self._cfg(config, "index_file", "index.md"))
        log_path = os.path.join(wiki_dir, self._cfg(config, "log_file", "log.md"))
        graphify_dir = os.path.join(project_dir, "graphify-out")

        return await self._do_ingest(
            source_path=source_path,
            focus=focus,
            raw_dir=raw_dir,
            wiki_dir=wiki_dir,
            index_path=index_path,
            log_path=log_path,
            graphify_dir=graphify_dir,
            wiki_name="<project>",
            agent_id=agent_id,
            config=config,
        )

    # ----------------------------------------------------------------
    # Core ingest logic (wiki-agnostic)
    # ----------------------------------------------------------------

    async def _do_ingest(self, source_path, focus, raw_dir, wiki_dir, index_path,
                         log_path, graphify_dir, wiki_name, agent_id, config):
        abs_source = os.path.join(raw_dir, source_path) if source_path else ""
        if not abs_source or not os.path.isfile(abs_source):
            available = self._list_raw_files(raw_dir)
            if available:
                listing = "\n".join(f"  - {f}" for f in available)
                return Response(
                    message=(
                        f"Source file not found: '{source_path}' in wiki `{wiki_name}`\n"
                        f"Raw dir: {raw_dir}\n"
                        f"Available raw sources:\n{listing}"
                    ),
                    break_loop=False,
                )
            else:
                return Response(
                    message=(
                        f"No raw source files found in `{raw_dir}` (wiki: {wiki_name}).\n"
                        f"Drop markdown/text documents into that directory first."
                    ),
                    break_loop=False,
                )

        try:
            source_content = files.read_file(abs_source)
        except Exception as e:
            return Response(message=f"Error reading source file: {e}", break_loop=False)

        index_content = ""
        if os.path.isfile(index_path):
            try:
                index_content = files.read_file(index_path)
            except Exception:
                pass

        ingest_count = 0
        if os.path.isfile(log_path):
            try:
                log_content = files.read_file(log_path)
                ingest_count = log_content.count("[INGEST]")
            except Exception:
                pass

        os.makedirs(wiki_dir, exist_ok=True)

        source_name = os.path.basename(abs_source)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        existing_pages = self._list_wiki_pages(wiki_dir)

        result_parts = [
            f"## Wiki Ingest: `{wiki_name}` ← {source_name}",
            f"**Agent:** {agent_id}",
            f"**Timestamp:** {timestamp}",
            f"**Source path:** {abs_source}",
            f"**Wiki directory:** {wiki_dir}",
            f"**Existing wiki pages ({len(existing_pages)}):** {', '.join(existing_pages[:30]) if existing_pages else 'none yet'}"
            + (f" _(+{len(existing_pages) - 30} more)_" if len(existing_pages) > 30 else ""),
            "",
        ]

        if focus:
            result_parts.extend([f"**Focus area:** {focus}", ""])

        graph_context = self._load_graph_context(graphify_dir, source_name)
        if graph_context:
            result_parts.extend(["### Graph Context (from graphify)", graph_context, ""])

        result_parts.extend([
            "### Current Index",
            index_content if index_content.strip() else "_No index yet — you will create it._",
            "",
            "### Source Content",
            f"```\n{source_content[:15000]}\n```",
            "",
            "### Instructions",
            f"Compile this source into the `{wiki_name}` wiki:",
            f"1. Write a summary page: `wiki/sources/YYYY-MM-DD-{os.path.splitext(source_name)[0]}.md`",
            "2. Create or update entity/concept pages as needed",
            "3. Add `[[backlinks]]` between related pages. Use namespaced `<other_wiki>::[[page]]` "
            "syntax if you reference pages from other wikis.",
            "4. Update `wiki/index.md` with new/changed entries",
            f"5. Append to `wiki/log.md`: `## [{timestamp}] [INGEST] {source_name} (by {agent_id})`",
            f"6. Call `wiki_commit` with wiki=`{wiki_name}` to seal the changes into git.",
            f"7. **Only if the commit succeeded**, delete the raw source file: `{abs_source}`. "
            "The content is now preserved in git history + summarised in `wiki/sources/`. "
            "If `git.auto_commit` is disabled or the commit failed, leave the raw file alone and tell the user.",
            self._coverage_block(config),
            self._git_footer(config),
            "",
            "Use file writes to create the compiled pages. Do NOT edit, rename, or move files in wiki_raw/ — the only allowed mutation is the final delete in step 7.",
        ])

        auto_lint_n = int(self._cfg(config, "auto_lint_after_n_ingests", 5))
        if auto_lint_n > 0 and (ingest_count + 1) % auto_lint_n == 0:
            result_parts.extend([
                "",
                f"⚠️ Ingest #{ingest_count + 1} — auto-lint threshold reached ({auto_lint_n}). "
                f"Run `wiki_lint wiki={wiki_name}` after this ingest.",
            ])

        return Response(message="\n".join(result_parts), break_loop=False)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------


    def _coverage_block(self, config) -> str:
        """Return a per-section coverage-tag instruction block, or '' if disabled."""
        cov = (config or {}).get("coverage", {}) if isinstance(config, dict) else {}
        if isinstance(cov, dict) and not cov.get("enabled", True):
            return ""
        tags = (cov.get("tags") if isinstance(cov, dict) else None) or ["high", "medium", "low"]
        return (
            "\n**Coverage indicators:** annotate each substantive H2/H3 section with a tag — "
            f"one of {tags}. Format: `## Section Name <!-- coverage: high -->`. "
            "`high` = directly sourced w/ minimal inference; `medium` = partial coverage; "
            "`low` = stub or heavy inference. These feed downstream trust decisions."
        )

    def _git_footer(self, config) -> str:
        g = (config or {}).get("git", {}) if isinstance(config, dict) else {}
        if isinstance(g, dict) and g.get("auto_commit", False):
            return (
                "\n**After writing files:** call `wiki_commit` to record the changes in git. "
                "Git auto-commit is enabled in plugin config."
            )
        return ""

    def _list_raw_files(self, raw_dir):
        if not os.path.isdir(raw_dir):
            return []
        out = []
        for root, _, fnames in os.walk(raw_dir):
            for f in fnames:
                if not f.startswith(".") and f != "README.md":
                    out.append(os.path.relpath(os.path.join(root, f), raw_dir))
        return sorted(out)

    def _list_wiki_pages(self, wiki_dir):
        if not os.path.isdir(wiki_dir):
            return []
        exclude = {"index.md", "log.md"}
        out = []
        for root, _, fnames in os.walk(wiki_dir):
            for f in fnames:
                if f.endswith(".md") and f not in exclude:
                    out.append(os.path.relpath(os.path.join(root, f), wiki_dir))
        return sorted(out)

    def _load_graph_context(self, graphify_dir, source_name):
        graph_json_path = os.path.join(graphify_dir, "graph.json")
        report_path = os.path.join(graphify_dir, "GRAPH_REPORT.md")
        if not os.path.isfile(graph_json_path):
            return ""

        parts = ["_Graphify knowledge graph detected. Use it to guide compilation._", ""]
        try:
            with open(graph_json_path, "r", encoding="utf-8") as f:
                graph_data = json.load(f)
            nodes = graph_data.get("nodes", [])
            edges = graph_data.get("edges", [])
            if not nodes:
                return ""

            degree_map = {}
            for edge in edges:
                degree_map[edge.get("source", "")] = degree_map.get(edge.get("source", ""), 0) + 1
                degree_map[edge.get("target", "")] = degree_map.get(edge.get("target", ""), 0) + 1
            god_nodes = sorted(degree_map.items(), key=lambda x: x[1], reverse=True)[:10]
            if god_nodes:
                parts.append("**God nodes:** " + ", ".join(f"**{n}** ({d})" for n, d in god_nodes))
                parts.append("")

            communities = {}
            for node in nodes:
                c = node.get("community")
                if c is not None:
                    communities.setdefault(c, []).append(node.get("label", node.get("id", "?")))
            if communities:
                parts.append(f"**Communities** ({len(communities)} clusters):")
                for cid, members in sorted(communities.items()):
                    sample = members[:8]
                    more = f" +{len(members) - 8} more" if len(members) > 8 else ""
                    parts.append(f"  - C{cid}: {', '.join(sample)}{more}")
                parts.append("")

            source_stem = os.path.splitext(source_name)[0].lower()
            related = [
                e for e in edges
                if source_stem in str(e.get("source_file", "")).lower()
                or source_stem in str(e.get("source", "")).lower()
                or source_stem in str(e.get("target", "")).lower()
            ]
            if related:
                parts.append(f"**Edges related to this source** ({len(related)}):")
                for e in related[:15]:
                    parts.append(
                        f"  - {e.get('source', '?')} —[{e.get('relation', 'related_to')} / {e.get('confidence', '?')}]→ {e.get('target', '?')}"
                    )
                parts.append("")
        except Exception as e:
            parts.append(f"_warning: could not parse graph.json: {e}_")

        if os.path.isfile(report_path):
            try:
                rc = files.read_file(report_path)
                if rc.strip():
                    parts.extend(["", "### Graph Report Summary", rc[:3000]])
                    if len(rc) > 3000:
                        parts.append("_[truncated]_")
            except Exception:
                pass

        return "\n".join(parts)



# A0 v1.10 module loader picks the last alphabetically-ordered class that subclasses Tool;
# remove the imported base from the module namespace so it picks the concrete tool defined here.
del WikiToolBase
