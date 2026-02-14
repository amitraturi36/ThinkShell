#!/usr/bin/env python3
import sys
import os
from pathlib import Path



project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
# Now we can safely try to import
try:
    import llm_engine
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        return

    mode = sys.argv[1]  # "FAIL"
    command = sys.argv[2]  # "list all files"
    if mode == "FAIL":
        fix = llm_engine.get_bash_command(command)
        print(f"echo '{fix}';")


if __name__ == "__main__":
    main()
