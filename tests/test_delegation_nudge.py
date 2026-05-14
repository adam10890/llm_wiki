"""
Regression test: _40_wiki_context.py renders the right block per profile.

- For `wiki_librarian` profile → block contains the canonical wiki_query
  JSON shape (`{ "tool_name": "wiki_query", ... }`).
- For every other profile → block contains the delegation policy with the
  `call_subordinate` JSON shape pointing at `wiki_librarian`.
- For both → block contains the SharedBrain header / wiki listing.

Runs in-process; does not require a live container.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXT = os.path.join(
    os.path.dirname(_HERE),
    "extensions",
    "python",
    "system_prompt",
)
if _EXT not in sys.path:
    sys.path.insert(0, _EXT)

# Stub helpers.extension so the module imports outside Agent Zero.
import types

if "helpers" not in sys.modules:
    helpers_pkg = types.ModuleType("helpers")
    sys.modules["helpers"] = helpers_pkg
if "helpers.extension" not in sys.modules:
    ext_mod = types.ModuleType("helpers.extension")

    class Extension:  # minimal stub
        def __init__(self, agent=None):
            self.agent = agent

    ext_mod.Extension = Extension
    sys.modules["helpers.extension"] = ext_mod

import importlib.util

spec = importlib.util.spec_from_file_location(
    "_40_wiki_context",
    os.path.join(_EXT, "_40_wiki_context.py"),
)
assert spec is not None
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

LLMWikiContext = mod.LLMWikiContext


class FakeConfig:
    def __init__(self, profile: str = ""):
        self.profile = profile


class FakeAgent:
    def __init__(self, profile: str = ""):
        self.id = "agent_zero"
        self.config = FakeConfig(profile=profile)


def make_data():
    return {
        "configured": True,
        "ok": True,
        "vault_root": "/data/SharedBrain",
        "agent_id": "agent_zero",
        "git": {"auto_commit": True},
        "wikis": [
            {
                "name": "commons",
                "scope": "shared",
                "sensitivity": "shared",
                "can_read": True,
                "can_write": True,
                "exists": True,
                "default": True,
                "pages": 15,
            },
            {
                "name": "general",
                "scope": "shared",
                "sensitivity": "shared",
                "can_read": True,
                "can_write": True,
                "exists": True,
                "default": False,
                "pages": 0,
            },
        ],
        "stats": {"total_pages": 15},
    }


def assert_contains(label, text, needle):
    ok = needle in text
    print(f"[{'OK ' if ok else 'FAIL'}] {label}: {'has' if ok else 'MISSING'} '{needle[:60]}...'")
    return ok


def assert_not_contains(label, text, needle):
    ok = needle not in text
    print(f"[{'OK ' if ok else 'FAIL'}] {label}: {'absent' if ok else 'PRESENT (unexpected)'} '{needle[:60]}...'")
    return ok


def main() -> int:
    failures = 0

    # --- Test 1: librarian profile gets the tool reference ----------------
    ext = LLMWikiContext.__new__(LLMWikiContext)
    ext.agent = FakeAgent(profile="wiki_librarian")
    block_lib = ext._render_block(make_data(), is_librarian=True)

    if not assert_contains("librarian: wiki_query JSON example",
                           block_lib,
                           '"tool_name": "wiki_query"'):
        failures += 1
    if not assert_contains("librarian: wiki_ingest JSON example",
                           block_lib,
                           '"tool_name": "wiki_ingest"'):
        failures += 1
    if not assert_not_contains("librarian: no delegation block",
                               block_lib,
                               "Wiki Delegation Policy"):
        failures += 1
    if not assert_not_contains("librarian: no call_subordinate to self",
                               block_lib,
                               '"profile": "wiki_librarian"'):
        failures += 1

    # --- Test 2: non-librarian profile gets the delegation nudge ----------
    ext2 = LLMWikiContext.__new__(LLMWikiContext)
    ext2.agent = FakeAgent(profile="developer")
    block_dev = ext2._render_block(make_data(), is_librarian=False)

    if not assert_contains("developer: delegation header",
                           block_dev,
                           "### Wiki Delegation Policy"):
        failures += 1
    if not assert_contains("developer: call_subordinate JSON shape",
                           block_dev,
                           '"tool_name": "call_subordinate"'):
        failures += 1
    if not assert_contains("developer: target profile is wiki_librarian",
                           block_dev,
                           '"profile": "wiki_librarian"'):
        failures += 1
    if not assert_not_contains("developer: NO direct wiki_query example",
                               block_dev,
                               '"tool_name": "wiki_query"'):
        failures += 1

    # --- Test 3: both flavors include the vault summary -------------------
    if not assert_contains("both: SharedBrain header (librarian)",
                           block_lib,
                           "LLM Wiki — SharedBrain"):
        failures += 1
    if not assert_contains("both: SharedBrain header (developer)",
                           block_dev,
                           "LLM Wiki — SharedBrain"):
        failures += 1
    if not assert_contains("both: commons listed (developer)",
                           block_dev,
                           "`commons`"):
        failures += 1

    # --- Test 4: librarian alias detection --------------------------------
    for alias in ("wiki_librarian", "WIKI_LIBRARIAN", "Librarian", "wiki-librarian"):
        ext3 = LLMWikiContext.__new__(LLMWikiContext)
        ext3.agent = FakeAgent(profile=alias)
        prof = ext3._resolve_profile()
        is_lib = prof.lower() in LLMWikiContext._LIBRARIAN_PROFILES
        if not is_lib:
            print(f"[FAIL] alias '{alias}' was not recognized as librarian")
            failures += 1
        else:
            print(f"[OK ] alias '{alias}' is recognized as librarian")

    print("")
    print(f"Failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
