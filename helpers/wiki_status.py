"""
wiki_status — shared vault summary builder.

Used by both:
  - api/wiki_status.py       (JSON endpoint powering the WebUI dashboard)
  - extensions/python/system_prompt/_40_wiki_context.py (agent prompt inject)

Produces a single, JSON-serializable dict describing the SharedBrain vault,
its registered wikis, the current agent's grants, git state, and recent
activity. Heavy work (page counts, git log parsing) is done once per process
and cached with a short TTL so repeated calls stay cheap.
"""
from __future__ import annotations

import os
import sys
import time
import json
import subprocess
from typing import Any, Dict, List, Optional

__all__ = ["build_wiki_status", "clear_cache"]

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS_DIR = os.path.join(_PLUGIN_DIR, "tools")


def _import_registry():
    """Import WikiRegistry without requiring the A0 runtime package path."""
    try:
        from usr.plugins.llm_wiki.tools.wiki_registry import WikiRegistry  # type: ignore
        return WikiRegistry
    except Exception:
        pass
    if _TOOLS_DIR not in sys.path:
        sys.path.insert(0, _TOOLS_DIR)
    from wiki_registry import WikiRegistry  # type: ignore
    return WikiRegistry


def _load_plugin_config() -> Dict[str, Any]:
    """Load config.json merged onto default_config.yaml. Stdlib only."""
    cfg: Dict[str, Any] = {}

    default_cfg = os.path.join(_PLUGIN_DIR, "default_config.yaml")
    if os.path.isfile(default_cfg):
        try:
            import yaml  # type: ignore
            with open(default_cfg, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}

    user_cfg = os.path.join(_PLUGIN_DIR, "config.json")
    if os.path.isfile(user_cfg):
        try:
            with open(user_cfg, "r", encoding="utf-8") as f:
                user_data = json.load(f) or {}
            cfg = _deep_merge(cfg, user_data)
        except Exception:
            pass

    return cfg


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _count_pages(wiki_dir: str) -> int:
    if not os.path.isdir(wiki_dir):
        return 0
    excluded = {"index.md", "log.md"}
    n = 0
    for root, _, files in os.walk(wiki_dir):
        for f in files:
            if f.endswith(".md") and f not in excluded:
                n += 1
    return n


