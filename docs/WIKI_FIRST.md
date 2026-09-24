# Wiki before every other search

## Policy

For every connected agent, refresh relevant SharedBrain knowledge before EACH
search outside the wiki, including web, code, files, databases, connectors and
other memories. Read permitted onboarding instructions, query relevant readable
wikis, and read the returned pages before proceeding. No parallel outside search.
Keep a task-local note of consulted pages, retrieval time, coverage and gaps.
Use outside sources for gaps or required freshness/source verification only.
Never put private wiki content into an external query.

The cached catalog is orientation, not proof of retrieval. Re-query before each
subsequent outside search. Wiki discovery and retrieval do not recursively
require another lookup. A bounded or truncated result does not establish that
the whole vault lacks information; consult relevant indexes/pages as permitted.

If the wiki is unreachable or access is denied, report the blocker and pause
other searches unless the user explicitly permits an exception. A successful
lookup with no relevant content permits a search to fill that gap.

Delegated tasks follow the same rule. Pass the requesting agent's identity and
permitted wiki scope to the librarian; do not use its identity to obtain data
the requester cannot read. Follow current registry grants; never expand grants
as part of enabling this policy.

## Loading the policy in each harness

The canonical runtime protocol belongs to the live SharedBrain vault. This
repository ships its onboarding scaffold at
`wikis/onboarding/wiki/_start_here.md`. Merge its search-order section into the
live vault's corresponding page, preserving existing instructions and content.

Agent Zero receives the rule via
`extensions/python/system_prompt/_40_wiki_context.py`, `skills/SKILL.md` and
`prompts/agent.system.tool.wiki_query.md`. Deploy the updated plugin and start
a fresh agent instance to avoid its conversation-lifetime prompt cache.

For Codex, Claude Code, Hermes, OpenClaw, Cowork and any other consumer, inventory
the installed harnesses and configure EACH active startup instruction to read
the permitted live onboarding page before any other search. Do not assume a
file named `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `hermes.md` or `openclaw.md`
loads merely because it exists in the vault's `agents/` directory. Verify the
actual loader in that installation. The README's sibling Claude Code companion
is not present in this checkout and must be updated in its own workspace.

Use this compact instruction in each active entry point, resolving the real
vault path for that harness:

> Before EVERY non-wiki search, read the permitted SharedBrain onboarding
> instructions and refresh task-relevant wiki knowledge. Read the results
> before searching elsewhere; no parallel outside search. Record consulted
> pages, retrieval time and gaps in task-local context. A cached catalog or
> previous answer is insufficient. Use other sources only for gaps or required
> freshness verification. Honor registry grants, including during delegation,
> and never expose private wiki content in external queries. On unavailable or
> denied access, report the blocker and pause other searches unless the user
> explicitly permits an exception. Wiki discovery/retrieval is not recursive.

## Verify each installed harness

Use a fixture vault and record actual tool-call order, not an agent's promise.

1. Ask for a repository or web search without mentioning the wiki. A completed
   wiki lookup and reading its result must precede the other search.
2. Change a relevant fixture page between two searches in the same task. The
   second search must use a fresh wiki read that observes the change.
3. Supply sufficient wiki coverage: avoid redundant outside searches. Supply a
   documented gap or freshness need: search after the lookup completes.
4. Make the wiki unavailable or deny the requested scope: report the condition
   and do not search elsewhere without an explicit user exception.
5. Delegate a lookup: verify the requester scope is preserved and the librarian
   finishes before any outside search. Include a read-only caller case.

This change supplies instructions, not a cross-harness tool interceptor. It
does not install other harnesses' entry points, deploy the local vault, prove
live compliance, or enforce caller-scope propagation in code. Those properties
require verification in each real runtime; record untested consumers as pending.
