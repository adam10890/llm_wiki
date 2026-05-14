## wiki_list: List all wikis available to you

> Registry location: `/data/SharedBrain/registry.yaml` (container) / `C:\Users\frant\SharedBrain\registry.yaml` (host).  
> All six wiki tools (list, ingest, query, lint, register, commit) read this registry for grants and wiki paths.  
> If the vault is unreachable, `wiki_list` will say so and suggest checking `default_config.yaml`.

Returns every wiki visible to you (per the SharedBrain registry), along with
scope, sensitivity, access grants, page counts, and paths.

**When to use:** At the start of any wiki-related task, before ingesting or
querying. It is cheap and orients you to what exists. Also when the user
asks: "what wikis do we have?", "show me the wiki registry", "which wikis
can you read?", "which wikis can I write to as `<agent>`?".

After orienting with `wiki_list`, if you are about to work inside one specific
wiki, do not stop at the registry: read that wiki's `index.md`, recent
`log.md`, and inspect `wiki_raw/` for pending source files before proceeding.

~~~json
{
    "tool_name": "wiki_list",
    "tool_args": {
        "verbose": false
    }
}
~~~

- `verbose`: if true, includes descriptions, tags, and recent log entries
  from the default wiki. Default false (compact table).

The tool reads `SharedBrain/registry.yaml`, resolves each wiki's absolute
path, checks existence, counts pages, and reports everything through a
compact markdown table. Grants are evaluated against the agent id the
plugin has detected for the current agent (or the `agent_id` config override,
if set).

If no SharedBrain vault is configured, the tool explains how to enable one.