def _git_log(vault_root: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Return the last N commits in the vault repo. Silent on any failure."""
    if not os.path.isdir(os.path.join(vault_root, ".git")):
        return []
    try:
        fmt = "%H%x1f%h%x1f%an%x1f%ad%x1f%s"
        rc = subprocess.run(
            ["git", "-C", vault_root, "log", f"-n{limit}",
             f"--pretty=format:{fmt}", "--date=iso-strict"],
            capture_output=True, text=True, timeout=5,
        )
        if rc.returncode != 0:
            return []
        out: List[Dict[str, Any]] = []
        for line in rc.stdout.strip().splitlines():
            parts = line.split("\x1f")
            if len(parts) != 5:
                continue
            sha, short, author, date, subject = parts
            out.append({
                "sha": sha,
                "short": short,
                "author": author,
                "date": date,
                "subject": subject,
            })
        return out
    except Exception:
        return []


def _last_log_entry(log_path: str) -> Optional[str]:
    """Return the most recent non-empty log entry header, if any."""
    if not os.path.isfile(log_path):
        return None
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            s = line.strip()
            if s.startswith("## "):
                return s[3:]
        return None
    except Exception:
        return None


# Simple per-process cache. Invalidate with clear_cache() or after TTL.
_CACHE: Dict[str, Any] = {"ts": 0.0, "agent_id": "", "data": None}
_CACHE_TTL_SEC = 15.0


def clear_cache() -> None:
    """Invalidate the module-level cache. Safe to call any time."""
    _CACHE["ts"] = 0.0
    _CACHE["agent_id"] = ""
    _CACHE["data"] = None


def build_wiki_status(
    agent_id: str = "agent_zero",
    include_git_log: bool = True,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Return a JSON-serializable dict describing vault + wikis + grants + git.

    Shape::

        {
          "ok": bool,
          "configured": bool,
          "error": str | None,
          "vault_root": str,
          "agent_id": str,
          "grants": {"read": [...], "write": [...]},
          "stats": {"total": int, "readable": int, "writable": int,
                     "total_pages": int, "missing": int},
          "git": {"is_repo": bool, "auto_commit": bool, "log": [...]},
          "wikis": [
             {"name": str, "title": str, "scope": str, "sensitivity": str,
              "path": str, "exists": bool, "pages": int, "default": bool,
              "can_read": bool, "can_write": bool,
              "last_log_entry": str | None}
          ],
          "generated_at": float,
        }
    """
    now = time.time()
    if (
        use_cache
        and _CACHE["data"] is not None
        and _CACHE["agent_id"] == agent_id
        and (now - _CACHE["ts"]) < _CACHE_TTL_SEC
    ):
        return _CACHE["data"]

    result: Dict[str, Any] = {
        "ok": False,
        "configured": False,
        "error": None,
        "vault_root": "",
        "agent_id": agent_id,
        "grants": {"read": [], "write": []},
        "stats": {"total": 0, "readable": 0, "writable": 0,
                  "total_pages": 0, "missing": 0},
        "git": {"is_repo": False, "auto_commit": False, "log": []},
        "wikis": [],
        "generated_at": now,
    }

    try:
        cfg = _load_plugin_config()
        WikiRegistry = _import_registry()
        registry = WikiRegistry.from_config(plugin_config=cfg, agent_id=agent_id)

        if registry is None:
            result["error"] = (
                "No SharedBrain vault configured. Set shared_vault.path in "
                "config.json or default_config.yaml, or run initialize.py."
            )
            if use_cache:
                _CACHE["ts"] = now
                _CACHE["agent_id"] = agent_id
                _CACHE["data"] = result
            return result

        result["configured"] = True
        result["vault_root"] = registry.vault_root
        grants = registry._grants()
        result["grants"] = {
            "read": list(grants.get("read", [])),
            "write": list(grants.get("write", [])),
        }

        gcfg = registry.git_config()
        result["git"]["auto_commit"] = bool(gcfg.get("auto_commit", False))
        result["git"]["is_repo"] = registry.is_git_repo()
        if include_git_log and result["git"]["is_repo"]:
            result["git"]["log"] = _git_log(registry.vault_root, limit=5)

        total_pages = 0
        missing = 0
        wikis = registry.list_wikis()
        wiki_out: List[Dict[str, Any]] = []
        for w in wikis:
            pages = _count_pages(os.path.join(w["path"], "wiki")) if w["exists"] else 0
            total_pages += pages
            if not w["exists"]:
                missing += 1
            last_entry = None
            if w["exists"]:
                last_entry = _last_log_entry(os.path.join(w["path"], "wiki", "log.md"))
            wiki_out.append({
                "name": w["name"],
                "title": w.get("title", w["name"]),
                "scope": w["scope"],
                "sensitivity": w["sensitivity"],
                "path": w["path"],
                "exists": bool(w["exists"]),
                "pages": pages,
                "default": bool(w["default_for_ingest"]),
                "can_read": registry.can_read(w["name"]),
                "can_write": registry.can_write(w["name"]),
                "last_log_entry": last_entry,
                "description": w.get("description", ""),
                "tags": list(w.get("tags", []) or []),
            })

        result["wikis"] = wiki_out
        result["stats"] = {
            "total": len(wikis),
            "readable": sum(1 for w in wiki_out if w["can_read"]),
            "writable": sum(1 for w in wiki_out if w["can_write"]),
            "total_pages": total_pages,
            "missing": missing,
        }
        result["ok"] = True

    except Exception as e:
        result["error"] = f"status build failed: {e}"

    if use_cache:
        _CACHE["ts"] = now
        _CACHE["agent_id"] = agent_id
        _CACHE["data"] = result

    return result
