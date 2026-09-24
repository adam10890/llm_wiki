## wiki_query: Search and answer across wikis

> Registry location: `/data/SharedBrain/registry.yaml` (container) / `C:\Users\frant\SharedBrain\registry.yaml` (host).  
> All six wiki tools (list, ingest, query, lint, register, commit) read this registry for grants and wiki paths.  
> If the vault is unreachable, `wiki_list` will say so and suggest checking `default_config.yaml`.

Query the LLM Wiki knowledge base. In multi-wiki (SharedBrain) mode the tool
fans out across every wiki you have read access to, capped by
`query.max_wikis_per_query`. Answers cite pages with namespaced backlinks
(e.g., `commons::[[page]]`) so the user can see which wiki each claim
came from.

**Mandatory search order:** Before EVERY non-wiki search, perform a fresh,
task-relevant wiki lookup and read the results. This includes web, repository,
filesystem, database, connector and other-memory searches, even when the user
does not mention the wiki. Do not launch the other search in parallel. A cached
catalog or previous answer is not a refresh. Follow the active profile's
delegation policy; the librarian must preserve the requester's access scope.
Use outside sources for remaining gaps or required freshness verification.
If the wiki is unavailable or access is denied, report the blocker and pause
other searches unless the user explicitly permits an exception. Wiki discovery
and retrieval are exempt from recursive preflight. Never send private wiki
content to external search services.

**Also use:** When the user asks a question that could be answered from
any wiki, or asks to "search the wiki", "look up", "find in wiki", "what does
the wiki say about", "what do you know about X" — use this BEFORE answering
from your training knowledge.

~~~json
{
    "tool_name": "wiki_query",
    "tool_args": {
        "question": "<the user's question>",
        "wikis": ["<optional: list of wiki names to narrow the search>"],
        "save_answer": false
    }
}
~~~

- `wikis`: optional. If provided, only these wikis are consulted (after access
  check). If omitted, the query fans out across all readable wikis.
- `save_answer`: if true, your synthesized answer is saved as a new page in
  the default wiki's `wiki/queries/` folder (compounding knowledge). Default false.

The tool returns each consulted wiki's index + relevant pages. Synthesize
them into a clear answer with namespaced `wiki_name::[[page]]` citations.
When wikis contradict, say so and cite both sides. When the wikis don't cover
the topic, say so and suggest which sources to ingest to fill the gap.

If your task focuses on one specific wiki rather than a broad fan-out query,
first inspect that wiki's `wiki_raw/` for pending source files. Fresh raw
material may change what the current canonical answer should be.

**Log discipline:** After answering, append a `[QUERY]` entry to the
`wiki/log.md` of every wiki you touched.
