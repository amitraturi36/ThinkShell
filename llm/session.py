import atexit
import json
import os
import time
from pathlib import Path

try:
    import psutil  # better PID validation (optional but recommended)
except ImportError:
    psutil = None


class ThinkShellSession:
    """
    Terminal-bound session manager.
    One terminal (TTY) = One session file.
    Shared across ALL LLM providers.
    """

    BASE_DIR = Path.home() / ".config" / "thinkshell" / "sessions"

    # ---------- INIT ----------

    def __init__(self):
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)

        self.pid = os.getpid()
        self.tty = self._resolve_tty()
        self.session_id = self.tty.replace("/dev/", "")
        self.file = self.BASE_DIR / f"{self.session_id}.json"

        self._cleanup_stale_sessions()
        self.data = self._load_or_create()

        atexit.register(self._on_exit)

    # ---------- PUBLIC API ----------

    def get_provider_state(self, provider: str) -> dict:
        """Return stored state for provider (openai/gemini/etc)."""
        return self.data.setdefault("providers", {}).setdefault(provider, {})

    def set_provider_state(self, provider: str, key: str, value):
        """Persist provider-specific state."""
        self.data.setdefault("providers", {}).setdefault(provider, {})[key] = value
        self._touch()
        self._save()

    def get(self, provider: str, key: str, default=None):
        return self.get_provider_state(provider).get(key, default)

    def set(self, provider: str, key: str, value):
        self.set_provider_state(provider, key, value)

    # ---------- SESSION CORE ----------

    def _resolve_tty(self) -> str:
        """
        Bind session to terminal device.
        This is the KEY to preventing duplicate sessions.
        """
        try:
            return os.ttyname(0)
        except OSError:
            # fallback (non-interactive execution)
            return f"no-tty-{self.pid}"

    def _load_or_create(self) -> dict:
        if self.file.exists():
            with open(self.file, "r") as f:
                data = json.load(f)

            # If PID is dead → treat as stale and recreate
            if not self._pid_alive(data.get("pid")):
                return self._create_new()

            return data

        return self._create_new()

    def _create_new(self) -> dict:
        return {
            "session_id": self.session_id,
            "pid": self.pid,
            "tty": self.tty,
            "providers": {},
            "created_at": time.time(),
            "last_used": time.time(),
        }

    # ---------- SAVE / TOUCH ----------

    def _touch(self):
        self.data["last_used"] = time.time()
        self.data["pid"] = self.pid

    def _save(self):
        tmp = f"{self.file}.tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.file)

    # ---------- CLEANUP ----------

    def _cleanup_stale_sessions(self):
        """
        Remove sessions whose PID no longer exists.
        This auto-cleans after reboot or crashes.
        """
        for file in self.BASE_DIR.glob("*.json"):
            try:
                with open(file, "r") as f:
                    data = json.load(f)

                pid = data.get("pid")
                if not self._pid_alive(pid):
                    file.unlink(missing_ok=True)

            except Exception:
                file.unlink(missing_ok=True)

    @staticmethod
    def _pid_alive(pid) -> bool:
        if not pid:
            return False

        if psutil:
            return psutil.pid_exists(pid)

        # fallback without psutil
        return os.path.exists(f"/proc/{pid}") if os.name == "posix" else True

    # ---------- EXIT HANDLER ----------

    def _on_exit(self):
        """
        Remove session when terminal closes cleanly.
        """
        try:
            if self.file.exists():
                self.file.unlink()
        except Exception:
            pass