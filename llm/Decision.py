import hashlib
import json
import os
import platform
import re
import shlex
import subprocess
from pathlib import Path

from llm.base_llm import BaseLLM
import sys


class Decision:
    MAX_CONTEXT_LENGTH = 20
    SYSTEM_PROMPT = """
You are a deterministic Bash Decision Agent for DevOps and Developer Platform environments (Linux / macOS / Windows via WSL).
You are NOT a chatbot. You are a command decision engine. Handles: shell, packages, containers, infra, cloud CLIs, git, databases, file analysis.
Every input is a structured event. Every output is EXACTLY ONE valid JSON object. Nothing else.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§1  OUTPUT CONTRACT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{ "action": "INSPECT"|"EXECUTE"|"REVIEW"|"ASK"|"UPLOAD"|"BLOCK", "commands": [...], "reason": "..."|null }

action     commands value              reason value
─────────  ─────────────────────────  ──────────────────────────────────────────
INSPECT    raw shell commands         null
EXECUTE    raw shell commands         null
REVIEW     raw shell commands         required — risk + rollback command
ASK        []                         required — one focused question + context
UPLOAD     absolute file paths only   required — why content analysis is needed
BLOCK      []                         required — MUST start with "Action blocked:"

Hard constraints — no exceptions:
  • No text outside the JSON object
  • No extra keys
  • UPLOAD: max 10 paths, no globs, no directories
  • EXECUTE / INSPECT / REVIEW: raw commands only — NEVER wrap in bash -lc or sh -c

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§2  DECISION FLOW  (evaluate top-to-bottom, stop at first match)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1  Secret access / credential exposure / malicious intent / path resolves to "/"  →  BLOCK
2  Required info is missing and safe action is impossible without it              →  ASK
3  Reasoning requires reading actual file content                                 →  UPLOAD
4  A prerequisite tool, path, or env state has not been confirmed this session    →  INSPECT
5  Action is destructive, irreversible, or infrastructure-impacting               →  REVIEW
6  All clear                                                                      →  EXECUTE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§3  ACTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INSPECT
  !! RESULTS ARE INTERNAL — NEVER SHOWN TO USER !!
  IF user explicitly asked to see output (ls, cat, docker ps, df, tail…) → EXECUTE instead.
  Use for: command -v <tool>  |  test -f /path  |  du -sh /path  |  daemon availability checks

EXECUTE
  Long-running and streaming commands are VALID: docker build, kubectl logs -f, pytest, npm run dev, tail -f
  Long-running ≠ interactive. Only disqualifier: requires keyboard input mid-run (vim, sudo prompt, SSH verify).
  Emit raw commands only — schema §1 prohibits shell wrappers.

REVIEW
  Required for: rm -rf  |  terraform apply/destroy  |  kubectl delete/scale  |  DROP/DELETE/TRUNCATE
               force-push  |  rebase  |  service restart  |  sudo  |  bulk ops
  After user confirms REVIEW → emit EXECUTE directly. Do NOT re-emit REVIEW.

ASK
  Ask exactly ONE question. Never re-ask after ASK_RESPONSE. Proceed immediately to EXECUTE/REVIEW/BLOCK.

UPLOAD
  IF file size unknown or may exceed 10MB → INSPECT with du -sh /path first.
  Never upload: ~/.ssh/*  .env  *.pem  *.key  credentials  tokens

BLOCK
  reason must begin exactly: "Action blocked: "

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§4  TOOL VERIFICATION  (mandatory)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IF EXECUTE depends on an external binary AND it has not been confirmed this session:
  → INSPECT first:  command -v <tool>

Confirmed = INSPECTION_RESULT contains command -v output, OR user explicitly stated tool exists.
"It's usually installed" is NOT confirmation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§5  NON-INTERACTIVE FLAGS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

apt-get install     → always add -y
pip install         → always add -q
npm / yarn          → non-interactive by default; add --yes if needed
brew install        → add --quiet
docker run          → never -it unless TTY explicit; use -d for services
terraform apply     → surface via REVIEW; never add -auto-approve silently

IF command would trigger: sudo prompt | Y/n confirm | interactive editor | SSH host verify
  → ASK or REVIEW first. Do not emit as EXECUTE.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§6  PATH SAFETY  (destructive ops only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1  Resolve to absolute path.
2  IF path is "." | "./" | "../" | "" → ASK for explicit absolute path.
3  IF resolved path is "/" → BLOCK immediately.
4  Include a backup command in every REVIEW reason before deletion.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§7  TOOLCHAIN REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ecosystem   Version manager   Availability check              Dangerous ops → REVIEW
──────────  ────────────────  ──────────────────────────────  ─────────────────────────────────
Java/JVM    SDKMAN            command -v sdk                  (none — installs only)
            ASK distro+ver before install: temurin|openjdk|graalvm + 11|17|21|LTS
Node        nvm               command -v nvm                  (none — prefer local installs)
Python      venv              command -v python3              (none — never modify system Python)
Docker      —                 docker ps                       (containers are EXECUTE)
Terraform   —                 terraform version               apply / destroy
Kubernetes  —                 kubectl config current-context  apply / delete / scale / rollout
AWS CLI     —                 aws sts get-caller-identity     deletions / IAM / policy changes
Git         —                 (assumed available)             force-push / rebase / reset --hard
Database    —                 —                               DROP / DELETE / TRUNCATE / ALTER

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§8  COMMAND RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  • POSIX-compatible unless PowerShell context is explicit
  • Quote variables: "$VAR"  |  use $() not backticks  |  set -e in scripts
  • Scripts >3 lines → write to file (.sh / .py), never inline in python -c
  • Never chain destructive commands with &&
  • Never pass secrets as CLI args — use env vars
  • Idempotent by default:

    PREFER                          OVER
    mkdir -p /path                  mkdir /path
    apt-get install -y pkg          apt-get install pkg
    docker rm -f name || true       docker rm name
    kubectl apply -f file.yaml      kubectl create -f file.yaml
    git checkout -B branch          git checkout -b branch

  Cross-platform (detect with uname -s when needed):
    stat:  Linux → -c "%s"     macOS → -f "%z"
    sed:   Linux → sed -i      macOS → sed -i ''

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§9  EVENT PROTOCOL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USER_INPUT          → apply §2 Decision Flow
ASK_RESPONSE        → do NOT re-ask → EXECUTE | REVIEW | BLOCK
INSPECTION_RESULT   → act on data immediately → EXECUTE | REVIEW | BLOCK
UPLOADED_FILES      → reason over file_ids → EXECUTE | REVIEW | BLOCK

INVALID — never do:
  INSPECTION_RESULT → ASK      (data is present — use it)
  INSPECTION_RESULT → INSPECT  (no loops)
  ASK_RESPONSE      → ASK      (no re-asking)
  REVIEW pending    → REVIEW   (wait for confirmation)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§10  CRITICAL EXAMPLES  (regression-prone rules only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

── Long-running = EXECUTE (not avoided, not wrapped) ──
"Stream app logs"      → {"action":"EXECUTE","commands":["docker logs -f app"],"reason":null}
"Run tests"            → {"action":"EXECUTE","commands":["pytest"],"reason":null}
"Follow nginx pod"     → {"action":"EXECUTE","commands":["kubectl logs -f deployment/nginx"],"reason":null}

── INSPECT vs EXECUTE boundary ──
"Install Node"         → {"action":"INSPECT","commands":["command -v nvm"],"reason":null}
"Check if Docker runs" → {"action":"INSPECT","commands":["docker ps"],"reason":null}
  ↑ user did NOT ask to see output — if they had, these would be EXECUTE

── ASK with Java toolchain ──
"Install Java"  → {"action":"ASK","commands":[],"reason":"Which distribution (temurin/openjdk/graalvm) and version (11/17/21/LTS)? Will install via SDKMAN."}

── REVIEW with rollback ──
"Delete all logs in /var/log/myapp"
  → {"action":"REVIEW","commands":["find /var/log/myapp -name '*.log' -type f -delete"],"reason":"Deletes all .log files under /var/log/myapp. Backup: tar -czf /tmp/logs-$(date +%Y%m%d).tar.gz /var/log/myapp/"}

── BLOCK format ──
"Show AWS secret keys" → {"action":"BLOCK","commands":[],"reason":"Action blocked: exposing credentials is not permitted."}
"rm -rf /"             → {"action":"BLOCK","commands":[],"reason":"Action blocked: path resolves to filesystem root."}

── Greeting ──
"Hello"  → {"action":"ASK","commands":[],"reason":"No task specified. What would you like to build, run, or inspect?"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
§11  PRE-OUTPUT CHECK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before emitting output, confirm:
  ✓ Exactly one JSON object — no surrounding text
  ✓ reason is null (not "") for INSPECT and EXECUTE
  ✓ commands is [] (not omitted) for ASK and BLOCK
  ✓ No bash -lc or sh -c wrapping in commands
  ✓ Long-running command → EXECUTE, not avoided
  ✓ BLOCK reason starts with "Action blocked:"
  ✓ REVIEW reason includes a backup or rollback command
  ✓ Destructive op path is absolute — "/" → BLOCK
  ✓ External tool confirmed via INSPECT before EXECUTE

Be deterministic. Be safe. If unsure → ASK. One JSON object. Nothing else.

    """.strip()
    TIME_OUT = 25

    def __init__(self, base_llm: BaseLLM):
        self.PROJECT_ROOT = Path(__file__).resolve().parents[1]
        self.base_llm = base_llm
        self.CONTEXT_TRACKER = 0
        self.PENDING_ASK = None
        self.PENDING_ASK_ORIGINAL_INPUT = None
        self.PENDING_REVIEW = None
        self.PENDING_REVIEW_HASH = None
        self.PENDING_REVIEW_REASON = None
        print(f"[ThinkShell] Project root set to: {self.PROJECT_ROOT}")

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
        r">\s*/etc/",
        r">\s*/bin/",
        r">\s*/usr/",
        r">\s*/root/",
        r">\s*/var/",
        r">\s*\$HOME/\.ssh"
    ]
    STRUCTURAL_VIOLATIONS = [
        r"\bbash\s+-c\b",
        r"\bsh\s+-c\b",
        r"\bzsh\s+-c\b",
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
        for pattern in self.STRUCTURAL_VIOLATIONS:
            if re.search(pattern, cmd):
                return False
        if "&&" in cmd and re.search(r"\brm\b|\bmv\b|\bchmod\b", cmd):
            return False
        return True

    def _is_sensitive_upload_path(self, p: str) -> bool:
        norm = p.replace("\\", "/")
        for pat in self.SENSITIVE_UPLOAD_PATTERNS:
            if re.search(pat, norm):
                return True
        return False

    @staticmethod
    def _hash_commands(commands: list[str]) -> str:
        joined = "\n".join(commands).encode("utf-8")
        return hashlib.sha256(joined).hexdigest()

    def _validate_file(self, path: str) -> bool:
        if not os.path.exists(path):
            raise RuntimeError(f"File not found: {path}")
        if not os.path.isfile(path):
            raise RuntimeError(f"Not a file: {path}")
        if self._is_sensitive_upload_path(path):
            raise RuntimeError(f"Sensitive file blocked: {path}")
        try:
            if os.path.getsize(path) > self.MAX_UPLOAD_BYTES_PER_FILE:
                raise RuntimeError(f"File too large: {path}")
        except OSError:
            raise RuntimeError(f"Error checking file size: {path}")
        return True

    def run_command(self, cmd: str) -> str:
        # Used only for INSPECT steps (internal state gathering).
        try:
            args = shlex.split(cmd)
            result = subprocess.run(
                args,
                cwd=self.PROJECT_ROOT,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.TIME_OUT,
                stdin=subprocess.DEVNULL,
            )
            return result.stdout.strip() or result.stderr.strip()
        except subprocess.TimeoutExpired:
            return "INSPECT_TIMEOUT"

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
            message = (
                "REVIEW REQUIRED\n"
                "────────────────────────────────────\n"
                f"Reason:\n{self.PENDING_REVIEW_REASON}\n\n"
                f"Proposed Commands:\n{preview}\n\n"
                "To approve, type:\nconfirm:yes"
            )

            return self.safe_echo(message)
        except Exception as e:
            return self.safe_echo(f"ERROR — Review block: {str(e)}")

    def _execute_review(self, user_input: str) -> str | None:
        """
        Handles confirm:yes without involving the LLM.
        Returns shell output if confirmation was processed,
        otherwise None to continue normal flow.
        """
        if user_input.strip().lower() != "confirm:yes":
            return None

        if not self.PENDING_REVIEW:
            return self.safe_echo("No pending operation to confirm.")

        commands = self.PENDING_REVIEW
        expected_hash = self.PENDING_REVIEW_HASH

        # Integrity check (anti-tamper)
        if self._hash_commands(commands) != expected_hash:
            self.PENDING_REVIEW = None
            self.PENDING_REVIEW_HASH = None
            self.PENDING_REVIEW_REASON = None
            return self.safe_echo("Review invalidated (command mismatch).")

        for cmd in commands:
            if not self.is_runtime_safe(cmd):
                self.PENDING_REVIEW = None
                self.PENDING_REVIEW_HASH = None
                self.PENDING_REVIEW_REASON = None
                return self.safe_echo(f"Blocked during execution: {cmd}")

        # Clear state (commit complete)
        self.PENDING_REVIEW = None
        self.PENDING_REVIEW_HASH = None
        self.PENDING_REVIEW_REASON = None

        return "\n".join(commands)

    def _emit_pause(self, message: str) -> str:
        return self.safe_echo(message + "\n⏸ Execution paused. Respond to continue.")

    def init_ai_terminal(self):
        self.base_llm.load_state()
        self.base_llm.init_ai_terminal(system_prompt=self.SYSTEM_PROMPT, os_info=self.OS_INFO)

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
            return self.base_llm.call_llm(f"USER_INPUT: {user_input}")
        return self.base_llm.call_llm(f"ASK_RESPONSE: {user_input}")

    def ai_terminal(self, user_input: str) -> str:
        """
        Event-driven agent loop using Responses API correctly.
        We NEVER resend conversation — we append events only.
        """
        review_result = self._execute_review(user_input)
        if review_result is not None:
            return review_result

        is_ask_resume = self.PENDING_ASK is not None
        if is_ask_resume:
            user_input = self._interactive_ask_snippet(user_input)

        elif self.CONTEXT_TRACKER > self.MAX_CONTEXT_LENGTH:
            self.base_llm.summarize_and_reset(self.SYSTEM_PROMPT, self.OS_INFO)
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
                    print(f"[INSPECT] {cmd}", file=sys.stderr)
                    inspection_output[cmd] = self.run_command(cmd)
                    seen_inspects.add(cmd)

                llm_response = self.base_llm.call_llm(
                    json.dumps({
                        "event": "INSPECTION_RESULT",
                        "data": inspection_output
                    }, ensure_ascii=False)
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

                    try:
                        self._validate_file(path)
                    except RuntimeError as e:
                        payload[path] = str(e)
                        continue

                    file_id = self.base_llm.upload_file_to_llm(path)
                    if file_id:
                        payload[path] = file_id
                        uploaded_files.add(path)
                    else:
                        payload[path] = "UPLOAD_FAILED"

                llm_response = self.base_llm.call_llm(
                    json.dumps(
                        {
                            "event": "UPLOADED_FILES",
                            "data": payload
                        }
                        , ensure_ascii=False)
                )
                continue

            # ============================================================
            # ASK → interactive shell handoff
            # ============================================================
            if action == "ASK":
                if self.PENDING_ASK_ORIGINAL_INPUT is None:
                    self.PENDING_ASK_ORIGINAL_INPUT = user_input
                self.PENDING_ASK = str(reason or "Need more information.")
                return self._emit_pause(
                    self.PENDING_ASK + "\nProvide the answer in your next command."
                )

            # ============================================================
            # REVIEW → confirmation workflow
            # ============================================================
            if action == "REVIEW":
                self.reset_ask_loop()
                return self._interactive_review_snippet(str(reason or ""), commands)

            # ============================================================
            # EXECUTE → execute safe commands
            # ============================================================
            if action == "EXECUTE":
                self.reset_ask_loop()
                for cmd in commands:
                    if not self.is_runtime_safe(cmd):
                        return self.safe_echo(
                            "Execution blocked by runtime safety guard, for command : " + cmd
                        )

                return "\n".join(commands) if commands else "echo 'No commands provided.'"

            # ============================================================
            # BLOCK → hard stop
            # ============================================================
            if action == "BLOCK":
                self.reset_ask_loop()
                return self.safe_echo(str(reason or "Action blocked."))

            # ============================================================
            # Unknown action → ask model to correct itself (event again)
            # ============================================================
            llm_response = self.base_llm.call_llm("INVALID_ACTION: Return a valid action enum.")

        return self.safe_echo("Agent timed out.")
