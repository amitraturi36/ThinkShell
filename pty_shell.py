import os
import pty
import sys
import tempfile
import atexit
import shutil
import uuid
from pathlib import Path

def get_controller_path():
    """
    Robustly finds the controller script path.
    Prioritizes the current directory structure but falls back gracefully.
    """
    # 1. Anchor to the directory containing THIS file
    current_script_dir = Path(__file__).resolve().parent

    # 2. Look for thinkshellctl.py in the same directory (Binary/Flat layout)
    candidate = current_script_dir / "thinkshellctl.py"
    if candidate.exists():
        return str(candidate)

    # 3. Look in 'controller' subdirectory (Dev layout)
    candidate = current_script_dir / "controller" / "thinkshellctl.py"
    if candidate.exists():
        return str(candidate)

    # 4. Fallback: Current Working Directory
    cwd_candidate = Path.cwd() / "thinkshellctl.py"
    if cwd_candidate.exists():
        return str(cwd_candidate)

    # Return valid path structure even if missing to allow explicit shell errors
    return str(current_script_dir / "thinkshellctl.py")

def spawn_shell():
    """
    Spawns the user's preferred shell (Bash) in a pseudo-terminal (PTY).
    Injects ThinkShell hooks while preserving the user's login environment
    (sdkman, pyenv, nvm, etc.).
    """
    # Create the custom RC file
    rc_path = _create_bashrc()

    # Fork the PTY
    # pty.fork() handles openpty(), fork(), login_tty(), and setsid() internally.
    pid, fd = pty.fork()

    if pid == 0:
        # --- CHILD PROCESS ---
        try:
            # 1. Set Controller Environment Variables
            os.environ["TS_CTL"] = get_controller_path()
            os.environ["TS_PY"] = sys.executable
            if "THINKSHELL_SESSION_ID" not in os.environ:
                os.environ["THINKSHELL_SESSION_ID"] = str(uuid.uuid4())

            # Note: Do NOT call os.setsid() here. pty.fork() does it automatically.
            # Calling it again causes [Errno 1] Operation not permitted.

            # 2. Locate Bash
            # We explicitly prefer Homebrew/Local bash over system bash (macOS often has old bash)
            bash_bin = "/bin/bash"
            if os.path.exists("/opt/homebrew/bin/bash"):
                bash_bin = "/opt/homebrew/bin/bash"
            elif os.path.exists("/usr/local/bin/bash"):
                bash_bin = "/usr/local/bin/bash"
            elif shutil.which("bash"):
                bash_bin = shutil.which("bash")

            # 3. Execute Shell
            # -i: Interactive
            # --rcfile: Force our custom config
            # Note: We do NOT use --noprofile because we manually source profiles in the rcfile.
            os.execvp(bash_bin, [bash_bin, "--rcfile", rc_path, "-i"])

        except Exception as e:
            # Last resort error reporting if exec fails
            # We use os.write to ensure output even if sys.stderr is mangled
            os.write(2, f"FATAL: Failed to spawn shell: {e}\n".encode())
            os._exit(1)

    # --- PARENT PROCESS ---
    return pid, fd

def _create_bashrc():
    """
    Generates a temporary bash configuration file.
    This file acts as a bridge: it loads the user's standard environment
    (to fix missing tools) and then injects the ThinkShell AI hooks.
    """

    # We use a raw string (r) to prevent Python from escaping bash backslashes
    bashrc_content = r"""
# ---- ThinkShell Environment Loader ----

# 1. Recursion Guard
if [ -n "$THINKSHELL_ACTIVE" ]; then
    return
fi
export THINKSHELL_ACTIVE=1

# 2. Load System & User Profiles (The "Login Shell" Simulation)
# This fixes issues where tools like sdkman, nvm, or pyenv are missing.
# We source these explicitly because 'bash --rcfile' skips them.

if [ -f /etc/profile ]; then source /etc/profile; fi

# Source the first available login profile
if [ -f "$HOME/.bash_profile" ]; then
    source "$HOME/.bash_profile"
elif [ -f "$HOME/.bash_login" ]; then
    source "$HOME/.bash_login"
elif [ -f "$HOME/.profile" ]; then
    source "$HOME/.profile"
fi

# 3. Load Interactive Config (.bashrc)
# Only source if it hasn't been sourced yet (common in .bash_profile)
# We check a common guard variable or just rely on idempotency, 
# but explicitly sourcing it ensures aliases work.
if [ -f "$HOME/.bashrc" ] && [ -z "$__BASHRC_SOURCED__" ]; then
    source "$HOME/.bashrc"
fi

# ---- ThinkShell AI Hooks ----

# Hook for Bash 4.0+ (Linux, Homebrew Bash)
if [ -n "${BASH_VERSINFO:-}" ] && ((BASH_VERSINFO[0] >= 4)); then
    command_not_found_handle() {
        local cmd="$1"
        shift
        local args="$@"
        local full_cmd="$cmd $args"

        # Query the Python Controller
        local agent_response
        agent_response=$("$TS_PY" "$TS_CTL" "FAIL" "$full_cmd")

        if [ -n "$agent_response" ]; then
            # Inject into history so 'Up Arrow' works
            history -s "$agent_response"
            # Execute the suggestion
            eval "$agent_response"
            # Implicitly return the exit code of the evaluated command
        else
            # Fallback to standard error
            echo "bash: $cmd: command not found"
            return 127
        fi
    }
fi

# Hook for Bash 3.x (Standard macOS /bin/bash)
if [ -n "${BASH_VERSINFO:-}" ] && ((BASH_VERSINFO[0] < 4)); then
    _ts_auto_fix() {
        # Check if previous command failed with 'Command not found' (127)
        if [ $? -eq 127 ]; then
             # Grab the last command from history
             local last=$(history 1 | sed 's/^[ ]*[0-9]*[ ]*//')
             [ -z "$last" ] && return

             # Query Controller
             local fix=$("$TS_PY" "$TS_CTL" "FAIL" "$last")

             if [ -n "$fix" ]; then
                echo "ThinkShell suggestion: $fix"
                eval "$fix"
             fi
        fi
    }

    # Prepend to PROMPT_COMMAND to run after every command
    if [ -n "$PROMPT_COMMAND" ]; then
        export PROMPT_COMMAND="_ts_auto_fix; $PROMPT_COMMAND"
    else
        export PROMPT_COMMAND="_ts_auto_fix"
    fi
fi

# 4. Visual Indicator (Optional override, keep user custom prompt if preferred)
# Only set if PS1 is default-ish, otherwise append a marker?
# For now, we force the indicator so the user knows they are in ThinkShell.
PS1="\[\033[1;34m\]ThinkShell\[\033[0m\] $ "
"""

    # Create a persistent temp file.
    # We set delete=False because the subprocess (bash) needs to read it.
    tf = tempfile.NamedTemporaryFile(mode="w", delete=False, prefix="thinkshell_rc_", suffix=".bash")
    tf.write(bashrc_content)
    tf.close()

    # Register cleanup to run when the Python script exits
    def cleanup_rc():
        try:
            if os.path.exists(tf.name):
                os.unlink(tf.name)
        except OSError:
            pass

    atexit.register(cleanup_rc)

    return tf.name
