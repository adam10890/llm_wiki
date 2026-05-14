"""
Quick regression test: wiki_query and friends accept synonym keys.

Run from the plugin root with:
    python tests/test_alias_args.py
"""
from __future__ import annotations

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.join(os.path.dirname(_HERE), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

# Ensure no SHARED_BRAIN env contamination
os.environ.pop("SHARED_BRAIN", None)

from wiki_query import WikiQuery  # type: ignore  # noqa: E402
from wiki_ingest import WikiIngest  # type: ignore  # noqa: E402
from wiki_lint import WikiLint  # type: ignore  # noqa: E402
from wiki_commit import WikiCommit  # type: ignore  # noqa: E402


class FakeAgent:
    id = "agent_zero"
    data = {}


def make_tool(cls, args):
    t = cls.__new__(cls)
    t.agent = FakeAgent()
    t.args = args
    return t


def assert_eq(label, got, want):
    status = "OK " if got == want else "FAIL"
    print(f"[{status}] {label}: got={got!r} want={want!r}")
    return got == want


def main() -> int:
    failures = 0

    # 1. wiki_query — empty args should produce the new helpful error
    t = make_tool(WikiQuery, {})
    res = asyncio.run(t.execute())
    if "Expected JSON" not in (res.message or ""):
        print(f"[FAIL] wiki_query empty error message missing schema. Got:\n{res.message}")
        failures += 1
    else:
        print("[OK ] wiki_query empty-arg error includes schema example")

    # 2. wiki_query — `query` alias should be accepted (will fail later on
    #    no vault, but we can confirm it got past the question check by
    #    looking for a non-"Please provide a question" message)
    t = make_tool(WikiQuery, {"query": "hello world"})
    res = asyncio.run(t.execute())
    if "Please provide a question" in (res.message or ""):
        print(f"[FAIL] wiki_query did not accept `query` alias")
        failures += 1
    else:
        print("[OK ] wiki_query accepts `query` as alias for `question`")

    # 3. wiki_query — `q` alias
    t = make_tool(WikiQuery, {"q": "hi"})
    res = asyncio.run(t.execute())
    if "Please provide a question" in (res.message or ""):
        print(f"[FAIL] wiki_query did not accept `q` alias")
        failures += 1
    else:
        print("[OK ] wiki_query accepts `q` as alias")

    # 4. wiki_query — singular `wiki` arg should be coerced
    t = make_tool(WikiQuery, {"question": "hi", "wiki": "commons"})
    res = asyncio.run(t.execute())
    # We expect the tool to bail later with "No SharedBrain vault" or
    # "Unknown wikis", but not "Please provide a question"
    if "Please provide a question" in (res.message or ""):
        print(f"[FAIL] wiki_query did not survive `wiki` singular alias")
        failures += 1
    else:
        print("[OK ] wiki_query accepts `wiki` (singular) as alias")

    # 5. wiki_lint — `name` alias for wiki target
    t = make_tool(WikiLint, {"name": "commons"})
    res = asyncio.run(t.execute())
    print(f"[INFO] wiki_lint with name= alias produced: {(res.message or '')[:80]}...")

    # 6. wiki_commit — `msg` alias
    t = make_tool(WikiCommit, {"wiki": "commons", "msg": "test"})
    res = asyncio.run(t.execute())
    print(f"[INFO] wiki_commit with msg= alias produced: {(res.message or '')[:80]}...")

    print("")
    print(f"Failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
