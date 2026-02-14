import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import platform
from openai import OpenAI

SYSTEM_PROMPT = """
You are an AI File-Aware Developer Platform Bash Decision Agent for All Operating Systems.

Analyze USER_INPUT and return a SINGLE valid JSON object. NO markdown, explanations, or comments.

--------------------------------
JSON SCHEMA
--------------------------------
{
  "action": "INSPECT" | "EXECUTE" | "REVIEW" | "ASK" | "UPLOAD" | "BLOCK",
  "commands": [string],
  "reason": string | null
}

--------------------------------
ACTIONS
--------------------------------

INSPECT (reason = null)
  INSPECT (internal-only) : 
    Used ONLY when the agent must gather missing system state before it can safely respond.
    INSPECT is NEVER used to fulfill a user request directly.
    If the user explicitly asks to run a read-only command (ls, cat, docker ps, etc.),
    that is EXECUTE, not INSPECT.
    INSPECT is for: 
        verifying tool existence before install
        checking environment before deployment
        confirming file presence before modification
    INSPECT is NOT for:
        showing information the user explicitly requested
        running general shell queries on behalf of the user

EXECUTE (reason = null)
  Safe, complete commands. Must not block or require interaction.
  Examples: docker run -d, pip install pandas, npm start
  Never: inspections, destructive ops

REVIEW (reason = required)
  Destructive/impactful operations requiring user confirmation.
  Includes: rm -rf, service restart, cloud ops (terraform apply, kubectl delete), 
  DB mutations (DROP, DELETE), sudo, bulk operations
  reason must explain risk + suggest rollback if applicable

ASK (commands = [], reason = required)
  Missing info or ambiguity. Ask ONE focused question with context.
  Examples: unclear version, missing path, ambiguous environment

UPLOAD (commands = file paths only, reason = required)
  Semantic file analysis needed. Max 10 files, prefer smallest relevant.
  commands: explicit paths only - NO globs, dirs, shell commands
  Never upload: ~/.ssh/*, .env, *.key, *.pem, credentials, secrets
  Check size first (INSPECT) if >10MB. For logs, try tail first.
  reason: briefly explain why content analysis needed

BLOCK (commands = [], reason = "Action blocked")
  Clearly unsafe: accessing secrets, malware, privilege exploits, data exfiltration

--------------------------------
CRITICAL RULES
--------------------------------
1. Return EXACTLY one JSON object per response
2. NEVER mix action types (no INSPECT + EXECUTE)
3. NEVER use sudo without explicit user request
4. NEVER assume state - INSPECT first if uncertain
5. Commands must be POSIX-compatible (bash/zsh)
6. Quote variables properly: "$var" not $var
7. Use $() not backticks for substitution

DOCKER: Check availability first, reuse existing, use -d mode, name containers (--name)
FILES: INSPECT existence before UPLOAD. Paths must be explicit and singular.
PYTHON: Never inline >3 lines with `python -c`. Create .py file instead.
WRITING: Use printf per line OR temp file. Preserve indentation.

--------------------------------
DECISION FLOW
--------------------------------
1. Destructive/unsafe? → BLOCK
2. Missing critical info? → ASK
3. Need file content analysis? → UPLOAD
4. Discovery/inspection? → INSPECT
5. Destructive but valid? → REVIEW
6. Safe execution? → EXECUTE

Keywords: "delete/destroy/kill" → likely REVIEW/BLOCK
         "check/show/list" → likely INSPECT
         "install/run/build" → likely EXECUTE (if safe) or REVIEW
         "why/debug/analyze file" → likely UPLOAD

--------------------------------
MULTI-STEP FILE FLOW
--------------------------------
1. Request analysis → UPLOAD with paths
2. System provides file_ids
3. Analyze using file_ids (NEVER re-request same files)
4. Continue with INSPECT/EXECUTE/REVIEW as needed

--------------------------------
TOOLING (VERSION MANAGERS FIRST)
--------------------------------
JAVA/JVM: Use SDKMAN. Check: command -v sdk. Install: curl -s "https://get.sdkman.io" | bash
  Tools: Java, Gradle, Maven, Kotlin, Scala
  
PYTHON: Use venv/virtualenv. Check: command -v python3. Prefer pip in venv.
  Never modify system Python without explicit request.

NODE: Use nvm. Check: command -v node. Prefer local packages over global.

DOCKER: Check daemon: docker ps. Reuse containers. Use official images.

TERRAFORM: Check: terraform version. Plan before apply. apply/destroy → REVIEW

KUBERNETES: Verify context: kubectl config current-context
  get/describe → INSPECT. apply/delete/scale → REVIEW

AWS: Verify creds: aws sts get-caller-identity
  Reads → EXECUTE. Deletions/IAM → REVIEW. NEVER expose secrets.

GIT: status/log → INSPECT. commit/push → EXECUTE. force-push/rebase → REVIEW

DATABASE: SELECT → EXECUTE. INSERT/UPDATE → EXECUTE (dev) or REVIEW (prod).
  DROP/DELETE/TRUNCATE → REVIEW always

--------------------------------
EDGE CASES
--------------------------------
"Install X" without version → ASK for version if choice matters, else use latest
"Deploy" without env → ASK which environment
"Delete all" → REVIEW with scope, suggest backup
"Check config" → ASK which config file
Missing tool → INSPECT first, propose installation
Permission errors → Suggest sudo in reason, ASK confirmation
Large operations → REVIEW with count/scope
Ambiguous file refs → ASK for explicit path
Interactive commands (vim, top) → EXECUTE if clearly intended, else ASK

--------------------------------
PLATFORM HANDLING
--------------------------------
Detect OS if needed: uname -s
Portable commands preferred. Handle Linux/macOS differences:
  stat: Use stat -c (Linux) or stat -f (macOS) - detect first
  sed: Use -i '' for macOS, -i for Linux
Check disk space before large ops: df -h
Check resources if intensive: free -h, top

--------------------------------
SECURITY
--------------------------------
Never upload/expose: SSH keys, .env, credentials, AWS keys, tokens
Validate paths before rm/mv/dangerous ops
Use secure permissions: chmod 600 for sensitive files
Environment vars for secrets, not CLI args
Sanitize user input in commands

--------------------------------
ERROR HANDLING
--------------------------------
Check exit codes for critical ops: || exit 1
Use set -e in scripts (exit on error)
Meaningful errors to stderr: echo "Error: ..." >&2
Clean temp resources on failure: trap cleanup
Log appropriately (stdout vs stderr)

--------------------------------
VALIDATION CHECKLIST
--------------------------------
✓ Valid JSON (no markdown, no text outside JSON)
✓ action is valid enum value
✓ commands matches action (empty for ASK/BLOCK, paths only for UPLOAD)
✓ reason follows rules (null for INSPECT/EXECUTE, required for others)
✓ No mixed actions
✓ Commands are complete and executable
✓ Security rules respected

--------------------------------
EXAMPLES
--------------------------------

USER: "Check if Docker is running"
{"action": "INSPECT", "commands": ["docker ps"], "reason": null}

USER: "Install latest Node.js"
{"action": "INSPECT", "commands": ["command -v nvm"], "reason": null}

USER: "Delete all log files"
{"action": "REVIEW", "commands": ["find /var/log -name '*.log' -type f -delete"], "reason": "This will permanently delete all .log files in /var/log. Suggest backing up first: tar -czf logs-backup.tar.gz /var/log/*.log"}

USER: "Install Java"
{"action": "ASK", "commands": [], "reason": "Which Java version? (11, 17, 21, or latest LTS). Will use SDKMAN for installation."}

USER: "Debug script.py - it crashes"
{"action": "UPLOAD", "commands": ["script.py"], "reason": "Need to analyze Python code to identify crash cause"}

USER: "Show me AWS secret keys"
{"action": "BLOCK", "commands": [], "reason": "Action blocked"}

USER: "Scale k8s deployment to 5"
{"action": "REVIEW", "commands": ["kubectl scale deployment/my-app --replicas=5"], "reason": "Will scale deployment to 5 replicas. Verify cluster context first: kubectl config current-context"}

USER: "Create React app"
First: {"action": "INSPECT", "commands": ["command -v npx", "node --version"], "reason": null}
Then: {"action": "EXECUTE", "commands": ["npx create-react-app my-app"], "reason": null}

USER: "Why is app slow? Check logs"
First: {"action": "INSPECT", "commands": ["tail -n 100 /var/log/app.log"], "reason": null}
If insufficient: {"action": "UPLOAD", "commands": ["/var/log/app.log"], "reason": "Need full log analysis to identify performance bottlenecks"}

--------------------------------
REMEMBER
--------------------------------
- Be deterministic and explicit
- Safety > convenience
- INSPECT before assuming
- ASK rather than guess
- One JSON object, nothing else
- Preserve security boundaries
- Prefer boring over clever
- Return EXACTLY one JSON object per response
- NEVER execute destructive commands on relative paths without resolving them to an absolute path first.
- If resolved path is '/', BLOCK immediately.
- Treat '.', './', '../', or empty paths as UNKNOWN until inspected.
""".strip()
client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"]
)

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-nano")

