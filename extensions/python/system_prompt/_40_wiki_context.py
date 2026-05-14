"""
LLM Wiki — system_prompt extension.

Injects a compact SharedBrain summary into the agent's system prompt so the
agent always knows, from turn 0:
  - The vault root
  - Which wikis exist
  - Its own read/write grants per wiki
  - Git auto-commit state

The summary is cached per-agent for the lifetime of the agent instance so we
never query the vault twice for the same conversation. A silent no-op if
SharedBrain is not configured (the agent continues without a wiki block).
"""
from __future__ import annotations

import os
import sys
from typing import Any

try:
    from helpers.extension import Extension
except ImportError:  # pragma: no cover - A0 path variance
    from python.helpers.extension import Extension  # type: ignore

try:
    from helpers import plugins as _a0_plugins  # type: ignore
except Exception:  # pragma: no cover
    _a0_plugins = None  # type: ignore


_PLUGIN_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_HELPERS_DIR = os.path.join(_PLUGIN_DIR, "helpers")


def _load_status_builder():
    """Resolve build_wiki_status under either package or sibling path."""
    try:
        from usr.plugins.llm_wiki.helpers.wiki_status import (  # type: ignore
            build_wiki_status,
        )
        return build_wiki_status
    except Exception:
        pass
    if _HELPERS_DIR not in sys.path:
        sys.path.insert(0, _HELPERS_DIR)
    from wiki_status import build_wiki_status  # type: ignore
    return build_wiki_status


