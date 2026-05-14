"""
LLM Wiki — user-triggered smoke test.

Run from Agent Zero's Plugin List UI to verify the plugin is correctly
configured: it locates the SharedBrain vault, parses the registry, and prints
a wiki_list-style summary. No writes, no network. Returns 0 on success.

Usage:
  python3 execute.py [/abs/path/to/SharedBrain]
  python3 execute.py --agent-id claude_code

If no path is provided, discovery follows the same order as
`default_config.yaml` documents:

  1. `shared_vault.path` from `config.json` or `default_config.yaml`
  2. Auto-detect: active project root, then ancestor directories of the
     Agent Zero install
  3. `$SHARED_BRAIN` environment variable
  4. Current working directory (last resort)
"""
import json
import os
import sys
import argparse

# Ensure Unicode check/cross marks and em-dashes in summary render on
# Windows consoles (cp1252 by default) without UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def _ancestors(start: str):
    current = os.path.abspath(start)
    while True:
        parent = os.path.dirname(current)
        if parent == current:
            break
        yield parent
        current = parent


def _config_path() -> str:
    """Return shared_vault.path from plugin config if enabled, else empty."""
    here = os.path.dirname(os.path.abspath(__file__))

    # 1. default_config.yaml in the plugin directory
    default_cfg = os.path.join(here, "default_config.yaml")
    if os.path.isfile(default_cfg) and yaml is not None:
        with open(default_cfg, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        sv = cfg.get("shared_vault", {})
        if sv.get("enabled") and sv.get("path"):
            return sv["path"]

    # 2. plugin-specific config.json (overrides default_config.yaml)
    plugin_cfg = os.path.join(here, "config.json")
    if os.path.isfile(plugin_cfg):
        with open(plugin_cfg, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        sv = cfg.get("shared_vault", {})
        if sv.get("enabled") and sv.get("path"):
            return sv["path"]

    # 3. per-project config.json
    for root in (os.getcwd(), here):
        for parent in [root] + list(_ancestors(root)):
            proj_cfg = os.path.join(parent, ".a0proj", "plugins", "llm_wiki", "config.json")
            if os.path.isfile(proj_cfg):
                with open(proj_cfg, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                sv = cfg.get("shared_vault", {})
                if sv.get("enabled") and sv.get("path"):
                    return sv["path"]
                break  # stop at first .a0proj found in this root

    return ""


def find_vault(explicit: str = "") -> str:
    candidates = []

    # 0. explicit argument
    if explicit:
        candidates.append(explicit)

    # 1. plugin config (default_config.yaml or per-project config.json)
    cfg_path = _config_path()
    if cfg_path:
        candidates.append(cfg_path)

    # 2. auto-detect: active project root and ancestor directories
    here = os.path.dirname(os.path.abspath(__file__))
    # Plugin lives at <install>/usr/plugins/llm_wiki/ — vault may be at
    # project root, Agent Zero install root, or a parent directory.
    for rel in (("..", "..", "..", "SharedBrain"),
                ("..", "..", "SharedBrain"),
                ("..", "SharedBrain")):
        candidates.append(os.path.abspath(os.path.join(here, *rel)))
    candidates.append(os.path.abspath(os.path.join(os.getcwd(), "SharedBrain")))

    # 3. $SHARED_BRAIN environment variable (override / fallback)
    env = os.environ.get("SHARED_BRAIN", "")
    if env:
        candidates.append(env)

    # 4. Current working directory (last resort)
    candidates.append(os.getcwd())

    for c in candidates:
        if os.path.isfile(os.path.join(c, "registry.yaml")):
            return c
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="llm_wiki smoke test")
    parser.add_argument("path", nargs="?", default="", help="Path to SharedBrain vault")
    parser.add_argument("--agent-id", default="agent_zero",
                        help="Agent id to simulate (default: agent_zero)")
    args = parser.parse_args()

    print("LLM Wiki — smoke test")
    print("=" * 60)

    vault = find_vault(args.path)
    if not vault:
        print("FAIL: no SharedBrain vault found.")
        print("Set $SHARED_BRAIN, pass the path as an argument, or check")
        print("shared_vault.path in default_config.yaml / .a0proj config.json.")
        print()
        # Offer interactive reconfiguration when running in a real TTY
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                ans = input("Run vault setup wizard now? [y/N]: ").strip().lower()
                if ans in ("y", "yes"):
                    here = os.path.dirname(os.path.abspath(__file__))
                    init_script = os.path.join(here, "initialize.py")
                    if os.path.isfile(init_script):
                        print()
                        # Re-execute ourselves via the wizard
                        import subprocess
                        subprocess.call([sys.executable, init_script, "--reconfigure"])
                        # After wizard completes, re-run smoke test once
                        print()
                        print("Re-running smoke test ...")
                        print()
                        return main()
            except (EOFError, KeyboardInterrupt):
                pass
        return 1

    print(f"Vault root: {vault}")

    # Load the registry module directly (no Agent Zero runtime required)
    tools_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
    sys.path.insert(0, tools_dir)
    try:
        from wiki_registry import WikiRegistry  # type: ignore
    except Exception as e:
        print(f"FAIL: could not import wiki_registry: {e}")
        return 1

    reg = WikiRegistry.from_config(
        plugin_config={"shared_vault": {"enabled": True, "path": vault}},
        agent_id=args.agent_id,
    )
    if reg is None:
        print("FAIL: WikiRegistry.from_config returned None.")
        return 1

    print()
    print(reg.summary())
    print()

    n_wikis = len(reg.list_wikis())
    n_read = len(reg.readable_wikis())
    n_write = len(reg.writable_wikis())

    print(f"Stats: {n_wikis} wikis | {n_read} readable | {n_write} writable (by `{args.agent_id}`)")
    print()

    # Git status
    is_git = reg.is_git_repo()
    print(f"Vault is git repo: {is_git}")
    if not is_git:
        print("  (hint: `cd " + vault + " && git init` to enable auto-commit)")

    print()
    print("OK — plugin configuration looks healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
