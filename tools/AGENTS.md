# DOX contract - llm_wiki/tools

## Purpose

The six core SharedBrain operations: registry/list, ingest, query, lint,
register, and commit.

## Ownership

- `wiki_registry.py` owns registry parsing, grants, sensitivity, and git helper
  behavior.
- Tools enforce grants before reads/writes.

## Local Contracts

- Multi-wiki mode and legacy single-wiki mode must both keep working unless a
  migration is explicitly accepted.
- `wiki_register` must not auto-grant access.
- Cross-wiki references use namespaced syntax.

## Work Guidance

- Keep access checks close to operation entry points.
- Do not read Agent Zero's private `agent_self` wiki.

## Verification

- Run plugin tests for registry/tool changes.
- Run `python -m py_compile` on touched tool files.

## Child DOX Index

No child AGENTS.md files yet.
