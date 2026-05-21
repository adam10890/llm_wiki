# Start Here — LLM Wiki Operating Instructions

You are reading this because you need to **read from** or **write to** the SharedBrain wiki system. This page is short on purpose: it explains the rules, then points you at the right next page.

## What the wiki layer is

A persistent, markdown-based knowledge base shared across agents. Each "wiki" is a folder of interlinked pages with `[[wikilinks]]` and YAML frontmatter. The vault is Obsidian-compatible — you can open it in Obsidian for graph view, backlinks, and full-text search.

## The 5 core rules

1. **Long-term memory only.** If a fact is useful only for the current session, write it to Pen & Paper, not the wiki.
2. **Compile, do not paste.** When ingesting a source, restructure into the wiki's voice. Do not dump the raw document.
3. **Use wikilinks liberally.** `[[page-name]]` for same wiki, `wiki-name::[[page]]` for cross-wiki citations.
4. **Coverage tags.** Mark each substantive section with `<!-- coverage: high|medium|low -->` so downstream tools know how much to trust it.
5. **Hard ceiling: 500 lines per page.** Target ≤400. Above that, split into linked pages with a parent MOC (map of content).

## Workflow

```
wiki_list                                # see what wikis you have access to
wiki_query question="..." wikis=[...]    # read across wikis
wiki_ingest source_path=... wiki=...     # compile a raw source into the wiki
wiki_lint wiki=...                       # health-check
wiki_commit wiki=... message=...         # commit the changes (auto by default)
```

Access is registry-controlled — `wiki_list` shows what you can do.

## What goes in which wiki

Default wikis in the SharedBrain vault:

- **`commons`** — shared multi-agent knowledge. Things any agent should know.
- **`agent_self`** — the agent's private self-model: capabilities, mistakes, preferences.
- **`about_user`** — what the agent knows about the user.
- **`general`** — topic-agnostic reference material.
- **`onboarding`** — *this* wiki. Operating instructions only.

Project-specific facts → register a project wiki with `wiki_register`.

## Bridge to Pen & Paper (working memory)

| Need | Tool |
|---|---|
| Scratchpad for *this* task | `pen_paper` (a0_pen_paper plugin) |
| Search prior knowledge | `wiki_query` |
| Promote a session finding to long-term | `wiki_ingest` from the session file |
| Find prior session vectors | `pen_paper` vectorizer or `wiki_query` |

Rule of thumb: **draft in Pen & Paper, distil to Wiki at session close.** Never store the same fact in both.

## What to do next

1. Querying? Run `wiki_query` with the right `wikis=[...]` list.
2. Writing? Pick the destination wiki, then `wiki_ingest`.
3. Confused about which wiki? Open `index.md` (sibling) or run `wiki_list`.
4. Need methodology depth? See `skills/SKILL.md` at the plugin root.
