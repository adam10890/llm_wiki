"""
/api/wiki_status — JSON endpoint backing the WebUI dashboard.

Returns the structured vault summary produced by helpers.wiki_status.
Accepts optional input:
  - agent_id: override (defaults to plugin config.agent_id or "agent_zero")
  - refresh: if truthy, bypass the in-process cache
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict

try:
    from helpers.api import ApiHandler
    from flask import Request
except Exception:  # pragma: no cover - runtime fallback
    class ApiHandler:  # type: ignore
        pass

    class Request:  # type: ignore
        pass


def _load_status_builder():
    """Resolve helpers.wiki_status via either package path or sibling import."""
    try:
        from usr.plugins.llm_wiki.helpers.wiki_status import (  # type: ignore
            build_wiki_status, clear_cache,
        )
        return build_wiki_status, clear_cache
    except Exception:
        pass
    helpers_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "helpers",
    )
    if helpers_dir not in sys.path:
        sys.path.insert(0, helpers_dir)
    from wiki_status import build_wiki_status, clear_cache  # type: ignore
    return build_wiki_status, clear_cache


def _resolve_agent_id(override: str) -> str:
    if override:
        return override
    # Fall back to plugin config (same source the tools read from)
    plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg_json = os.path.join(plugin_dir, "config.json")
    if os.path.isfile(cfg_json):
        try:
            import json
            with open(cfg_json, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            aid = data.get("agent_id")
            if isinstance(aid, str) and aid:
                return aid
        except Exception:
            pass
    return "agent_zero"


class WikiStatus(ApiHandler):
    """Return the current SharedBrain vault status as JSON."""

    async def process(self, input: Dict[str, Any], request: Request) -> Dict[str, Any]:
        try:
            build_wiki_status, clear_cache = _load_status_builder()
        except Exception as e:
            return {
                "success": False,
                "error": f"failed to import wiki_status helper: {e}",
            }

        agent_id = _resolve_agent_id(str((input or {}).get("agent_id", "") or ""))
        refresh = bool((input or {}).get("refresh", False))
        if refresh:
            try:
                clear_cache()
            except Exception:
                pass

        try:
            data = build_wiki_status(
                agent_id=agent_id,
                include_git_log=True,
                use_cache=not refresh,
            )
        except Exception as e:
            return {"success": False, "error": f"build_wiki_status crashed: {e}"}

        return {"success": True, "status": data}
