"""
wiki_lint — health-check one wiki.

Multi-wiki aware: accepts `wiki` argument to target a specific wiki.
Refuses to lint a wiki the agent can't read. Refuses to fix issues in a
wiki the agent can't write to.
"""

import os
import re
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


class WikiLint(WikiToolBase):
    """Health-check a wiki."""

    async def execute(self, **kwargs):
        scope = self.args.get("scope", "full") or "full"
        fix = bool(self.args.get("fix", False))

        wiki_name = ""
        for key in ("wiki", "wiki_name", "target", "name"):
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
            if wiki_name:
                target = registry.get_wiki(wiki_name)
                if target is None:
                    return Response(
                        message=f"Wiki `{wiki_name}` not found. Available: {[w['name'] for w in registry.list_wikis()]}",
                        break_loop=False,
                    )
            else:
                target = registry.default_ingest_wiki()
                if target is None:
                    return Response(
                        message="No default wiki configured. Pass the `wiki` argument explicitly.",
                        break_loop=False,
                    )

            if not registry.can_read(target["name"]):
                return Response(
                    message=f"Agent `{agent_id}` cannot read wiki `{target['name']}`. Check grants.",
                    break_loop=False,
                )

            if fix and not registry.can_write(target["name"]):
                return Response(
                    message=(
                        f"Agent `{agent_id}` cannot WRITE to wiki `{target['name']}`, so fix mode is not allowed.\n"
                        f"Re-run without `fix: true` for a report-only lint, or update grants."
                    ),
                    break_loop=False,
                )

            paths = registry.wiki_paths(target)
            return await self._do_lint(
                wiki_dir=paths["wiki_dir"],
                index_path=paths["index"],
                log_path=paths["log"],
                wiki_name=target["name"],
                scope=scope,
                fix=fix,
                agent_id=agent_id,
                config=config,
            )

        # ---------------- legacy mode ----------------
        if not project_dir:
            return Response(
                message="No active project and no SharedBrain vault configured.",
                break_loop=False,
            )
        wiki_dir = os.path.join(project_dir, self._cfg(config, "wiki_dir", "wiki"))
        index_path = os.path.join(wiki_dir, self._cfg(config, "index_file", "index.md"))
        log_path = os.path.join(wiki_dir, self._cfg(config, "log_file", "log.md"))
        return await self._do_lint(
            wiki_dir=wiki_dir,
            index_path=index_path,
            log_path=log_path,
            wiki_name="<project>",
            scope=scope,
            fix=fix,
            agent_id=agent_id,
            config=config,
        )

    # ----------------------------------------------------------------

    async def _do_lint(self, wiki_dir, index_path, log_path, wiki_name, scope, fix, agent_id, config):
        if not os.path.isdir(wiki_dir):
            return Response(
                message=f"Wiki directory does not exist: {wiki_dir}",
                break_loop=False,
            )

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        max_pages = int(self._cfg(config, "max_pages_per_lint", 30))
        exclude = {"index.md", "log.md"}

        all_pages = {}
        for root, _, fnames in os.walk(wiki_dir):
            for f in fnames:
                if f.endswith(".md") and f not in exclude and not f.startswith("lint-"):
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, wiki_dir)
                    try:
                        all_pages[rel] = files.read_file(full)
                    except Exception:
                        pass

        if not all_pages:
            return Response(
                message=f"Wiki `{wiki_name}` is empty — nothing to lint.",
                break_loop=False,
            )

        index_content = ""
        if os.path.isfile(index_path):
            try:
                index_content = files.read_file(index_path)
            except Exception:
                pass

        issues = []

        # 1. Orphan pages (not in index) — 🟡
        for page in all_pages:
            page_stem = os.path.splitext(os.path.basename(page))[0]
            if page_stem not in index_content and page not in index_content:
                issues.append({
                    "type": "orphan_page",
                    "tier": "yellow",
                    "page": page,
                    "detail": "Page not listed in index.md",
                })

        # 2. Broken backlinks — 🔴
        backlink_pattern = re.compile(r"(?<!::)\[\[([^\]]+)\]\]")
        cross_wiki_pattern = re.compile(r"(\w+)::\[\[([^\]]+)\]\]")
        page_stems = {os.path.splitext(os.path.basename(p))[0].lower() for p in all_pages}
        for page, content in all_pages.items():
            for m in backlink_pattern.finditer(content):
                target = m.group(1).strip().lower()
                target_stem = os.path.splitext(os.path.basename(target))[0].lower()
                if target_stem not in page_stems:
                    issues.append({
                        "type": "broken_backlink",
                        "tier": "red",
                        "page": page,
                        "detail": f"Backlink [[{m.group(1)}]] — target not found in this wiki",
                    })

        # 3. Pages with no outbound links — 🔵
        combined_pattern = re.compile(r"\[\[|::\[\[")
        for page, content in all_pages.items():
            if not combined_pattern.search(content):
                issues.append({
                    "type": "no_outbound_links",
                    "tier": "blue",
                    "page": page,
                    "detail": "Page has no outbound [[backlinks]] — consider cross-referencing",
                })

        # 4. Stub pages — 🟡
        for page, content in all_pages.items():
            if len(content.strip()) < 50:
                issues.append({
                    "type": "stub_page",
                    "tier": "yellow",
                    "page": page,
                    "detail": f"Page is very short ({len(content.strip())} chars) — may need expansion",
                })

        # 5. Empty index — 🔴
        if not index_content.strip():
            issues.append({
                "type": "empty_index",
                "tier": "red",
                "page": "index.md",
                "detail": "Index file is empty or missing",
            })

        # 6. Cross-wiki references (informational)
        xwiki_refs = []
        for page, content in all_pages.items():
            for m in cross_wiki_pattern.finditer(content):
                xwiki_refs.append((page, m.group(1), m.group(2)))

        red = [i for i in issues if i["tier"] == "red"]
        yellow = [i for i in issues if i["tier"] == "yellow"]
        blue = [i for i in issues if i["tier"] == "blue"]

        # ---- build the full report (saved to disk) ----
        report_parts = [
            f"# Wiki Lint Report — `{wiki_name}`",
            "",
            f"| Field | Value |",
            f"|---|---|",
            f"| Agent | `{agent_id}` |",
            f"| Timestamp | {timestamp} |",
            f"| Scope | {scope} |",
            f"| Pages scanned | {len(all_pages)} |",
            f"| 🔴 Broken | {len(red)} |",
            f"| 🟡 Orphan / Stub | {len(yellow)} |",
            f"| 🔵 Suggestion | {len(blue)} |",
            "",
        ]

        if not issues:
            report_parts.append("## ✅ Wiki is healthy — no issues found!")
            report_parts.append("")

        if red:
            report_parts.append("## 🔴 Broken (must fix)")
            for i in red:
                report_parts.append(f"- **{i['page']}** — {i['detail']}")
            report_parts.append("")

        if yellow:
            report_parts.append("## 🟡 Orphan / Stub (should fix)")
            for i in yellow:
                report_parts.append(f"- **{i['page']}** — {i['detail']}")
            report_parts.append("")

        if blue:
            report_parts.append("## 🔵 Suggestion (consider)")
            for i in blue:
                report_parts.append(f"- **{i['page']}** — {i['detail']}")
            report_parts.append("")

        if xwiki_refs:
            report_parts.append(f"## 🔗 Cross-wiki references ({len(xwiki_refs)})")
            for page, other, target in xwiki_refs[:20]:
                report_parts.append(f"- `{page}` → `{other}::[[{target}]]`")
            if len(xwiki_refs) > 20:
                report_parts.append(f"  _(+{len(xwiki_refs) - 20} more)_")
            report_parts.append("")

        # Pages section (semantic review context — lives in the file, not in the response)
        pages_to_review = list(all_pages.items())[:max_pages]
        report_parts.extend([
            "## Wiki Pages (semantic review)",
            f"_Loaded {len(pages_to_review)} of {len(all_pages)} pages._",
            "",
        ])
        for page_path, content in pages_to_review:
            truncated = content[:3000] + ("\n_[truncated]_" if len(content) > 3000 else "")
            report_parts.extend([f"### {page_path}", truncated, ""])

        # ---- save report to disk ----
        date_str = datetime.now().strftime("%Y-%m-%d")
        report_filename = f"lint-{date_str}.md"
        report_path = os.path.join(wiki_dir, report_filename)
        report_content = "\n".join(report_parts)
        try:
            files.write_file(report_path, report_content)
            saved_path = report_path
        except Exception as e:
            saved_path = None
            save_error = str(e)

        # ---- build concise agent response ----
        summary_parts = [
            f"## Lint: `{wiki_name}` — {timestamp}",
            f"**Pages scanned:** {len(all_pages)}  |  "
            f"🔴 {len(red)} broken  🟡 {len(yellow)} orphan/stub  🔵 {len(blue)} suggestions",
            "",
        ]

        if red:
            summary_parts.append("### 🔴 Broken (must fix)")
            for i in red:
                summary_parts.append(f"- **{i['page']}**: {i['detail']}")
            summary_parts.append("")

        if yellow:
            summary_parts.append("### 🟡 Orphan / Stub")
            for i in yellow:
                summary_parts.append(f"- **{i['page']}**: {i['detail']}")
            summary_parts.append("")

        if blue:
            summary_parts.append("### 🔵 Suggestions")
            for i in blue[:10]:
                summary_parts.append(f"- **{i['page']}**: {i['detail']}")
            if len(blue) > 10:
                summary_parts.append(f"  _(+{len(blue) - 10} more — see full report)_")
            summary_parts.append("")

        if not issues:
            summary_parts.append("✅ Wiki is healthy — no issues found!")
            summary_parts.append("")

        if saved_path:
            summary_parts.append(f"**Full report saved:** `{report_filename}` (open in Obsidian for semantic review)")
        else:
            summary_parts.append(f"⚠️ Could not save report file: {save_error}")

        summary_parts.extend([
            "",
            "### Semantic review instructions",
            "Open the saved report for the full page content, then:",
            "- Look for contradictions between pages",
            "- Identify claims superseded by newer sources",
            "- Suggest concepts that deserve their own page",
            "- Flag cross-wiki refs that should become canonical pointers",
        ])

        if fix:
            summary_parts.extend([
                "",
                "**Auto-fix mode is ON.** Repair mechanical issues:",
                "- Add missing index entries for orphan pages",
                "- Expand stub pages if enough context is available",
                "- Convert suspected cross-wiki refs to proper `wiki::[[page]]` form",
                f"- Append to log.md: `## [{timestamp}] [LINT] {wiki_name} — {len(red)}🔴 {len(yellow)}🟡 {len(blue)}🔵, auto-fix (by {agent_id})`",
            ])
        else:
            summary_parts.extend([
                "",
                "**Report-only mode.** Present findings and ask before fixing.",
                f"- Append to log.md: `## [{timestamp}] [LINT] {wiki_name} — {len(red)}🔴 {len(yellow)}🟡 {len(blue)}🔵 (by {agent_id})`",
            ])

        return Response(message="\n".join(summary_parts), break_loop=False)



# A0 v1.10 module loader picks the last alphabetically-ordered class that subclasses Tool;
# remove the imported base from the module namespace so it picks the concrete tool defined here.
del WikiToolBase
