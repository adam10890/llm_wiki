# LLM Wiki — Karpathy-style Multi-Wiki Knowledge Base for Agent Zero

A plugin that implements [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) as a first-class Agent Zero plugin — extended into a **multi-wiki registry** so multiple agents can share one brain while keeping private, per-user, per-project, and external knowledge cleanly separated.

Instead of re-deriving knowledge via RAG on every query, agents **incrementally compile** raw sources into structured, interlinked markdown collections that compound over time.

## Version 2.1 — what's new

- **Multi-wiki mode is ON by default.** `shared_vault.path` is empty by
  default so the plugin auto-detects the vault by looking for
  `SharedBrain/registry.yaml` in the active project root and a few ancestor
  directories. This works out-of-the-box both on the Windows host and inside
  the Agent Zero container (`/data/SharedBrain` is the bind-mount target — see
  [Deployment layout](#deployment-layout-this-workspace)). If you need to pin
  a path, set `shared_vault.path` to an absolute directory.
- **Git auto-commit trail.** Every `wiki_ingest`, `wiki_lint fix=true`, and
  `wiki_register` records a commit in the vault's git repo so you can
  review and revert any agent's work. Silent no-op if the vault isn't a
  git repo. Never pushes.
- **Coverage indicators.** Ingested pages get per-section `<!-- coverage: high|medium|low -->`
  tags so downstream tools know how much to trust each section.
- **Two new tools:**
  - `wiki_register` — add a new wiki to the registry at runtime (creates
    the standard skeleton; does NOT auto-grant access).
  - `wiki_commit` — stage and commit pending changes in the vault git
    repo.
- **`execute.py` smoke test.** Run it from Agent Zero's Plugin List UI
  or the command line to verify the vault is wired up correctly.
- **Claude Code companion plugin.** A sibling `claude-code-plugin/llm-wiki/`
  at the repo root gives Claude Code the same slash commands against the
  same `registry.yaml`.

## Version 2.0 — carry-over

- **Multi-wiki registry.** One vault hosts many independent wikis (`commons`, `agent_self`, `about_user`, `general`, per-project, external). Registry lives at `SharedBrain/registry.yaml`.
- **Per-agent access control.** Each agent (`agent_zero`, `claude_code`, `cowork`, `openclaw`, `hermes`, …) has explicit read/write grants. Tools refuse operations outside the grants.
- **Cross-wiki queries.** `wiki_query` fans out across every readable wiki and cites pages with namespaced backlinks: `commons::[[page]]`.
- **External local wikis.** Register any folder on the machine (e.g., an existing personal Obsidian vault) as a read-only source.
- **Legacy mode preserved.** If `shared_vault.enabled: false`, the plugin still runs in the original per-project single-wiki mode.

## Quick Start

### 1. Create (or point at) a SharedBrain vault

A ready-to-use template ships alongside this plugin at `SharedBrain/` (top of the Agent Zero install). It contains:

- `wikis/commons/` — shared multi-agent brain
- `wikis/agent_self/` — Agent Zero's private self-model
- `wikis/about_user/` — what we know about the user
- `wikis/general/` — topic-agnostic reference material
- `agents/` — per-agent entry points (`CLAUDE.md`, `SKILL.md`, `AGENTS.md`, `openclaw.md`, `hermes.md`)
- `registry.yaml` — canonical wiki registry
- `README.md`, `SETUP.md`, `ROADMAP.md`

Move the folder anywhere you like (your real Obsidian vault location, `~/Documents`, etc.) — the registry uses absolute paths.

### 2. Set the vault path

In this workspace `shared_vault.path` is already pinned to `/data/SharedBrain`
in `default_config.yaml` so Agent Zero sees the vault at the container mount
point. On a fresh install you can either set an absolute path or leave it
empty to let the plugin auto-detect a sibling `SharedBrain/` directory:

```yaml
shared_vault:
  enabled: true
  path: "/absolute/path/to/SharedBrain"
```

Or per-project via `.a0proj/plugins/llm_wiki/config.json`.

### 3. (Optional) enable git auto-commit

```bash
cd /path/to/SharedBrain
git init
```

Now every write records a reviewable commit. Disable with `git.auto_commit: false` in `default_config.yaml` if you prefer silent writes.

### 4. Smoke-test the install

From Agent Zero's Plugin List UI, click **Run** next to `llm_wiki` — this invokes `execute.py`, which prints the detected vault, your grants, wiki counts, and git status.

Or from a shell:
```bash
python3 usr/plugins/llm_wiki/execute.py SharedBrain --agent-id agent_zero
```

### 5. Use it

```
wiki_list                                          # see all wikis + your grants
wiki_ingest source_path=article.md wiki=general
wiki_query question="what do we know about X" wikis=[commons, general]
wiki_lint wiki=commons
wiki_register name=project_foo scope=project title="Project Foo"
wiki_commit wiki=commons op=INGEST message="attention.pdf"
```

## Tools

| Tool | Purpose | Multi-wiki argument |
|---|---|---|
| `wiki_list` | List all wikis + grants + stats | — |
| `wiki_ingest` | Compile a raw source into a wiki | `wiki` (defaults to registry's default) |
| `wiki_query` | Search wikis and synthesize an answer | `wikis` (defaults to all readable) |
| `wiki_lint` | Health-check a wiki | `wiki` (required) |
| `wiki_register` | Add a new wiki to the registry | `name`, `scope`, `path`, … |
| `wiki_commit` | Stage + commit wiki changes in git | `wiki`, `op`, `message` |

All original v1/v2 arguments still work; v2.1 additions are purely additive.

## Documentation map

| File | Audience | What it teaches |
|---|---|---|
| `README.md` | Human user / admin | Installation, config, tool reference |
| `default_config.yaml` | Admin | Runtime settings (vault path, agent id, git, coverage) |
| `skills/SKILL.md` | Agent (system prompt) | Architecture, workflow, conventions |
| `prompts/agent.system.tool.*.md` | Agent (per-tool) | Exact JSON schema + when-to-use for each tool |
| `execute.py` | Admin / CI | Smoke-test script; verifies vault discovery + grants |
| `config.json` (per-project) | Admin | Project-specific overrides of defaults |
| `registry.yaml` | SharedBrain runtime | Canonical wiki list + agent grants (human-curated) |

## Deployment layout (this workspace)

In this Agent Zero installation the vault is bind-mounted into the container:

- **Host path:** `C:\Users\frant\SharedBrain`
- **Container path:** `/data/SharedBrain`
- **Compose stanza:**

  ```yaml
  services:
    agent-zero-2:
      volumes:
        - type: bind
          source: ./SharedBrain
          target: /data/SharedBrain
  ```

**Plugin config** (`default_config.yaml`) matches the mount:

```yaml
shared_vault:
  enabled: true
  path: "/data/SharedBrain"
agent_id: "agent_zero"
```

That `agent_id` must match the `grants.agent_zero` block in
`/data/SharedBrain/registry.yaml`.

**Vault tree as seen from inside the container:**

```text
/data/SharedBrain/
├── wikis/
│   ├── commons/
│   ├── about_user/
│   ├── agent_self/
│   ├── general/
│   └── slr_project/
├── registry.yaml
└── .git
```

## Registry schema

See `/data/SharedBrain/registry.yaml` (container) or `C:\Users\frant\SharedBrain\registry.yaml` (host) for the canonical schema. The essentials:

```yaml
wikis:
  - name: commons
    title: "Shared Brain"
    path: "./wikis/commons"     # relative to vault root, or absolute
    scope: shared                     # shared|self|personal|project|reference|external
    description: "..."
    tags: [shared, multi-agent]
    sensitivity: internal             # public|internal|private|secret
    default_for_ingest: true

grants:
  agent_zero:
    read:  ["*"]
    write: [commons, agent_self, about_user, general]
  claude_code:
    read:  [commons, about_user, general, slr_project]
    write: [commons, general, slr_project]
  # ...

query:
  default_scope: all_readable         # all_readable|default_only|scoped
  max_wikis_per_query: 6
  max_pages_per_wiki: 15
  namespaced_citations: true
```

## Access control

On every tool call, the plugin:

1. Reads `shared_vault.path` from config (or auto-detects) → locates the vault root.
2. Reads `registry.yaml` at the vault root.
3. Determines your agent id from `agent_id` config override or auto-detection.
4. Looks up `grants.<agent_id>.read` / `.write`.
5. Refuses any operation that exceeds your grants.

If an agent is not listed in `grants`, the plugin defaults to `read: ["*"]` on `sensitivity <= internal` and no write access.

`wiki_register` creates the skeleton and appends to `registry.yaml` but **never touches `grants:`** — access control is always a human decision. After registering, the user edits `registry.yaml` by hand to grant access.

## Git auto-commit

Every write-producing tool calls `registry.git_commit_after(...)` after the LLM finishes writing files. Commit messages look like:

```
[llm_wiki] [INGEST] commons: 2026-04-18-standup.md (by agent_zero)
```

Configure via the `git:` block in `default_config.yaml`. Set `auto_commit: false` to silence it globally, or invoke `wiki_commit` manually when you want a commit.

`wiki_ingest` reminds the agent to call `wiki_commit` after writing — because the tool returns before the LLM writes the actual files, the commit needs to happen in a second turn.

## Coverage indicators

When `coverage.enabled: true` (default), `wiki_ingest` instructs the agent to annotate each substantive `##` / `###` section of a new page with a trust tag:

```markdown
## Background <!-- coverage: high -->
## Open questions <!-- coverage: low -->
```

Values: `high` (well-sourced), `medium` (partial / inferred), `low` (stub / speculative). `wiki_lint` and `wiki_query` can use these to decide when to fall back to raw sources.

## Graphify integration (per wiki)

Same as v1: each wiki can have its own `graphify-out/graph.json` at its root. `wiki_ingest` auto-loads god nodes, communities, and source-related edges into the ingest prompt.

## Obsidian compatibility

Open `SharedBrain/` as an Obsidian vault and you get the full graph view, backlink panel, and search for free. `[[backlinks]]` are plain Obsidian wikilinks; namespaced backlinks (`other_wiki::[[page]]`) render as plain text in Obsidian but are still human-readable.

## Legacy single-wiki mode

If `shared_vault.enabled: false`, tools fall back to the original behavior: use the active project's `wiki_raw/` and `wiki/` directories. No access control, no registry, one wiki per project. You can mix both modes across projects freely.

## Claude Code companion

If you want the same commands inside Claude Code, the companion plugin at the repo root (`claude-code-plugin/llm-wiki/`) exposes `/wiki-list`, `/wiki-ingest`, `/wiki-query`, `/wiki-lint`, `/wiki-register`, `/wiki-commit` against the same vault. Both agents read the same `registry.yaml` so grants are consistent.

## Credits

- Pattern: [Andrej Karpathy's LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- Plugin + multi-wiki adaptation: Adam Frantz
- Built for [Agent Zero](https://github.com/agent0ai/agent-zero)

## License

MIT
