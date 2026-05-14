## wiki_register: Add a new wiki to the SharedBrain registry

> Registry location: `/data/SharedBrain/registry.yaml` (container) / `C:\Users\frant\SharedBrain\registry.yaml` (host).  
> All six wiki tools (list, ingest, query, lint, register, commit) read this registry for grants and wiki paths.  
> If the vault is unreachable, `wiki_list` will say so and suggest checking `default_config.yaml`.

Register a new wiki at runtime — creates the standard `wiki_raw/` + `wiki/`
skeleton under `wikis/<name>/` inside the vault, appends the entry to
`registry.yaml`, and reloads. The new wiki's **grants are not auto-modified**;
the tool prints the exact YAML snippet for you to paste so access control
stays in human hands.

**When to use:** User says "register a new wiki", "add a project wiki",
"create a new wiki for X", or drops a folder and asks to make it a wiki.

~~~json
{
    "tool_name": "wiki_register",
    "tool_args": {
        "name": "<snake_case id, e.g. project_foo>",
        "title": "<human readable title>",
        "path": "<absolute or vault-relative path>",
        "scope": "shared|self|personal|project|reference|external",
        "description": "<one sentence>",
        "tags": ["list", "of", "tags"],
        "sensitivity": "public|internal|private|secret",
        "default_for_ingest": false,
        "create_skeleton": true
    }
}
~~~

Validation:
- `name` must be snake_case and not already registered.
- `scope` must be one of the six valid scopes.
- `sensitivity` must be one of the four valid levels.
- If the path doesn't exist and `create_skeleton: true`, the tool creates
  `wiki_raw/` and `wiki/{concepts,entities,sources,queries}` with an empty
  `index.md` + `log.md`.

After registration: tell the user which grants snippet to paste into
`registry.yaml` and confirm they want those grants before writing to the new
wiki. Never self-grant.