# ---------------- Runtime Guard ---------------- #

FORBIDDEN_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r">\s*/$",
    r"\|\s*(sh|bash|zsh)\b",
    r":\(\)\s*\{.*\|\s*&\s*\};:",
    r"\bchmod\s+-R\s+777\s+/\b",
    r"\bmv\s+/\b",
    r">\s*/dev/sd[a-z]",
]

SENSITIVE_UPLOAD_PATTERNS = [
    r"(^|/)\.ssh(/|$)",
    r"(^|/)\.aws(/|$)",
    r"(^|/)\.gnupg(/|$)",
    r"(^|/)\.env$",
    r"\.pem$",
    r"\.key$",
    r"id_rsa$",
    r"id_ed25519$",
]

MAX_UPLOAD_FILES = 10
MAX_UPLOAD_BYTES_PER_FILE = 250_000  # keep prompts small-ish

OS_INFO = {
    "OSName": platform.system(),
    "OSVersion": platform.version(),
    "Release": platform.release(),
    "Machine": platform.machine(),
    "Processor": platform.processor()
}


def _bash_quote(s: str) -> str:
    return shlex.quote(s)


def _get_openai_key() -> str | None:
    # Support both env var names used in this repo.
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAIAPIKEY")


def is_runtime_safe(cmd: str) -> bool:
    """Hard safety gate: no reasoning, just block known foot-guns."""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, cmd):
            return False
    return True


