"""
wiki_commit — stage & commit pending wiki changes to the vault git repo.

Agents call this after `wiki_ingest` (or any operation that wrote files) to
record the work as a reviewable commit. Silent no-op if git isn't available
or the vault isn't a git repo. Never pushes.
"""

import os

try:
    from ._base import WikiToolBase, WikiRegistry, Response
except ImportError:
    # Agent Zero v1.10+ loads tool files via importlib.spec_from_file_location
    # without a package context, breaking relative imports. Fall back to absolute.
    import os as _os, sys as _sys
    _here = _os.path.dirname(_os.path.abspath(__file__))
    if _here not in _sys.path:
        _sys.path.insert(0, _here)
    from _base import WikiToolBase, WikiRegistry, Response  # type: ignore


class WikiCommit(WikiToolBase):
    """Commit pending wiki changes to the vault's git repo."""

    async def execute(self, **kwargs):
        wiki_name = ""
        for key in ("wiki", "wiki_name", "target", "name"):
            val = self.args.get(key)
            if isinstance(val, str) and val.strip():
                wiki_name = val.strip()
                break
            if isinstance(val, list) and val:
                wiki_name = str(val[0]).strip()
                break

        op = self.args.get("op", "WRITE") or "WRITE"
        message = ""
        for key in ("message", "msg", "commit_message", "text"):
            val = self.args.get(key)
            if isinstance(val, str) and val.strip():
                message = val.strip()
                break

        config = self._get_config()
        agent_id = self._get_agent_id()
        project_dir = self._get_project_dir()

        registry = WikiRegistry.from_config(
            plugin_config=config,
            agent_id=agent_id,
            fallback_project_dir=project_dir,
        )
        if registry is None:
            return Response(
                message="No SharedBrain vault configured; wiki_commit is a no-op in legacy mode.",
                break_loop=False,
            )

        # Narrow the stage paths to the target wiki if provided
        paths = None
        if wiki_name:
            w = registry.get_wiki(wiki_name)
            if w is None:
                return Response(
                    message=f"Wiki `{wiki_name}` not in registry.",
                    break_loop=False,
                )
            paths = [registry.wiki_paths(w)["wiki_dir"]]

        if not message:
            message = "wiki changes"

        result = registry.git_commit_after(
            op=op,
            wiki_name=wiki_name or "<vault>",
            message=message,
            paths=paths,
        )

        if not result["ok"]:
            return Response(
                message=f"wiki_commit failed: {result.get('reason', 'unknown')}",
                break_loop=False,
            )
        if not result["committed"]:
            return Response(
                message=f"No commit created ({result.get('reason', 'no changes')}).",
                break_loop=False,
            )
        return Response(
            message=f"Committed {result['sha']} — [{op}] {wiki_name or '<vault>'}: {message}",
            break_loop=False,
        )



# A0 v1.10 module loader picks the last alphabetically-ordered class that subclasses Tool;
# remove the imported base from the module namespace so it picks the concrete tool defined here.
del WikiToolBase
