import hashlib
import json
import os
import platform
import re
import shlex
import subprocess

from openai import OpenAI
from pydantic import Json


class OpenAiIntegrator:
    LLM_RESPONSE_ID = None
    CONTEXT_TRACKER = 0
    MAX_CONTEXT_LENGTH = 20
    PENDING_ASK = None
    PENDING_ASK_ORIGINAL_INPUT = None
    PENDING_REVIEW = None
    PENDING_REVIEW_HASH = None
    PENDING_REVIEW_REASON = None
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
    
    USER: "HI/Hello/Good morning"
    First: {"action": "ASK", "commands": [], "reason": "No task specified. What would you like to build, run, or inspect?"}
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
    RESPONSE_SCHEMA = {
        "type": "json_schema",
        "name": "agent_decision",
        "schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["INSPECT", "EXECUTE", "REVIEW", "ASK", "UPLOAD", "BLOCK"]
                },
                "commands": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "reason": {
                    "type": ["string", "null"]
                }
            },
            "required": ["action", "commands", "reason"],
            "additionalProperties": False
        }
    }

    def __init__(self):
        key = self._get_openai_key()
        if key:
            self.client = OpenAI(api_key=key)
        else:
            self.client = OpenAI()

    DEFAULT_MODEL = "gpt-5-nano"

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

    @staticmethod
    def _bash_quote(s: str) -> str:
        return shlex.quote(s)

    @staticmethod
    def _get_openai_key() -> str | None:
        # Support both env var names used in this repo.
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAIAPIKEY")

    def is_runtime_safe(self, cmd: str) -> bool:
        """Hard safety gate: no reasoning, just block known foot-guns."""
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, cmd):
                return False
        return True

    def _is_sensitive_upload_path(self, p: str) -> bool:
        norm = p.replace("\\", "/")
        for pat in self.SENSITIVE_UPLOAD_PATTERNS:
            if re.search(pat, norm):
                return True
        return False

    def _hash_commands(self, commands: list[str]) -> str:
        joined = "\n".join(commands).encode("utf-8")
        return hashlib.sha256(joined).hexdigest()

    def _validate_file(self, path: str) -> bool:
        if not os.path.exists(path):
            print(f"echo 'File not found: {path}'")
            return False
        if not os.path.isfile(path):
            print(f"echo 'Not a file: {path}'")
            return False
        if self._is_sensitive_upload_path(path):
            print(f"echo 'Sensitive file blocked: {path}'")
            return False
        try:
            if os.path.getsize(path) > self.MAX_UPLOAD_BYTES_PER_FILE:
                print(f"echo 'File too large: {path}'")
                return False
        except OSError:
            print(f"echo 'Error checking file size: {path}'")
            return False
        return True

    def _upload_file_to_llm(self, path: str) -> str | None:
        try:
            with open(path, "rb") as f:
                # Using files.create as it is the standard way to upload files and get a file ID
                file_object = self.client.files.create(
                    file=f,
                    purpose="assistants"
                )
            return file_object.id
        except Exception as e:
            print(f"echo 'Upload failed for {path}: {e}'")
            return None

    @staticmethod
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

    def call_llm(self, event: str) -> dict:
        response = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            previous_response_id=self.LLM_RESPONSE_ID,
            input=event,
            text={"format": self.RESPONSE_SCHEMA}
        )

        self.LLM_RESPONSE_ID = response.id
        return json.loads(response.output_text)

    def _summarize_and_reset(self):
        summary_resp = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            previous_response_id=self.LLM_RESPONSE_ID,
            input="Summarize the session so far for future continuation.",
        )
        summary_text = summary_resp.output_text
        # Start a fresh conversation WITH that summary
        new_resp = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            instructions=self.SYSTEM_PROMPT,
            input=f"SESSION SUMMARY: {summary_text}",
            text={"format": {"type": "json_object"}}
        )

        self.LLM_RESPONSE_ID = new_resp.id

    @staticmethod
    def safe_echo(msg: str) -> str:
        return "echo " + json.dumps(msg)

    @staticmethod
    def normalize_commands(cmds) -> list[str]:
        if not isinstance(cmds, list):
            return []
        return [c for c in cmds if isinstance(c, str) and c.strip()]

    def _interactive_review_snippet(self, reason: str, commands: list[str]) -> str:
        try:
            self.reset_ask_loop()

            if not commands:
                return self.safe_echo("Nothing to review.")

            for cmd in commands:
                if not self.is_runtime_safe(cmd):
                    return self.safe_echo(f"Blocked unsafe command: {cmd}")
            self.PENDING_REVIEW = commands
            self.PENDING_REVIEW_HASH = self._hash_commands(commands)
            self.PENDING_REVIEW_REASON = str(reason or "")
            preview = "\n".join(commands)
            return f"REVIEW REQUIRED: {self.PENDING_REVIEW_REASON}\n\nProposed Commands: {preview} \n\nIf you approve, run:confirm:yes"
        except Exception as e:
            return f"ERROR-----Review block: {str(e)}"

    def _execute_review(self, user_input: str) -> str | None:
        """
        Handles confirm:yes without involving the LLM.
        Returns shell output if confirmation was processed,
        otherwise None to continue normal flow.
        """
        if user_input.strip().lower() != "confirm:yes":
            return None

        if not self.PENDING_REVIEW:
            return "No pending operation to confirm."

        commands = self.PENDING_REVIEW
        expected_hash = self.PENDING_REVIEW_HASH

        # Integrity check (anti-tamper)
        if self._hash_commands(commands) != expected_hash:
            self.PENDING_REVIEW = None
            self.PENDING_REVIEW_HASH = None
            self.PENDING_REVIEW_REASON = None
            return "Review invalidated (command mismatch)."

        output = []
        for cmd in commands:
            if not self.is_runtime_safe(cmd):
                self.PENDING_REVIEW = None
                self.PENDING_REVIEW_HASH = None
                self.PENDING_REVIEW_REASON = None
                return f"Blocked during execution: {cmd}"

            output.append(self.run_command(cmd))

        # Clear state (commit complete)
        self.PENDING_REVIEW = None
        self.PENDING_REVIEW_HASH = None
        self.PENDING_REVIEW_REASON = None

        return "\n".join(output) if output else "Done."

    @staticmethod
    def _emit_pause(message: str) -> str:
        return f"{message}\n\n⏸ Execution paused. Respond to continue."

    def init_ai_terminal(self):
        response = self.client.responses.create(
            model=self.DEFAULT_MODEL,
            instructions=self.SYSTEM_PROMPT,
            input=f"OS_INFO: {json.dumps(self.OS_INFO)}"
        )

        self.LLM_RESPONSE_ID = response.id

    def _interactive_ask_snippet(self, reason: str) -> str:
        combined = (
            f"ORIGINAL_REQUEST:\n{self.PENDING_ASK_ORIGINAL_INPUT}\n\n"
            f"MODEL_QUESTION:\n{self.PENDING_ASK}\n\n"
            f"USER_ANSWER:\n{reason}")
        self.PENDING_ASK = None
        return combined

    def reset_ask_loop(self):
        self.PENDING_ASK = None
        self.PENDING_ASK_ORIGINAL_INPUT = None

    def reset_review(self):
        self.PENDING_REVIEW = None
        self.PENDING_REVIEW_HASH = None
        self.PENDING_REVIEW_REASON = None

    def _interactive_call_llm(self, user_input: str, is_ask_resume: bool) -> dict:
        if not is_ask_resume:
            self.CONTEXT_TRACKER += 1
            return self.call_llm(f"USER_INPUT: {user_input}")
        return self.call_llm(f"ASK_RESPONSE: {user_input}")

    def _cli_safe(self, text: str) -> str:
        """
        Escapes text so the outer CLI can safely wrap it in: echo '...'
        """
        return text.replace("'", "'\"'\"'")

    def ai_terminal(self, user_input: str) -> str:
        """
        Event-driven agent loop using Responses API correctly.
        We NEVER resend conversation — we append events only.
        """
        review_result = self._execute_review(user_input)
        if review_result is not None:
            return self._cli_safe(review_result)
        self.reset_review()
        is_ask_resume = self.PENDING_ASK is not None
        if is_ask_resume:
            user_input = self._interactive_ask_snippet(user_input)

        if self.LLM_RESPONSE_ID is None:
            self.init_ai_terminal()
        elif self.CONTEXT_TRACKER > self.MAX_CONTEXT_LENGTH:
            self._summarize_and_reset()
            self.CONTEXT_TRACKER = 0
        MAX_STEPS = 12
        seen_inspects: set[str] = set()
        uploaded_files: set[str] = set()

        # ---- First Event: User Intent ----
        llm_response = self._interactive_call_llm(user_input, is_ask_resume)

        for _ in range(MAX_STEPS):

            action = str(llm_response.get("action", "")).upper().strip()
            commands = self.normalize_commands(llm_response.get("commands", []))
            reason = llm_response.get("reason")

            # ============================================================
            # INSPECT  → run locally → send results back as next event
            # ============================================================
            if action == "INSPECT":
                inspection_output: dict[str, str] = {}

                for cmd in commands:
                    if cmd in seen_inspects:
                        inspection_output[cmd] = "ERROR: repeated inspection detected"
                        continue

                    if not self.is_runtime_safe(cmd):
                        inspection_output[cmd] = "BLOCKED: runtime safety guard"
                        continue

                    print(f"echo 'Inspecting command: {cmd}'")
                    inspection_output[cmd] = self.run_command(cmd)
                    seen_inspects.add(cmd)

                llm_response = self.call_llm(
                    "INSPECTION_RESULT:\n" +
                    json.dumps(inspection_output, ensure_ascii=False)
                )
                continue

            # ============================================================
            # UPLOAD → validate → upload → send file IDs back as event
            # ============================================================
            if action == "UPLOAD":
                payload: dict[str, str] = {}

                for path in commands[:self.MAX_UPLOAD_FILES]:
                    if path in uploaded_files:
                        continue

                    if self._validate_file(path):
                        print(f"echo 'Uploading file {path}'")
                        file_id = self._upload_file_to_llm(path)

                        if file_id:
                            payload[path] = file_id
                            uploaded_files.add(path)
                        else:
                            payload[path] = "UPLOAD_FAILED"
                    else:
                        payload[path] = "VALIDATION_FAILED"

                llm_response = self.call_llm(
                    "UPLOADED_FILES:\n" +
                    json.dumps(payload, ensure_ascii=False)
                )
                continue

            # ============================================================
            # ASK → interactive shell handoff
            # ============================================================
            if action == "ASK":
                if self.PENDING_ASK_ORIGINAL_INPUT is None:
                    self.PENDING_ASK_ORIGINAL_INPUT = user_input
                self.PENDING_ASK = str(reason or "Need more information.")
                return self._cli_safe(self._emit_pause(
                    self.PENDING_ASK + "\n\nProvide the answer in your next command."
                ))

            # ============================================================
            # REVIEW → confirmation workflow
            # ============================================================
            if action == "REVIEW":
                self.reset_ask_loop()
                return self._cli_safe(self._interactive_review_snippet(str(reason or ""), commands))

            # ============================================================
            # EXECUTE → execute safe commands
            # ============================================================
            if action == "EXECUTE":
                result = []
                self.reset_ask_loop()
                for cmd in commands:
                    if not self.is_runtime_safe(cmd):
                        return self._cli_safe(
                            "Execution blocked by runtime safety guard, for command : " + cmd
                        )

                    print(f"echo 'Executing command : {cmd}'")
                    result.append(self.run_command(cmd))

                return self._cli_safe("\n".join(result) if commands else self.safe_echo("No commands provided."))

            # ============================================================
            # BLOCK → hard stop
            # ============================================================
            if action == "BLOCK":
                self.reset_ask_loop()
                return self._cli_safe(str(reason or "Action blocked."))

            # ============================================================
            # Unknown action → ask model to correct itself (event again)
            # ============================================================
            llm_response = self.call_llm("INVALID_ACTION: Return a valid action enum.")

        return self.safe_echo("Agent timed out.")
