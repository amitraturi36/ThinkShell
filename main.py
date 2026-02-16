import argparse
import atexit
import getpass
import os
import sys
import termios

from aiproviders import get_available_providers_from_config
from aiproviders import provider_selection_menu
from configreader import load_config
from configreader import save_config
from io_loop import start_io_loop
from pty_shell import spawn_shell
from signals import setup_signals
from winsize import set_pty_size
from aiproviders import PROVIDERS


def prompt_for_key(provider: str) -> str:
    meta = PROVIDERS[provider]
    return getpass.getpass(f"Enter {meta['label']} API Key: ").strip()


def apply_provider_env(cfg: dict, provider: str):
    """
    Set only the chosen provider key into environment (clears others to avoid ambiguity).
    """
    # Clear all provider env vars first
    for p, meta in PROVIDERS.items():
        if meta["env_key"]:
            os.environ.pop(meta["env_key"], None)

    if provider == "none":
        return

    meta = PROVIDERS[provider]
    key = (cfg.get(meta["cfg_key"]) or "").strip()
    if key:
        os.environ[meta["env_key"]] = key


def ensure_provider_has_key(cfg: dict, provider: str):
    """
    If provider requires a key and config doesn't have it, prompt user and save.
    """
    if provider == "none":
        return

    meta = PROVIDERS[provider]
    cfg_key = meta["cfg_key"]
    existing = (cfg.get(cfg_key) or "").strip()
    if existing:
        return

    key = prompt_for_key(provider)
    if not key:
        print("No key entered. Starting without AI.")
        cfg["provider"] = "none"
        save_config(cfg)
        return

    cfg[cfg_key] = key
    save_config(cfg)


def choose_provider_on_startup(cfg: dict, cli_provider: str | None, switch_ai: bool) -> str:
    """
    Startup decision rules:
    - If cli_provider provided => use it (validate key)
    - else if cfg.provider exists => use it (validate key)
    - else if multiple keys exist in cfg => ask which model to use
    - else if exactly one key exists => auto-select that provider
    - else => ask setup menu
    """
    available = get_available_providers_from_config(cfg)

    # If user explicitly wants to switch, always show menu
    if switch_ai:
        provider = provider_selection_menu(title="ThinkShell AI Model Switch")
        cfg["provider"] = provider
        save_config(cfg)
        ensure_provider_has_key(cfg, provider)
        return provider

    # CLI provider wins
    if cli_provider:
        provider = cli_provider
        cfg["provider"] = provider
        save_config(cfg)
        ensure_provider_has_key(cfg, provider)
        return provider

    # Config provider next
    cfg_provider = (cfg.get("provider") or "").strip().lower()
    if cfg_provider in PROVIDERS:
        provider = cfg_provider
        ensure_provider_has_key(cfg, provider)
        return provider

    # Multiple keys found -> ask user
    if len(available) >= 2:
        print("\nMultiple AI providers detected in config.")
        provider = provider_selection_menu(title="Select AI Provider to Use")
        cfg["provider"] = provider
        save_config(cfg)
        ensure_provider_has_key(cfg, provider)
        return provider

    # Exactly one key -> choose it
    if len(available) == 1:
        provider = available[0]
        cfg["provider"] = provider
        save_config(cfg)
        return provider

    # No keys -> run full setup menu
    provider = provider_selection_menu()
    cfg["provider"] = provider
    save_config(cfg)
    ensure_provider_has_key(cfg, provider)
    return provider


def set_manual_raw(fd):
    """Sets precise raw mode flags to fix cursor/space issues."""
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK |
                  termios.ISTRIP | termios.INLCR | termios.IGNCR |
                  termios.ICRNL | termios.IXON)
    attrs[1] &= ~termios.OPOST
    attrs[2] |= termios.CS8
    attrs[3] &= ~(termios.ECHO | termios.ICANON |
                  termios.IEXTEN | termios.ISIG)
    attrs[6][termios.VMIN] = 1
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)

def restore(fd, attrs):
    # noinspection PyBroadException
    try: termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
    except: pass

def interactive_setup(cfg: dict):
    """Shows a menu if no keys are provided via CLI."""
    print("\n🤖 \033[1mThinkShell AI Setup\033[0m")
    print("--------------------------------")
    print("1. OpenAI (GPT-4o/3.5)")
    print("2. Google Gemini")
    print("3. Anthropic Claude")
    print("4. Skip (No AI)")
    print("--------------------------------")

    choice = input("Select Provider [1-4]: ").strip()

    if choice == "1":
        key = getpass.getpass("Enter OpenAI API Key: ").strip()
        if key:
            os.environ["OPENAI_API_KEY"] = key
            cfg["openai_key"] = key
            save_config(cfg)
    elif choice == "2":
        key = getpass.getpass("Enter Google Gemini Key: ").strip()
        if key:
            os.environ["GOOGLE_API_KEY"] = key
            cfg["gemini_key"] = key
            save_config(cfg)
    elif choice == "3":
        key = getpass.getpass("Enter Anthropic API Key: ").strip()
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
            cfg["anthropic_key"] = key
            save_config(cfg)
    elif choice == "4":
        print("⚠️  Starting without AI capabilities.")
    else:
        print("Invalid choice. Skipping AI setup.")

def main():
    # 1. Check Command Line Arguments
    parser = argparse.ArgumentParser(description="ThinkShell Launcher")
    parser.add_argument("--openai_key", help="OpenAI API Key")
    parser.add_argument("--anthropic_key", help="Anthropic API Key")
    parser.add_argument("--gemini_key", help="Google Gemini API Key")

    # Custom command: select/switch model
    parser.add_argument(
        "--provider",
        choices=["openai", "gemini", "anthropic", "none"],
        help="Select which AI provider to use (saved to config)."
    )
    parser.add_argument(
        "--switch-ai",
        action="store_true",
        help="Interactively switch AI provider (saved to config)."
    )

    # Optional: allow choosing a custom config path
    parser.add_argument("--config", help="Path to ThinkShell config file")

    args, unknown = parser.parse_known_args()

    # If --config is provided, override config path via env var and reload
    if args.config:
        os.environ["THINKSHELL_CONFIG"] = os.path.expanduser(args.config)

    cfg = load_config()

    # If user passed CLI keys, save them to config right away
    if args.openai_key:
        cfg["openai_key"] = args.openai_key.strip()
    if args.anthropic_key:
        cfg["anthropic_key"] = args.anthropic_key.strip()
    if args.gemini_key:
        cfg["gemini_key"] = args.gemini_key.strip()
    if any([args.openai_key, args.anthropic_key, args.gemini_key]):
        save_config(cfg)

    # Determine provider, enforce key if needed
    provider = choose_provider_on_startup(cfg, args.provider, args.switch_ai)
    # Apply environment for chosen provider
    apply_provider_env(cfg, provider)

    # 5. Launch Shell
    print(f"\n🚀 ThinkShell Ready (AI: {PROVIDERS[provider]['label']})")
    fd = sys.stdin.fileno()
    try:
        old_attrs = termios.tcgetattr(fd)
    except Exception as e:
        print("Error: Not running in a terminal.", e)
        return

    atexit.register(restore, fd, old_attrs)

    try:
        pid, pty_fd = spawn_shell()
        set_pty_size(pty_fd)
        setup_signals(pty_fd)
        set_manual_raw(fd)
        start_io_loop(pty_fd)
    except Exception as e:
        restore(fd, old_attrs)
        print(f"Error: {e}")
    finally:
        restore(fd, old_attrs)

if __name__ == "__main__":
    main()

