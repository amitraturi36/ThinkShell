#!/usr/bin/env python3
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Now we can safely try to import
try:
    import llm_engine
except ImportError:
    llm_engine = None
def call_llm_fix(bad_cmd):
    # LOGIC:
    # 1. User typed: "list files"
    # 2. Return: "echo '🤖 Running ls -la'; ls -la"

    cmd = bad_cmd.lower()

    if "list" in cmd and "files" in cmd:
        return "echo '🔍 Auto-running ls -la'; ls -la"

    elif "ip" in cmd and "address" in cmd:
        return "ifconfig | grep inet"

    # If we truly don't know, return EMPTY string so we don't loop forever.
    return ""

def main():
    if len(sys.argv) < 3:
        return

    mode = sys.argv[1]    # "FAIL"
    command = sys.argv[2] # "list all files"

    if mode == "FAIL":
        if llm_engine:
            fix = llm_engine.get_bash_command(command)
            print(f"echo '🤖 Agent: {fix}'; {fix}")
        else:
            fix = call_llm_fix(command)
            print(fix)

if __name__ == "__main__":
    main()
