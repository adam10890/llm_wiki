# DOX contract — llm_wiki

## Purpose

Agent Zero plugin for SharedBrain: a multi-wiki knowledge base with registry
grants, sensitivity labels, cross-wiki queries, ingest/lint/register/commit
tools, and a companion Claude Code plugin.

## Ownership

- This plugin is the maintained SharedBrain implementation for Agent Zero.
- The canonical permission source is SharedBrain `registry.yaml`.
- Tools enforce grants before reads/writes. Do not bypass registry checks.
- Keep A0 plugin behavior and Claude Code companion behavior aligned when a
  command contract changes.

## Local Contracts

- `tools/wiki_registry.py` is the registry and grants contract.
- `tools/wiki_ingest.py`, `wiki_query.py`, `wiki_lint.py`, `wiki_list.py`,
  `wiki_register.py`, and `wiki_commit.py` are the six core operations.
- Prompt files in `prompts/` must stay aligned with tool names and behavior.
- `shared_vault.enabled: true` multi-wiki mode and legacy single-wiki mode must
  both keep working unless the user explicitly accepts a migration.
- `wiki_register` may create wiki structure and append registry entries, but
  must not auto-grant access.

## Work Guidance

- Read the parent Agent Zero workspace contract before wiki work when this
  plugin is installed in a live Agent Zero tree.
- For SharedBrain vault edits, follow the vault's own agents protocol rather
  than this plugin contract.
- For plugin code edits, preserve dual-mode behavior and access checks.
- If adding portable access for Hermes/OC/meta, prefer a small MCP/HTTP door in
  front of existing registry logic rather than a new parallel policy store.

## Verification

- Compile touched Python files.
- Run plugin tests when modifying argument parsing, registry behavior, or
  prompt/tool contracts.
- Smoke-test with `execute.py` when vault discovery or grants behavior changes.

## Child DOX Index

- `tools/AGENTS.md` — registry, ingest, query, lint, list, register, and commit
  tool contracts.
- `helpers/AGENTS.md` — shared helper code for web/API/plugin support.
- `api/AGENTS.md` — web/API wrappers for wiki operations.
- `extensions/AGENTS.md` — Agent Zero prompt/context hooks.
- `prompts/AGENTS.md` — tool prompt guidance.
- `skills/AGENTS.md` — natural-language SharedBrain skill guidance.
- `tests/AGENTS.md` — registry/tool behavior tests.
- `webui/AGENTS.md` — plugin UI.
- `docs/AGENTS.md` — SharedBrain/plugin documentation.
