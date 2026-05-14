## wiki_lint: Health-check a wiki

> Registry location: `/data/SharedBrain/registry.yaml` (container) / `C:\Users\frant\SharedBrain\registry.yaml` (host).  
> All six wiki tools (list, ingest, query, lint, register, commit) read this registry for grants and wiki paths.  
> If the vault is unreachable, `wiki_list` will say so and suggest checking `default_config.yaml`.

Run a health check on one wiki at a time. Scans for broken backlinks, orphan
pages, stub pages, index gaps, and (in multi-wiki mode) cross-wiki references
that may need canonicalization. Contradictions are always flagged for human
review, never auto-resolved. The full report is saved inside the target wiki's
root directory (e.g. `wikis/commons/lint-YYYY-MM-DD.md`).

**When to use:** When the user asks to "lint", "health check", "audit",
"clean up", or "maintain" a wiki. Also triggered automatically after a
configurable number of ingest operations.

~~~json
{
    "tool_name": "wiki_lint",
    "tool_args": {
        "wiki": "<optional: target wiki name; defaults to registry's default>",
        "scope": "full",
        "fix": false
    }
}
~~~

- `wiki`: which wiki to lint. Defaults to the registry's default wiki. Lint
  one wiki at a time — don't pass a list.
- `scope`: `full` (default), `quick`, `broken_links`, `orphans`, or
  `contradictions`.
- `fix`: if true, repair mechanical issues (broken links, orphans, index
  gaps). Requires WRITE access to the target wiki — the tool refuses
  otherwise. Contradictions are never auto-fixed.

The tool returns a **tiered severity summary** and saves the full report to
`lint-YYYY-MM-DD.md` in the wiki root (viewable in Obsidian). Severity tiers:

| Tier | Meaning | Action |
|---|---|---|
| 🔴 Broken | broken backlinks, empty index | must fix |
| 🟡 Orphan / Stub | missing index entry, very short page | should fix |
| 🔵 Suggestion | no outbound links | consider |

The saved file includes full page content for semantic review (contradictions,
stale claims, missing cross-refs). The agent response is a concise summary —
don't expand it further; point the user to the saved report file.

If you are linting as part of broader wiki maintenance, inspect `wiki_raw/`
first. Pending source files should usually be ingested before treating lint
results as the current truth of that wiki.

**Log discipline:** After linting, append a `[LINT]` entry to the target
wiki's log.md` using the format provided in the tool's summary output.

**Autonomous Infection Check Protocol (Non-Blocking):**
This tool should not block ongoing work. Run it asynchronously or at logical breaks.
1. **Pass/Clean**: Silently return to and complete the pending task steps (no user notification needed).
2. **Fail/Contradictions**:
   - Analyze the contradictions and draft a specific solution (e.g., a patch or merge plan).
   - **Stop and ask the user**: `'Proposed Fix: [Details]. Proceed?'`
   - **Wait for explicit user approval** before applying any fixes.
   - Once approved and fixed, **immediately resume** the pending task.
