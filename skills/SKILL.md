---
name: "llm-wiki"
description: >
  Karpathy-style LLM Wiki — a persistent, self-maintaining knowledge base
  built from markdown files. Use this skill whenever the user mentions wiki,
  knowledge base, second brain, ingest sources, compile knowledge, research
  wiki, or asks to organize information into a structured interlinked
  collection. Also trigger when the user drops files into any `wiki_raw/` under
  the SharedBrain vault, or asks questions that could be answered from any
  wiki in the registry you have read access to.
version: "1.0.0"
author: "Adam Frantz"
license: "MIT"
tags: ["knowledge-base", "wiki", "research", "markdown", "rag-alternative"]
triggers:
  - "wiki"
  - "knowledge base"
  - "second brain"
  - "ingest"
  - "compile knowledge"
  - "lint wiki"
  - "wiki query"
---

# LLM Wiki — Karpathy-style Knowledge Base

## Overview

This plugin implements Andrej Karpathy's LLM Knowledge Base pattern.
Instead of re-deriving knowledge via RAG on every query, the LLM
**incrementally builds and maintains a persistent wiki** — a structured,
interlinked collection of markdown files that compounds with every source
you add and every question you ask.

## Deployment-specific paths (this workspace)

The SharedBrain vault is bind-mounted into the Agent Zero container at
`/data/SharedBrain/`.  The canonical registry lives at:

- **Inside the container:** `/data/SharedBrain/registry.yaml`
- **On the Windows host:**
  `C:\Users\frant\SharedBrain\registry.yaml`

All wiki content is stored under `wikis/<name>/` inside that vault.
Legacy single-wiki mode (per-project `wiki_raw/` + `wiki/`) is still
supported but not used here.

## Architecture

**Multi-wiki mode (this workspace):**

```
/data/SharedBrain/           ← Vault root (registry.yaml lives here)
├── wikis/
│   ├── commons/
│   │   ├── wiki_raw/      ← Immutable sources (human-curated)
│   │   └── wiki/
│   │       ├── concepts/
│   │       ├── entities/
│   │       ├── sources/
│   │       ├── queries/
│   │       ├── index.md   ← Table of contents
│   │       └── log.md     ← Append-only operation log
│   ├── about_user/
│   ├── agent_self/
│   ├── general/
│   └── slr_project/
└── registry.yaml          ← Canonical wiki list + agent grants
```

**Legacy single-wiki mode (per-project):**

```
project/
├── wiki_raw/          ← Immutable source material (human adds, never modify)
│   └── topic/
│       └── 2026-04-06-source.md
├── wiki/              ← Compiled knowledge (LLM maintains)
│   ├── concepts/
│   ├── entities/
│   ├── sources/
│   ├── queries/
│   ├── index.md       ← Table of contents by category
│   └── log.md         ← Append-only operation log
```

## Three Operations

### 1. Ingest (`wiki_ingest`)
When a new source is added to `wiki_raw/` (e.g. `wikis/commons/wiki_raw/`):
1. Read the source document
2. Write a summary page under `wiki/sources/`
3. Create or update entity pages under `wiki/entities/`
4. Create or update concept pages under `wiki/concepts/`
5. Add `[[backlinks]]` between all related pages
6. Update `wiki/index.md` with new entries
7. Append to `wiki/log.md`

A single source typically touches 5-15 wiki pages.
In multi-wiki mode the target wiki is chosen from the registry
(`commons`, `agent_self`, `about_user`, `general`, or a project wiki).

### 2. Query (`wiki_query`)
When the user asks a knowledge question:
1. Read the registry to find all wikis you have read access to
2. Read each target wiki's `wiki/index.md` to identify relevant pages
3. Load and read the relevant pages
4. Synthesize an answer with `[[page-name]]` and namespaced `wiki::[[page]]` citations
5. Optionally save the answer as a new page under `wiki/queries/`

### 3. Lint (`wiki_lint`)
Periodically health-check the wiki:
- Broken `[[backlinks]]`
- Orphan pages not in the index
- Stub pages needing expansion
- Missing cross-references
- Contradictions between pages
- Stale claims superseded by newer sources

In multi-wiki mode, lint operates on one named wiki at a time
(e.g. `wiki=commons`).

## Wiki Page Conventions

### Backlinks
Use `[[page-name]]` notation (Obsidian-compatible) to link between pages.
Every page should have at least one inbound and one outbound backlink.

