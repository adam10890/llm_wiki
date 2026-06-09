# DOX contract - llm_wiki/helpers

## Purpose

Shared helper code for web/API/plugin support around SharedBrain behavior.

## Ownership

- Helpers support tools and UI but must not bypass registry grants.

## Local Contracts

- Reuse registry logic from tools rather than creating a parallel policy store.

## Work Guidance

- Keep helper functions small and dependency-light.

## Verification

- Run `python -m py_compile` on touched helper files.

## Child DOX Index

No child AGENTS.md files yet.