class LLMWikiContext(Extension):
    """Inject SharedBrain wiki summary into the system prompt."""

    _DATA_KEY = "_llm_wiki_prompt"

    # Profile names that ARE the wiki librarian itself (or its aliases).
    # When the active profile is one of these, we show the full tool reference
    # because the librarian needs the canonical JSON shapes for the wiki_*
    # tools. For every OTHER profile we show a delegation nudge instead.
    _LIBRARIAN_PROFILES = frozenset({
        "wiki_librarian",
        "wiki-librarian",
        "wikilibrarian",
        "librarian",
    })

    async def execute(
        self,
        system_prompt: list[str] = [],
        **kwargs: Any,
    ) -> None:
        # Skip if the plugin is disabled for this agent/project
        agent_id = self._resolve_agent_id()
        profile = self._resolve_profile()
        is_librarian = profile.lower() in self._LIBRARIAN_PROFILES

        # Cache per-(profile, agent_id). If the same Agent instance is reused
        # under a different profile (rare but possible), we want a fresh block.
        cache_key = f"{self._DATA_KEY}::{profile}::{agent_id}"
        try:
            cached = self.agent.get_data(cache_key)
        except Exception:
            cached = None
        if cached:
            system_prompt.append(cached)
            return

        try:
            build_wiki_status = _load_status_builder()
            data = build_wiki_status(agent_id=agent_id, include_git_log=False)
        except Exception:
            return  # Silent: never break the system prompt loop

        if not data or not data.get("configured") or not data.get("ok"):
            return

        block = self._render_block(data, is_librarian=is_librarian)
        if not block:
            return

        try:
            self.agent.set_data(cache_key, block)
        except Exception:
            pass
        system_prompt.append(block)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _resolve_agent_id(self) -> str:
        # 1. Plugin config override (same precedence as WikiToolBase)
        if _a0_plugins is not None:
            try:
                cfg = _a0_plugins.get_plugin_config("llm_wiki", self.agent) or {}
                aid = cfg.get("agent_id")
                if isinstance(aid, str) and aid:
                    return aid
            except Exception:
                pass
        # 2. Agent attributes
        for attr in ("id", "name", "agent_id"):
            v = getattr(self.agent, attr, None)
            if isinstance(v, str) and v:
                return v.lower().replace(" ", "_")
        return "agent_zero"

    def _resolve_profile(self) -> str:
        """Return the active agent profile name (e.g. 'developer', 'agent0',
        'wiki_librarian'). Defaults to empty string if unavailable — callers
        should treat empty as 'unknown / not the librarian'."""
        try:
            cfg = getattr(self.agent, "config", None)
            prof = getattr(cfg, "profile", "")
            if isinstance(prof, str) and prof:
                return prof
        except Exception:
            pass
        return ""

    def _render_block(self, data: dict, is_librarian: bool = False) -> str:
        wikis = data.get("wikis", [])
        writable = [w for w in wikis if w.get("can_write")]
        readable = [w for w in wikis if w.get("can_read")]
        default = next((w for w in wikis if w.get("default")), None)

        if not wikis:
            return ""

        lines: list[str] = [
            "## 📚 LLM Wiki — SharedBrain",
            (
                f"**Vault:** `{data.get('vault_root', '')}`  ·  "
                f"**You are:** `{data.get('agent_id', '')}`  ·  "
                f"**Git auto-commit:** "
                f"{'on' if data.get('git', {}).get('auto_commit') else 'off'}"
            ),
            "",
        ]

        if default:
            lines.append(
                f"**Default ingest target:** `{default['name']}`  "
                f"({default.get('scope', '')}, {default.get('pages', 0)} pages)"
            )
            lines.append("")

        lines.append("**Wikis you can access:**")
        max_rows = 12
        for w in wikis[:max_rows]:
            if not w.get("can_read"):
                continue
            perms = ("RW" if w.get("can_write") else "R-")
            star = " ★" if w.get("default") else ""
            exists = "" if w.get("exists") else " _(missing)_"
            lines.append(
                f"- `{w['name']}` [{perms}]{star}  —  "
                f"{w.get('scope', '?')}/{w.get('sensitivity', '?')}, "
                f"{w.get('pages', 0)} pages{exists}"
            )
        if len(wikis) > max_rows:
            lines.append(f"- _…and {len(wikis) - max_rows} more_")

        lines.append("")
        lines.append(
            f"**Stats:** {len(readable)} readable / {len(writable)} writable "
            f"/ {data.get('stats', {}).get('total_pages', 0)} total pages."
        )
        lines.append("")

        if is_librarian:
            lines.extend(self._librarian_tool_reference())
        else:
            lines.extend(self._delegation_nudge())

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Block flavors
    # ------------------------------------------------------------------
    def _librarian_tool_reference(self) -> list[str]:
        """Full canonical JSON quick-reference for the wiki_librarian profile.
        The librarian is the ONE place where the wiki_* tools should be called
        directly, so it gets the full schemas inline."""
        return [
            "**Wiki tool quick reference (canonical JSON shapes):**",
            "",
            "```json",
            '{ "tool_name": "wiki_list", "tool_args": { "verbose": false } }',
            "```",
            "```json",
            '{ "tool_name": "wiki_query", "tool_args": '
            '{ "question": "<your question>", "wikis": ["commons"] } }',
            "```",
            "```json",
            '{ "tool_name": "wiki_ingest", "tool_args": '
            '{ "source_path": "/data/SharedBrain/wikis/<wiki>/wiki_raw/<file>.md", '
            '"wiki": "<wiki-name>" } }',
            "```",
            "```json",
            '{ "tool_name": "wiki_lint", "tool_args": '
            '{ "wiki": "<wiki-name>", "scope": "full", "fix": false } }',
            "```",
            "```json",
            '{ "tool_name": "wiki_commit", "tool_args": '
            '{ "wiki": "<wiki-name>", "op": "INGEST|QUERY|LINT|WRITE", '
            '"message": "<commit subject>" } }',
            "```",
            "",
            "**Critical:** `wiki_query` requires `question` (not `query`). "
            "All wiki tools accept `wiki` (string) for a single target. "
            "Always answer knowledge questions by calling `wiki_query` "
            "**first** \u2014 do NOT answer from training data.",
        ]

    def _delegation_nudge(self) -> list[str]:
        """Universal delegation nudge shown to every NON-librarian profile.

        Tells the active profile (developer, researcher, agent0, etc.) to
        offload wiki work to the dedicated `wiki_librarian` sub-agent via
        `call_subordinate`. This preserves the main context window and
        lets the librarian apply citation + grant discipline.
        """
        return [
            "### Wiki Delegation Policy",
            "",
            "When the user asks a **knowledge question**, a **wiki search**, an "
            "**ingestion**, or any other wiki-related task \u2014 do NOT call the "
            "`wiki_*` tools yourself. Instead, **delegate to the dedicated "
            "`wiki_librarian` sub-agent** via `call_subordinate`. The librarian:",
            "",
            "- has full read/write grants on every wiki (no permission friction),",
            "- preserves your context window by doing the wiki lookup in its own session,",
            "- enforces citation discipline (`commons::[[page]]` namespaced backlinks),",
            "- returns a structured `Answer / Citations / Coverage / Suggested Ingestion` payload.",
            "",
            "**Trigger phrases (English & Hebrew, non-exhaustive):**",
            "- \"what do we know about\", \"look up\", \"search the wiki\", \"second brain\","
            " \"knowledge base\", \"ingest\", \"compile this into\", \"add to wiki\","
            " \"lint the wiki\", \"commit the wiki\"",
            "- \u05d4\u05d0\u05dd \u05d9\u05e9 \u05d1\u05d5\u05d9\u05e7\u05d9, \u05de\u05d4 \u05d0\u05e0\u05d7\u05e0\u05d5 \u05d9\u05d5\u05d3\u05e2\u05d9\u05dd, \u05ea\u05d0\u05e8\u05d2\u05df, \u05ea\u05dc\u05e7\u05d8, \u05ea\u05e8\u05d0\u05d4 \u05de\u05d4 \u05db\u05ea\u05d5\u05d1, \u05ea\u05d7\u05e4\u05e9 \u05d1\u05d5\u05d9\u05e7\u05d9, \u05d4\u05d5\u05e1\u05e3 \u05dc\u05d1\u05e8\u05d9\u05df \u05d4\u05de\u05e9\u05d5\u05ea\u05e3",
            "",
            "**Exact JSON shape:**",
            "",
            "```json",
            "{",
            '  "tool_name": "call_subordinate",',
            '  "tool_args": {',
            '    "profile": "wiki_librarian",',
            '    "message": "<verbatim user question, plus any context the librarian needs>",',
            '    "reset": true',
            "  }",
            "}",
            "```",
            "",
            "**Set `reset: true` on the FIRST librarian call** of each task; use "
            "`reset: false` for follow-ups in the same task. Pass the question in "
            "the user's original language (typically Hebrew or English).",
            "",
            "**Direct `wiki_*` tool calls are reserved for the librarian profile.** "
            "If you absolutely must run one yourself (e.g. quick `wiki_list` for "
            "your own orientation), use it sparingly and never for end-user "
            "queries that the librarian could answer with proper citations.",
        ]
