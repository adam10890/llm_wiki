"""
LLM Wiki — one-time initialization / vault reconfiguration wizard.

No external dependencies needed — this plugin uses only stdlib.

This script runs:
  - Automatically when the plugin is first installed (via Plugin List → Init).
  - Manually via `python initialize.py` or `python initialize.py --reconfigure`
    to point the plugin at a different SharedBrain vault.

Workflow:
  1. Auto-detect existing SharedBrain vaults in common locations.
  2. Present them to the user; allow manual path entry.
  3. Validate the chosen path contains a registry.yaml.
  4. Write the path into the plugin's config.json (shared_vault.path).
"""
import json
import os
import sys


# ---------------------------------------------------------------------------
# Auto-detect helpers
# ---------------------------------------------------------------------------

def _is_vault(path: str) -> bool:
    return path and os.path.isdir(path) and os.path.isfile(
        os.path.join(path, "registry.yaml")
    )


def _common_vault_candidates():
    """Yield likely vault locations in priority order."""
    # 1. Environment override
    env = os.environ.get("SHARED_BRAIN", "")
    if env:
        yield env, "$SHARED_BRAIN"

    # 2. Parent directories of the Agent Zero install (container + host layouts)
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (
        ("..", "..", "..", "SharedBrain"),
        ("..", "..", "SharedBrain"),
        ("..", "SharedBrain"),
        ("..", "..", "..", "..", "SharedBrain"),
    ):
        p = os.path.abspath(os.path.join(here, *rel))
        if _is_vault(p):
            yield p, "auto-detect (near A0 install)"

    # 3. Common host paths (Windows + Linux/macOS)
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "SharedBrain"),
        os.path.join(home, "Documents", "SharedBrain"),
        os.path.join(home, "agent-zero", "SharedBrain"),
        os.path.join(os.path.dirname(home), "SharedBrain"),  # sibling of home on Windows
        "/data/SharedBrain",
    ]
    for p in candidates:
        if _is_vault(p):
            yield p, "common location"

    # 4. If the current working directory is a vault itself
    if _is_vault(os.getcwd()):
        yield os.getcwd(), "current directory"


# ---------------------------------------------------------------------------
# Interactive prompt (works in any terminal — Docker, IDE, bare shell)
# ---------------------------------------------------------------------------

def _readline(prompt: str, default: str = "") -> str:
    full = f"{prompt} [{default}]: " if default else f"{prompt}: "
    try:
        raw = input(full)
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)
    return raw.strip() or default


def _pick_vault() -> str:
    found = list(_common_vault_candidates())

    print("=" * 60)
    print("LLM Wiki — Vault Setup Wizard")
    print("=" * 60)
    print()

    if found:
        print("Detected SharedBrain vault(s):")
        for i, (path, src) in enumerate(found, start=1):
            print(f"  {i}. {path}  ({src})")
        print(f"  {len(found) + 1}. Enter a custom path manually")
        print()
        choice = _readline("Choose option", str(1 if len(found) == 1 else ""))
        try:
            idx = int(choice)
            if 1 <= idx <= len(found):
                return found[idx - 1][0]
        except ValueError:
            pass
        # fall through to manual entry
    else:
        print("No existing SharedBrain vault detected automatically.")
        print()

    # Manual entry loop
    while True:
        manual = _readline("Enter absolute path to your SharedBrain vault")
        manual = os.path.expanduser(manual)
        if _is_vault(manual):
            return manual
        if os.path.isdir(manual):
            print("  That directory exists but does NOT contain registry.yaml.")
            print("  A valid vault must have a registry.yaml at its root.")
        else:
            print("  Directory not found.")
        retry = _readline("Try again? (y/n)", "y")
        if retry.lower() not in ("y", "yes"):
            print("Setup aborted. You can re-run with --reconfigure later.")
            sys.exit(1)


def _write_config(vault_path: str):
    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(here, "config.json")

    # Load existing or start from default structure
    cfg: dict = {}
    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

    cfg["shared_vault"] = {
        "enabled": True,
        "path": vault_path,
    }

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Saved vault path to {cfg_path}")
    print(f"  shared_vault.path = {vault_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="LLM Wiki vault setup wizard")
    parser.add_argument("--reconfigure", action="store_true",
                        help="Change the vault path after initial setup")
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(here, "config.json")
    existing = ""
    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            existing = json.load(f).get("shared_vault", {}).get("path", "")

    if existing and not args.reconfigure:
        print(f"Vault already configured: {existing}")
        print("Run `python initialize.py --reconfigure` to change it.")
        print("Running smoke test ...")
        print()
        # Delegate to execute.py for a quick health check
        import subprocess
        smoke = os.path.join(here, "execute.py")
        if os.path.isfile(smoke):
            subprocess.call([sys.executable, smoke])
        return 0

    # Wizard
    vault = _pick_vault()
    print()
    print(f"Selected vault: {vault}")
    print()
    _write_config(vault)
    print()
    print("Setup complete. The plugin will now use this vault.")
    print("You can re-run with --reconfigure at any time to switch vaults.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
