# llm_wiki — Reference

**Version:** 2.2.0 | Agent Zero v1.15–v1.17

## Overview

Multi-wiki knowledge base for Agent Zero. Agents compile raw sources into structured markdown collections that compound over time — instead of re-deriving knowledge via RAG on every query.

Pattern: [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) extended into a multi-wiki registry with per-agent access control.

## Installation

```bash
docker cp ./llm_wiki <container>:/a0/usr/plugins/llm_wiki
```

Point the plugin at your vault in `default_config.yaml`:
```yaml
shared_vault:
  enabled: true
  path: "/data/SharedBrain"    # or leave empty for auto-detect
agent_id: "agent_zero"
```

## Smoke test

From Plugin List UI → click **Run** next to `llm_wiki`, or:
```bash
python3 usr/plugins/llm_wiki/execute.py /data/SharedBrain --agent-id agent_zero
```

## Tools

### wiki_list
```json
{"tool_name":"wiki_list","tool_args":{}}
```

### wiki_ingest
```json
{
  "tool_name": "wiki_ingest",
  "tool_args": {
    "source_path": "/data/article.md",
    "wiki": "general"
  }
}
```
After `wiki_ingest` returns, call `wiki_commit` to record a git commit.

### wiki_query
```json
{
  "tool_name": "wiki_query",
  "tool_args": {
    "question": "What do we know about rate limiting?",
    "wikis": ["commons", "general"]
  }
}
```

### wiki_lint
```json
{"tool_name":"wiki_lint","tool_args":{"wiki":"commons"}}
```
Auto-fix: add `"fix": true`.

### wiki_register
```json
{
  "tool_name": "wiki_register",
  "tool_args": {
    "name": "project_foo",
    "scope": "project",
    "title": "Project Foo"
  }
}
```
After registering, manually edit `registry.yaml` to add grants.

### wiki_commit
```json
{
  "tool_name": "wiki_commit",
  "tool_args": {
    "wiki": "commons",
    "op": "INGEST",
    "message": "article.md"
  }
}
```

## Registry schema

`SharedBrain/registry.yaml`:

```yaml
wikis:
  - name: commons
    title: "Shared Brain"
    path: "./wikis/commons"
    scope: shared
    sensitivity: internal
    default_for_ingest: true

grants:
  agent_zero:
    read:  ["*"]
    write: [commons, agent_self, about_user, general]

query:
  default_scope: all_readable
  max_wikis_per_query: 6
  max_pages_per_wiki: 15
  namespaced_citations: true
```

## Page conventions

| Convention | Value |
|---|---|
| Hard line cap | 500 lines (split into MOC above) |
| Coverage tags | `<!-- coverage: high\|medium\|low -->` |
| Backlinks | `[[page]]` or `other_wiki::[[page]]` |

## Git auto-commit

Initialize a git repo in the vault to enable:
```bash
cd /data/SharedBrain && git init
```

Every write records a commit:
```
[llm_wiki] [INGEST] commons: article.md (by agent_zero)
```

Disable with `git.auto_commit: false`.

## Multi-wiki vs legacy mode

| Mode | Config | Behaviour |
|---|---|---|
| Multi-wiki (default) | `shared_vault.enabled: true` | Registry + access control |
| Legacy | `shared_vault.enabled: false` | Per-project `wiki_raw/` + `wiki/` dirs, no access control |
