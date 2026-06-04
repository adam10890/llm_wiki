# AGENTS.md — llm_wiki

**Version:** 2.2.0 | **Target:** Agent Zero v1.15–v1.17

## What this plugin does

Multi-wiki knowledge base implementing Karpathy's LLM Wiki pattern. Agents compile raw sources into structured markdown collections (wikis) stored in a shared vault (`SharedBrain`). Multiple agents share one vault via a registry with per-agent access control.

## Key files

| Path | Role |
|---|---|
| `plugin.yaml` | Manifest — `always_enabled: true`, section: `agent` |
| `tools/wiki_ingest.py` | Compile a raw source into a wiki page |
| `tools/wiki_query.py` | Search across wikis, synthesize answer |
| `tools/wiki_lint.py` | Health-check a wiki (broken links, oversized pages) |
| `tools/wiki_list.py` | List wikis + grants + stats |
| `tools/wiki_register.py` | Add a new wiki to the registry |
| `tools/wiki_commit.py` | Stage + commit pending vault changes in git |
| `tools/wiki_registry.py` | `WikiRegistry` class — reads/writes `registry.yaml` |
| `tools/_base.py` | `WikiToolBase(Tool)` — shared config/identity/path helpers |
| `helpers/` | Vault discovery, git operations, coverage tagging |
| `extensions/` | System-prompt injection of vault summary |
| `initialize.py` | Plugin startup — vault discovery + sanity check |
| `execute.py` | Smoke-test script (run from Plugin List UI or CLI) |
| `default_config.yaml` | Runtime defaults (vault path, agent_id, git, coverage) |

## Vault layout

```
SharedBrain/
├── registry.yaml        # canonical wiki list + agent grants
├── wikis/
│   ├── commons/         # shared multi-agent brain
│   ├── agent_self/      # agent's private self-model
│   ├── about_user/      # knowledge about the user
│   ├── general/         # topic-agnostic reference
│   └── onboarding/      # first-instructions wiki
└── .git                 # optional — enables auto-commit
```

## Registry schema (essentials)

```yaml
wikis:
  - name: commons
    path: "./wikis/commons"    # relative to vault root, or absolute
    scope: shared              # shared|self|personal|project|reference|external
    sensitivity: internal      # public|internal|private|secret
    default_for_ingest: true

grants:
  agent_zero:
    read:  ["*"]
    write: [commons, agent_self, about_user, general]
```

## Tool reference

| Tool | Required args | Notes |
|---|---|---|
| `wiki_list` | — | Returns all wikis + grants |
| `wiki_ingest` | `source_path`, `wiki` | `wiki` defaults to registry's `default_for_ingest` |
| `wiki_query` | `question` | `wikis` defaults to all readable |
| `wiki_lint` | `wiki` | `fix=true` to auto-fix |
| `wiki_register` | `name`, `scope` | Creates skeleton; does NOT touch `grants` |
| `wiki_commit` | `wiki`, `op`, `message` | Commits pending write-tool output |

## Page conventions

- Hard cap: **500 lines per page**. Above that, split with a parent MOC.
- Coverage tags on substantive sections: `<!-- coverage: high|medium|low -->`
- Namespaced backlinks: `other_wiki::[[page]]`

## Access control enforcement

On every write tool call:
1. Read `registry.yaml` → get grants for current `agent_id`.
2. Reject if the target wiki is not in `write` grants.
3. `wiki_register` never modifies `grants` — always a human decision.

## How to add a new tool

1. Create `tools/wiki_<name>.py` with a class inheriting `WikiToolBase`.
2. A0 auto-discovers all files in `tools/`.
3. Add tool description to `prompts/agent.system.tool.<name>.md`.

## Configuration

`default_config.yaml` keys:
- `shared_vault.path` — absolute path to SharedBrain (empty = auto-detect)
- `agent_id` — must match a `grants` key in `registry.yaml`
- `git.auto_commit` — boolean
- `coverage.enabled` — boolean

`per_project_config: true` — override per project via `.a0proj/plugins/llm_wiki/config.json`.

## Integration with a0_pen_paper

Division of labour:
- `a0_pen_paper` = working memory (current session, 200–300 line pages)
- `llm_wiki` = long-term memory (cross-session, 500-line hard cap)
