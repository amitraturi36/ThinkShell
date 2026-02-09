import os
import pty
import sys
import tempfile
from pathlib import Path

def get_controller_path():
    """
    Robustly finds the controller script.
    Works in:
    1. Dev mode (current dir)
    2. Installed mode (~/.thinkshell)
    3. Frozen/Binary mode
    """
    # 1. Get the directory containing THIS file (pty_shell.py)
    # This is the most reliable anchor.
    current_script_dir = Path(__file__).resolve().parent

    # 2. Look for thinkshellctl.py in the same directory
    candidate = current_script_dir / "thinkshellctl.py"

    if candidate.exists():
        return str(candidate)

    # 3. Fallback: Look in 'controller' subdirectory (Dev structure)
    candidate = current_script_dir / "controller" / "thinkshellctl.py"
    if candidate.exists():
        return str(candidate)

    # 4. Fallback: Current Working Directory (last resort)
    cwd_candidate = Path.cwd() / "thinkshellctl.py"
    if cwd_candidate.exists():
        return str(cwd_candidate)

    # If we are here, installation is broken.
    # Return a path that will likely error out clearly
    return str(current_script_dir / "thinkshellctl.py")

def spawn_shell():
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.environ["TS_CTL"] = get_controller_path()
            os.environ["TS_PY"] = sys.executable
            rc_path = _create_bashrc()
            # Try to find a modern bash first
            bash_bin = "/bin/bash"
            if os.path.exists("/opt/homebrew/bin/bash"): bash_bin = "/opt/homebrew/bin/bash"
            elif os.path.exists("/usr/local/bin/bash"): bash_bin = "/usr/local/bin/bash"

            os.execvp(bash_bin, ["bash", "--noprofile", "--rcfile", rc_path, "-i"])
        except:
            os._exit(1)
    return pid, fd

def _create_bashrc():
    bashrc = """
[ -f /etc/bashrc ] && source /etc/bashrc
[ -f ~/.bashrc ] && source ~/.bashrc

# --- THE MAGIC HOOK (Requires Bash 4+) ---
# This runs INSTEAD of printing "command not found"
command_not_found_handle() {
    local cmd="$1"
    shift
    local args="$@"
    local full_cmd="$cmd $args"

    # Call Python Agent with "FAIL" mode
    local agent_response
    agent_response=$("$TS_PY" "$TS_CTL" "FAIL" "$full_cmd")
    
    if [ -n "$agent_response" ]; then
        # Agent found a fix! Run it.
        eval "$agent_response"
        return 0
    else
        # Agent gave up. Print the standard error manually.
        echo "bash: $cmd: command not found"
        return 127
    fi
}

# Fallback for old Bash (Mac default)
if ((BASH_VERSINFO[0] < 4)); then
    _ts_auto_fix() {
        if [ $? -eq 127 ]; then
             local last=$(history 1 | sed 's/^[ ]*[0-9]*[ ]*//')
             [ -z "$last" ] && return
             local fix=$("$TS_PY" "$TS_CTL" "FAIL" "$last")
             [ -n "$fix" ] && eval "$fix"
        fi
    }
    export PROMPT_COMMAND="_ts_auto_fix; $PROMPT_COMMAND"
fi

PS1="\\[\\033[1;34m\\]ThinkShell\\[\\033[0m\\] $ "
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(bashrc)
    return f.name