### Page Structure
```markdown
# Page Title

> One-line summary of this page.

## Content
Main content here...

## Sources
- [[source-summary-page]] — what this source contributed

## Related
- [[related-concept]]
- [[related-entity]]
```

### Index Structure
```markdown
# Wiki Index

## Concepts
- [[concept-name]] — one-line summary (N sources)

## Entities
- [[entity-name]] — one-line summary

## Sources
- [[source-summary]] — date, origin

## Queries
- [[query-page]] — date, question asked
```

### Log Structure
```markdown
# Wiki Log

## [2026-04-06 20:30] [INGEST] article-about-topic.md
Ingested source. Created 2 new pages, updated 3 existing.

## [2026-04-06 21:00] [QUERY] What is the relationship between X and Y?
Answered from 4 wiki pages. Saved as queries/2026-04-06_21-00-query.md.

## [2026-04-06 22:00] [LINT] 3 issues found
Fixed 2 broken backlinks. 1 stub page flagged for expansion.
```

## Key Principles

1. **Raw sources are immutable** — never modify files in `wiki_raw/`
2. **The LLM owns the wiki** — humans rarely edit wiki pages directly
3. **Knowledge compounds** — every ingest and query makes the wiki richer
4. **Backlinks create structure** — they replace the need for embeddings
5. **The index is the navigation** — the LLM reads it first on every query
6. **The log is the timeline** — it orients new sessions without re-explaining

## Graphify Integration

The LLM Wiki integrates with [graphify](https://github.com/safishamsi/graphify) —
a knowledge graph tool that extracts entities and relationships from any mix of
files (code, docs, papers, images) using AST parsing and Claude.

### How They Work Together

graphify and LLM Wiki are complementary layers:

| Layer | graphify | LLM Wiki |
|-------|----------|----------|
| **Format** | JSON graph (nodes + edges) | Markdown pages with backlinks |
| **Strength** | Structural discovery, topology | Narrative synthesis, human reading |
| **Navigation** | BFS/DFS traversal, shortest path | Index-based, backlink following |
| **Best for** | "What connects X to Y?" | "Explain X in detail" |

### Recommended Workflow

```
1. Drop sources into wiki_raw/
2. Run:  /graphify wiki_raw/          ← builds graph.json + GRAPH_REPORT.md
3. Run:  wiki_ingest <source>         ← auto-reads graph context
4. The ingest tool uses god nodes, communities, and edges from the graph
   to create smarter wiki pages with better cross-references
```

### What the Ingest Tool Gets from Graphify

When `graphify-out/graph.json` exists in the project, `wiki_ingest` automatically
loads and injects:

- **God nodes** — the 10 highest-connectivity concepts (ensures wiki covers them)
- **Communities** — cluster groupings (guides which concepts belong together)
- **Related edges** — connections involving the current source (guides backlinks)
- **GRAPH_REPORT.md** — god nodes summary, surprising connections, suggested questions

### Graph-Informed Wiki Pages

When graph context is available, follow these additional guidelines:

- Every **god node** should have its own wiki page (concept or entity)
- Nodes in the **same community** should cross-reference each other via backlinks
- **EXTRACTED edges** from the graph map directly to backlinks
- **INFERRED edges** are candidates for backlinks — verify in source first
- **AMBIGUOUS edges** should be noted in the wiki page as uncertain connections
- **Surprising connections** from GRAPH_REPORT.md deserve their own analysis pages

### Running Graphify

graphify is a separate tool. Install it in the Agent Zero environment:

```bash
pip install graphifyy --break-system-packages
```

Then either:
- Use Claude Code's `/graphify` skill command
- Or run directly: `python3 -m graphify wiki_raw/`

The output lands in `graphify-out/` at the project root. The wiki tools
detect it automatically — no configuration needed.

## Common Pitfalls

- Don't try to ingest too many sources at once — go one at a time for quality
- Don't skip updating the index — it's how future queries find information
- Don't create pages without backlinks — isolated pages get lost
- Don't forget to lint — wikis drift without maintenance

## See also

- `README.md` — full plugin docs, config reference, and tool table
- `default_config.yaml` — runtime settings (`shared_vault.path`, `agent_id`, git)
- Tool prompts (injected per-tool): `wiki_list`, `wiki_ingest`, `wiki_query`,
  `wiki_lint`, `wiki_register`, `wiki_commit`
