## wiki_ingest: Compile a raw source into a wiki

> Registry location: `/data/SharedBrain/registry.yaml` (container) / `C:\Users\frant\SharedBrain\registry.yaml` (host).  
> All six wiki tools (list, ingest, query, lint, register, commit) read this registry for grants and wiki paths.  
> If the vault is unreachable, `wiki_list` will say so and suggest checking `default_config.yaml`.

Ingest a raw source document into a named wiki. Works in two modes:

1. **SharedBrain multi-wiki mode** — targets a named wiki from the registry
   (e.g., `commons`, `agent_self`, `about_user`, `general`, or a project
   wiki). Access-controlled via `registry.yaml → grants.<your_agent_id>.write`.
   In this mode the raw file lives under `wikis/<name>/wiki_raw/` inside the vault.
2. **Legacy single-wiki mode** — uses the active project's `wiki_raw/` + `wiki/`.

**When to use:** When the user drops a new source file into a `wiki_raw/`
directory, or asks you to "add", "ingest", "process", "import", or "read into
the wiki", or "ingest into `<wiki_name>`".

~~~json
{
    "tool_name": "wiki_ingest",
    "tool_args": {
        "source_path": "<relative path inside the target wiki's wiki_raw/>",
        "wiki": "<optional: target wiki name; defaults to registry's default>",
        "focus": "<optional: what to emphasize when extracting>"
    }
}
~~~

The tool will:
1. Resolve which wiki to target (explicit `wiki`, or the registry's default).
2. Verify your write access (refuses politely if you don't have it).
3. Read the raw source file.
4. Load the target wiki's current `index.md` for cross-reference awareness.
5. Auto-load `graphify-out/graph.json` at the wiki root if it exists.
6. Return source content + context so you can compile the wiki updates.
7. Before moving on to other tasks in that wiki, make sure no other pending raw
   files in the same `wiki_raw/` should be ingested first.
8. You then write/update wiki pages via file tools, update `index.md`, and
   append to `log.md`.
9. Call `wiki_commit` to seal the compiled pages + log entry into git.
10. **Only if the commit succeeded**, delete the raw source file from
    `wiki_raw/`. The content is preserved in git history + summarised in
    `wiki/sources/`. If `git.auto_commit` is disabled or the commit failed,
    leave the raw file alone and tell the user. `wiki_raw/` is otherwise
    immutable — never edit, rename, or move raw sources in place.

**Multi-wiki decisions:** The tool tells you which wiki it targeted. If the
user was ambiguous, verify the choice in your response. The decision tree:

- Self-reflection / lessons-learned → `agent_self`
- Facts about the user → `about_user`
- Project-specific → `<project_name>` wiki
- Reference material (paper, article) → `general`
- Cross-agent operational knowledge → `commons` (the default)

**Cross-wiki backlinks:** When you link to a page in a different wiki, use
namespaced syntax: `other_wiki::[[page-name]]`. Inside a single wiki, plain
`[[backlinks]]` are fine.

**Graphify integration:** If `graphify-out/graph.json` exists at the target
wiki's root, the tool automatically loads god nodes, community clusters, and
source-related edges. Use this to create smarter backlinks. Run
`/graphify <wiki_raw_path>` first for best results.