def _is_sensitive_upload_path(p: str) -> bool:
    norm = p.replace("\\", "/")
    for pat in SENSITIVE_UPLOAD_PATTERNS:
        if re.search(pat, norm):
            return True
    return False


def _read_upload_file(path: str) -> dict:
    """Return a JSON-serializable payload for a single file."""
    if _is_sensitive_upload_path(path):
        return {"error": "Blocked: path looks sensitive (.ssh/.env/keys)."}

    p = Path(path).expanduser()
    try:
        rp = p.resolve()
    except Exception:
        rp = p

    if not p.exists():
        return {"error": "Not found."}

    if p.is_dir():
        return {"error": "Is a directory; provide an explicit file path."}

    try:
        size = p.stat().st_size
    except Exception as e:
        return {"error": f"Could not stat file: {e}"}

    if size > MAX_UPLOAD_BYTES_PER_FILE:
        # Read a head+tail sample rather than failing hard.
        try:
            data = p.read_bytes()
            head = data[:120_000]
            tail = data[-120_000:] if len(data) > 120_000 else b""
            text = (head + (b"\n\n...TRUNCATED...\n\n" if tail else b"") + tail).decode("utf-8", errors="replace")
            return {"size": size, "truncated": True, "content": text}
        except Exception as e:
            return {"error": f"Could not read file: {e}"}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return {"size": size, "truncated": False, "content": text}
    except Exception:
        try:
            data = p.read_bytes()
            return {"size": size, "truncated": False, "content": data.decode("utf-8", errors="replace")}
        except Exception as e:
            return {"error": f"Could not read file: {e}"}


def run_command(cmd: str) -> str:
    # Used only for INSPECT steps (internal state gathering).
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (result.stdout + result.stderr).strip()[:4000]
    except Exception as e:
        return f"ERROR: {str(e)}"


def call_llm(messages: list[dict]) -> dict:
    key = _get_openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def safe_echo(msg: str) -> str:
    return "echo " + json.dumps(msg)


def normalize_commands(cmds) -> list[str]:
    if not isinstance(cmds, list):
        return []
    return [c for c in cmds if isinstance(c, str) and c.strip()]


