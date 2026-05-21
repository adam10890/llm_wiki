"""
wiki_query — answer a question by reading compiled wiki pages.

Multi-wiki aware:
- If a SharedBrain registry is configured, query fans out across every wiki
  the agent has READ grant on (capped by query.max_wikis_per_query).
- Accepts an optional `wikis` argument to narrow to a specific list.
- Cites answers with namespaced backlinks (`wiki_name::[[page]]`) when
  query.namespaced_citations is true.
- Legacy single-wiki mode still works if registry is absent.
"""

import os
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


class WikiQuery(WikiToolBase):
    """Search wikis and synthesize an answer with citations."""

    async def execute(self, **kwargs):
        # Accept common synonyms — agents often use `query`/`q`/`search` instead
        # of `question`. Same for `wiki` (singular) instead of `wikis` (plural).
        question = ""
        for key in ("question", "query", "q", "search", "text"):
            val = self.args.get(key)
            if isinstance(val, str) and val.strip():
                question = val.strip()
                break

        save_answer = bool(self.args.get("save_answer", False))
        wikis_arg = self.args.get("wikis")
        if wikis_arg is None:
            wikis_arg = self.args.get("wiki")  # singular alias

        if not question:
            return Response(
                message=(
                    "Please provide a question.\n\n"
                    "Expected JSON:\n"
                    "```json\n"
                    "{\n"
                    '  "tool_name": "wiki_query",\n'
                    '  "tool_args": {\n'
                    '    "question": "<your knowledge question>",\n'
                    '    "wikis": ["commons"]\n'
                    "  }\n"
                    "}\n"
                    "```\n"
                    "Required: `question` (alias: `query`/`q`/`search`/`text`).\n"
                    "Optional: `wikis` (list of wiki names; omit for all-readable fan-out)."
                ),
                break_loop=False,
            )

        config = self._get_config()
        agent_id = self._get_agent_id()
        project_dir = self._get_project_dir()

        registry = WikiRegistry.from_config(
            plugin_config=config,
            agent_id=agent_id,
            fallback_project_dir=project_dir,
        )

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ---------------- multi-wiki mode ----------------
        if registry is not None:
            qcfg = registry.query_config()
            max_wikis = qcfg["max_wikis_per_query"]
            max_pages = qcfg["max_pages_per_wiki"]
            namespaced = qcfg["namespaced_citations"]

            # Resolve which wikis to consult
            if isinstance(wikis_arg, str):
                wikis_arg = [w.strip() for w in wikis_arg.split(",") if w.strip()]

            if wikis_arg:
                selected = []
                missing_access = []
                not_found = []
                for name in wikis_arg:
                    w = registry.get_wiki(name)
                    if w is None:
                        not_found.append(name)
                    elif not registry.can_read(name):
                        missing_access.append(name)
                    else:
                        selected.append(w)
                if not_found:
                    return Response(
                        message=f"Unknown wikis: {not_found}. Available: {[w['name'] for w in registry.list_wikis()]}",
                        break_loop=False,
                    )
                if missing_access:
                    return Response(
                        message=f"Agent `{agent_id}` cannot read: {missing_access}. Check grants in registry.yaml.",
                        break_loop=False,
                    )
            else:
                selected = registry.readable_wikis()

            if not selected:
                return Response(
                    message=f"No readable wikis for agent `{agent_id}`. Check registry.yaml grants.",
                    break_loop=False,
                )

            # Cap fan-out
            selected = [w for w in selected if w["exists"]][:max_wikis]
            if not selected:
                return Response(
                    message="All readable wikis are registered but their directories don't exist on disk.",
                    break_loop=False,
                )

            result_parts = [
                f"## Wiki Query (multi-wiki)",
                f"**Question:** {question}",
                f"**Agent:** {agent_id}",
                f"**Timestamp:** {timestamp}",
                f"**Wikis consulted ({len(selected)}):** {', '.join(w['name'] for w in selected)}",
                "",
            ]

            total_pages_loaded = 0
            for w in selected:
                paths = registry.wiki_paths(w)
                result_parts.append(f"### Wiki: `{w['name']}` ({w['scope']})")
                result_parts.append(f"_Path: {paths['wiki_dir']}_")
                result_parts.append("")

                # Read index
                if os.path.isfile(paths["index"]):
                    try:
                        idx = files.read_file(paths["index"])
                        result_parts.append(f"**Index of `{w['name']}`:**")
                        result_parts.append(idx[:4000])
                        if len(idx) > 4000:
                            result_parts.append("_[index truncated]_")
                        result_parts.append("")
                    except Exception:
                        pass
                else:
                    result_parts.append(f"_(no index file yet)_")
                    result_parts.append("")
                    continue

                # Load pages
                pages = self._load_wiki_pages(paths["wiki_dir"], max_pages)
                total_pages_loaded += len(pages)
                for page_path, content in pages:
                    rel = os.path.relpath(page_path, paths["wiki_dir"])
                    display = content[:4000]
                    if len(content) > 4000:
                        display += f"\n_[truncated — full at {w['name']}/wiki/{rel}]_"
                    result_parts.extend([
                        f"#### `{w['name']}::{rel}`",
                        display,
                        "",
                    ])

            result_parts.extend([
                "### Instructions",
                f"Answer the question: **{question}**",
                "- Use information from the wiki pages above",
                f"- Cite pages with {'NAMESPACED' if namespaced else 'plain'} backlinks"
                + (f" — e.g. `commons::[[page-name]]`" if namespaced else " — e.g. `[[page-name]]`"),
                "- If multiple wikis agree, cite all of them.",
                "- If wikis contradict, say so and cite both sides.",
                "- If nothing in the wikis answers the question, say so and suggest which sources to ingest.",
                f"- Append to each consulted wiki's `wiki/log.md`: `## [{timestamp}] [QUERY] {question[:80]} (by {agent_id})`",
            ])

            if save_answer:
                default = registry.default_ingest_wiki()
                if default and registry.can_write(default["name"]):
                    result_parts.extend([
                        "",
                        f"**Save this answer** to the default wiki `{default['name']}`:",
                        f"1. Write to `{default['name']}/wiki/queries/{timestamp.replace(':', '-').replace(' ', '_')}-query.md`",
                        f"2. Update `{default['name']}/wiki/index.md`",
                        f"3. Append to `{default['name']}/wiki/log.md`",
                    ])
                else:
                    result_parts.extend([
                        "",
                        f"_(save_answer requested but no writable default wiki — skipping save)_",
                    ])

            result_parts.insert(5, f"**Total pages loaded:** {total_pages_loaded}")
            result_parts.insert(6, "")

            # Conservative token estimate: Hebrew/mixed content ≈ 3 chars/token.
            # Appended as an HTML comment so the router can parse it without
            # the LLM tripping over it.
            full_text = "\n".join(result_parts)
            token_est = max(1, len(full_text) // 3)
            result_parts.append(
                f"<!-- token_estimate: {token_est} "
                f"pages_loaded: {total_pages_loaded} "
                f"wikis_queried: {len(selected)} -->"
            )

            return Response(message="\n".join(result_parts), break_loop=False)

        # ---------------- legacy single-wiki mode ----------------
        if not project_dir:
            return Response(
                message="No active project and no SharedBrain vault configured.",
                break_loop=False,
            )

        wiki_dir = os.path.join(project_dir, self._cfg(config, "wiki_dir", "wiki"))
        index_path = os.path.join(wiki_dir, self._cfg(config, "index_file", "index.md"))

        if not os.path.isfile(index_path):
            return Response(
                message="No wiki index found. Ingest some sources first using wiki_ingest.",
                break_loop=False,
            )

        try:
            index_content = files.read_file(index_path)
        except Exception as e:
            return Response(message=f"Error reading index: {e}", break_loop=False)

        max_pages = int(self._cfg(config, "max_context_pages", 15))
        pages = self._load_wiki_pages(wiki_dir, max_pages)

        result_parts = [
            f"## Wiki Query (single-wiki)",
            f"**Question:** {question}",
            f"**Timestamp:** {timestamp}",
            f"**Wiki directory:** {wiki_dir}",
            f"**Pages loaded:** {len(pages)}",
            "",
            "### Wiki Index",
            index_content,
            "",
        ]
        for page_path, content in pages:
            rel = os.path.relpath(page_path, wiki_dir)
            display = content[:5000]
            if len(content) > 5000:
                display += f"\n\n_[truncated — full at {rel}]_"
            result_parts.extend([f"### Page: {rel}", display, ""])

        result_parts.extend([
            "### Instructions",
            f"Answer the question: **{question}**",
            "- Cite pages with `[[page-name]]` backlinks",
            "- If the wiki is insufficient, say so and suggest sources to ingest",
        ])
        if save_answer:
            result_parts.extend([
                "",
                "**Save this answer:**",
                f"1. Write to `wiki/queries/{timestamp.replace(':', '-').replace(' ', '_')}-query.md`",
                "2. Update index.md",
                f"3. Append to log.md: `## [{timestamp}] [QUERY] {question[:80]}`",
            ])

        full_text = "\n".join(result_parts)
        token_est = max(1, len(full_text) // 3)
        result_parts.append(
            f"<!-- token_estimate: {token_est} "
            f"pages_loaded: {len(pages)} "
            f"wikis_queried: 1 -->"
        )

        return Response(message="\n".join(result_parts), break_loop=False)

    # ----------------------------------------------------------------

    def _load_wiki_pages(self, wiki_dir, max_pages):
        exclude = {"index.md", "log.md"}
        pages = []
        if not os.path.isdir(wiki_dir):
            return pages
        for root, _, fnames in os.walk(wiki_dir):
            for f in fnames:
                if f.endswith(".md") and f not in exclude:
                    fp = os.path.join(root, f)
                    pages.append((fp, os.path.getmtime(fp)))
        pages.sort(key=lambda x: x[1], reverse=True)
        out = []
        for fp, _ in pages[:max_pages]:
            try:
                out.append((fp, files.read_file(fp)))
            except Exception:
                continue
        return out



# A0 v1.10 module loader picks the last alphabetically-ordered class that subclasses Tool;
# remove the imported base from the module namespace so it picks the concrete tool defined here.
del WikiToolBase
