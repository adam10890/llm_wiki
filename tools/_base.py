"""
_base — shared base class for all llm_wiki tools.

Centralises fallback imports, config / agent-id resolution, and common helpers
so every tool doesn't duplicate the same boilerplate.
"""
import os
import sys
import logging

__all__ = ["WikiToolBase", "WikiRegistry", "Tool", "Response", "files"]

_log = logging.getLogger("llm_wiki")

# --- Fallback for Agent Zero helpers ---------------------------------
try:
    from helpers.tool import Tool, Response
except Exception:
    class Tool:
        """Fallback Tool base when running outside Agent Zero runtime."""

    class Response:
        """Fallback Response when running outside Agent Zero runtime."""
        def __init__(self, message="", break_loop=False):
            self.message = message
            self.break_loop = break_loop

try:
    from helpers import files
except Exception:
    class _FilesFallback:
        @staticmethod
        def read_file(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

    files = _FilesFallback()

# --- Fallback for wiki_registry (same pattern used by every tool) ---
try:
    from .wiki_registry import WikiRegistry
except Exception:
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    from wiki_registry import WikiRegistry  # type: ignore


class WikiToolBase(Tool):
    """Base class for all llm_wiki tools.  DRY for config / identity / paths."""

    # ------------------------------------------------------------------
    # Agent identity
    # ------------------------------------------------------------------
    def _get_agent_id(self):
        # 1. Config override wins
        try:
            from helpers.plugins import get_plugin_config

            cfg = get_plugin_config("llm_wiki", self.agent) or {}
            forced = cfg.get("agent_id", "")
            if forced:
                return forced
        except Exception:
            pass
        # 2. Try agent attributes
        for attr in ("id", "name", "agent_id"):
            v = getattr(self.agent, attr, None)
            if isinstance(v, str) and v:
                return v.lower().replace(" ", "_")
        # 3. Default
        return "agent_zero"

    # ------------------------------------------------------------------
    # Plugin config (logs once if helpers.plugins is unreachable)
    # ------------------------------------------------------------------
    _config_warn_logged = False

    def _get_config(self):
        try:
            from helpers.plugins import get_plugin_config

            return get_plugin_config("llm_wiki", self.agent) or {}
        except Exception as exc:
            if not WikiToolBase._config_warn_logged:
                _log.debug("helpers.plugins unavailable, using empty config: %s", exc)
                WikiToolBase._config_warn_logged = True
            return {}

    # ------------------------------------------------------------------
    # Project directory resolution
    # ------------------------------------------------------------------
    def _get_project_dir(self):
        try:
            project = getattr(self.agent, "project", None)
            if project and hasattr(project, "path"):
                return project.path
            data = getattr(self.agent, "data", {})
            if isinstance(data, dict) and "project_path" in data:
                return data["project_path"]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Config key helper (searches wiki / lint / query sections)
    # ------------------------------------------------------------------
    def _cfg(self, cfg_dict, key, default):
        for section in ("wiki", "lint", "query"):
            if isinstance(cfg_dict.get(section), dict) and key in cfg_dict[section]:
                return cfg_dict[section][key]
        return cfg_dict.get(key, default)
