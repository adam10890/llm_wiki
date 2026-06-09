# DOX contract - llm_wiki/api

## Purpose

Web/API wrappers for SharedBrain plugin operations.

## Ownership

- API files are wrappers and must delegate grant-sensitive behavior to tools or
  shared registry helpers.

## Local Contracts

- Do not expose a write path that skips registry grant checks.

## Work Guidance

- Keep route names aligned with webui callers.

## Verification

- Run `python -m py_compile` on touched API files.

## Child DOX Index

No child AGENTS.md files yet.
