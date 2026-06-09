# DOX contract - llm_wiki/extensions

## Purpose

Agent Zero extension hooks for prompt/context behavior.

## Ownership

- Extensions integrate SharedBrain context with Agent Zero.
- Tools/registry own permissions and operation behavior.

## Local Contracts

- Hooks must not read or inject private wiki data without grant checks.

## Work Guidance

- Keep prompt/context injection compact.

## Verification

- Run `python -m py_compile` on touched extension files.

## Child DOX Index

No child AGENTS.md files yet.
