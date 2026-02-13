import os
import json


# ----------------------------
# Config file helpers
# ----------------------------

def get_config_path():
    """
    Default: ~/.config/thinkshell/config.json
    You can override path via THINKSHELL_CONFIG env var if you want.
    """
    override = os.environ.get("THINKSHELL_CONFIG")
    if override:
        return os.path.expanduser(override)

    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(xdg, "thinkshell", "config.json")


def ensure_config_file_exists(path: str):
    """
    If config file doesn't exist, create parent dir and write an empty JSON object.
    """
    if os.path.exists(path):
        return

    print("Creating config file...")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Create a minimal valid config file
    with open(path, "w", encoding="utf-8") as f:
        f.write("{}\n")

    # Restrict permissions (best-effort; Windows may behave differently)
    # noinspection PyBroadException
    try:
        print("Providing permissions to configuration file...")
        os.chmod(path, 0o600)
    except Exception:
        print("\nError while providing permissions to configuration file...")
        print("\nContinuing with default permissions...")
        pass


def load_config():
    path = get_config_path()

    # NEW: create empty file if missing (requirement)
    ensure_config_file_exists(path)

    # noinspection PyBroadException
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        print("Configuration file not found...")
        print("Initializing with default configurations...")
        return {}
    except Exception:
        # If config is corrupt/unreadable, ignore it rather than breaking startup
        print("Invalid configuration file.")
        print("Initializing with default configurations...")
        return {}


def save_config(cfg: dict):
    path = get_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    # Restrict permissions (best-effort; on Windows this may not behave the same)
    try:
        os.chmod(tmp_path, 0o600)
    except Exception as e:
        print("Not able to save config", e)
        print("Won't be loading current config on new session....")
        pass

    os.replace(tmp_path, path)


def set_env_from_config(cfg: dict) -> bool:
    """
    Load keys from config into environment if present.
    Returns True if at least one key was loaded.
    """
    loaded_any = False

    openai = (cfg.get("openai_key") or "").strip()
    anthropic = (cfg.get("anthropic_key") or "").strip()
    gemini = (cfg.get("gemini_key") or "").strip()

    if openai:
        os.environ["OPENAI_API_KEY"] = openai
        loaded_any = True
    if anthropic:
        os.environ["ANTHROPIC_API_KEY"] = anthropic
        loaded_any = True
    if gemini:
        os.environ["GOOGLE_API_KEY"] = gemini
        loaded_any = True

    return loaded_any


def update_config_from_env(cfg: dict) -> bool:
    """
    If env vars exist, write them back to config keys.
    Returns True if config changed.
    """
    changed = False

    env_openai = os.environ.get("OPENAI_API_KEY", "").strip()
    env_anthropic = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    env_gemini = os.environ.get("GOOGLE_API_KEY", "").strip()

    if env_openai and cfg.get("openai_key") != env_openai:
        cfg["openai_key"] = env_openai
        changed = True
    if env_anthropic and cfg.get("anthropic_key") != env_anthropic:
        cfg["anthropic_key"] = env_anthropic
        changed = True
    if env_gemini and cfg.get("gemini_key") != env_gemini:
        cfg["gemini_key"] = env_gemini
        changed = True

    return changed
