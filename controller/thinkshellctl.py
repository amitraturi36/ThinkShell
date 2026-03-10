#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def _bootstrap_import_path() -> None:
    """
    Ensure project root is importable regardless of invocation location.
    Works for:
      - installed binary layout
      - dev repo layout
      - symlink execution
    """
    try:
        current = Path(__file__).resolve()
        project_root = current.parent.parent
        sys.path.insert(0, str(project_root))
    except Exception as e:
        print(f"[ThinkShell] Path bootstrap failed: {e}", file=sys.stderr)
        sys.exit(1)


_bootstrap_import_path()


# Import AFTER path bootstrap
try:
    import llm_engine
except Exception as e:
    print(f"[ThinkShell] Import failed: {e}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    """
    Controller entrypoint invoked by shell hooks.

    Usage:
        thinkshellctl.py FAIL "<original command>"
    """
    if os.environ.get("THINKSHELL_ACTIVE") == "1":
        return 0
    if len(sys.argv) < 3:
        # Do NOT print to stdout — this breaks shell contract.
        print("[ThinkShell] Invalid invocation.", file=sys.stderr)
        return 1

    mode = sys.argv[1]

    # Preserve full original command (handles quoted args safely)
    command = " ".join(sys.argv[2:]).strip()

    if not command:
        print("[ThinkShell] Empty command received.", file=sys.stderr)
        return 1

    if mode != "FAIL":
        print(f"[ThinkShell] Unsupported mode: {mode}", file=sys.stderr)
        return 1

    try:
        fix = llm_engine.get_bash_command(command)

        # IMPORTANT:
        # Only print the command to stdout — nothing else.
        if fix:
            sys.stdout.write(fix.strip() + "\n")
            sys.stdout.flush()
            return 0

        return 1

    except Exception as e:
        print(f"echo '[ThinkShell] Execution error:{e}'")
        return 0


if __name__ == "__main__":
    sys.exit(main())