def _interactive_review_snippet(reason: str, commands: list[str]) -> str:
    # Build a bash snippet that prints context and asks the user before executing.
    lines: list[str] = []
    lines.append(f"printf '%s\\n' {_bash_quote('Review required: ' + (reason or 'Confirmation needed.'))}")
    lines.append("printf '%s\\n' 'Proposed commands:'")
    for cmd in commands:
        lines.append(f"printf '  %s\\n' {_bash_quote(cmd)}")

    # Safety gate again before emitting runnable code.
    for cmd in commands:
        if not is_runtime_safe(cmd):
            return safe_echo("Execution blocked by runtime safety guard.")

    lines.append("read -r -p 'Proceed? [y/N] ' TS_PROCEED")
    lines.append("case \"$TS_PROCEED\" in")
    lines.append("  y|Y|yes|YES)")
    lines.append("    set -e")
    for cmd in commands:
        lines.append(f"    {cmd}")
    lines.append("    ;;")
    lines.append("  *) echo 'Aborted.' ;;")
    lines.append("esac")
    return "\n".join(lines)


def _interactive_ask_snippet(original_intent: str, question: str) -> str:
    # Ask one question, then re-call the controller with the answer appended.
    q = question or "Need more information."
    lines: list[str] = []
    lines.append(f"printf '%s\\n' {_bash_quote(q)}")
    lines.append("read -r -p '> ' TS_ANSWER")
    lines.append(f"TS_FOLLOWUP={_bash_quote(original_intent)}")
    lines.append('TS_NEW_QUERY="$TS_FOLLOWUP\n\nUSER_ANSWER: $TS_ANSWER"')
    lines.append('agentresponse="$($TSPY $TSCTL FAIL \"$TS_NEW_QUERY\")"')
    lines.append('if [ -n "$agentresponse" ]; then eval "$agentresponse"; fi')
    return "\n".join(lines)


def ai_terminal(user_input: str) -> str:
    """Return bash code that the shell will eval."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"OS_INFO: {OS_INFO}"},
        {"role": "system", "content": f"ORIGINAL_INTENT: {user_input}"},
    ]

    MAX_STEPS = 12
    seen_inspects: set[str] = set()
    uploaded_files: set[str] = set()

    for _ in range(MAX_STEPS):
        llm_response = call_llm(messages)
        messages.append({"role": "assistant", "content": json.dumps(llm_response, ensure_ascii=False)})

        action = str(llm_response.get("action", "")).upper().strip()
        commands = normalize_commands(llm_response.get("commands", []))
        reason = llm_response.get("reason")

        if action == "INSPECT":
            inspection_output: dict[str, str] = {}
            for cmd in commands:
                if cmd in seen_inspects:
                    inspection_output[cmd] = "ERROR: repeated inspection detected"
                    continue
                if not is_runtime_safe(cmd):
                    inspection_output[cmd] = "BLOCKED: runtime safety guard"
                    continue
                print(f"echo 'Inspecting command: {cmd}'")
                inspection_output[cmd] = run_command(cmd)
                seen_inspects.add(cmd)

            messages.append(
                {"role": "system", "content": f"INSPECTION_RESULT: {json.dumps(inspection_output, ensure_ascii=False)}"}
            )
            continue

        if action == "UPLOAD":
            payload: dict[str, dict] = {}
            for path in commands[:MAX_UPLOAD_FILES]:
                if path in uploaded_files:
                    continue
                payload[path] = _read_upload_file(path)
                uploaded_files.add(path)
            print(f"echo 'Uploading file {path}'")
            messages.append(
                {"role": "system", "content": f"UPLOADED_FILES: {json.dumps(payload, ensure_ascii=False)}"}
            )
            continue

        if action == "ASK":
            return _interactive_ask_snippet(user_input, str(reason or ""))

        if action == "REVIEW":
            return _interactive_review_snippet(str(reason or ""), commands)

        if action == "EXECUTE":
            result = []
            for cmd in commands:
                if not is_runtime_safe(cmd):
                    return safe_echo("Execution blocked by runtime safety guard, for command : " + cmd)
                else:
                    print(f"echo 'Executing command : {cmd}'")
                    result.append(run_command(cmd))
            # Execute in the user's shell so stateful operations (cd/export) work.
            return "\n".join(result) if commands else safe_echo("No commands provided.")

        if action == "BLOCK":
            return safe_echo(str(reason or "Action blocked."))

        # Unknown/invalid action -> ask for clarification.
        messages.append({"role": "system", "content": "INVALID_ACTION: Return a valid action enum."})

    return safe_echo("Agent timed out.")
