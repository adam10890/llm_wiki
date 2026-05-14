## wiki_commit: Record wiki changes in git

> Registry location: `/data/SharedBrain/registry.yaml` (container) / `C:\Users\frant\SharedBrain\registry.yaml` (host).  
> All six wiki tools (list, ingest, query, lint, register, commit) read this registry for grants and wiki paths.  
> If the vault is unreachable, `wiki_list` will say so and suggest checking `default_config.yaml`.

After `wiki_ingest` (or any operation that wrote files), call `wiki_commit` to
stage and commit the changes in the SharedBrain vault's git repo
(`/data/SharedBrain/.git`). Silent no-op if git isn't available or the vault
isn't a git repo. Never pushes.

**When to use:** Right after you finish writing files following a `wiki_ingest`
response, or after `wiki_lint fix=true`, or any time you manually edited wiki
pages. Skip if `git.auto_commit` is disabled in plugin config.

~~~json
{
    "tool_name": "wiki_commit",
    "tool_args": {
        "wiki": "<optional: wiki name to narrow staging to just that wiki>",
        "op": "INGEST|LINT|WRITE|REGISTER",
        "message": "<one-line human-readable summary>"
    }
}
~~~

Returns the commit SHA on success, or a reason string when there was nothing
to commit. Good commit messages match the `log.md` format: refer to the source
filename for ingests, the issue type for lints, etc.
