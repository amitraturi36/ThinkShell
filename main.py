import argparse
import atexit
import getpass
import os
import sys
import termios

from io_loop import start_io_loop
from pty_shell import spawn_shell
from signals import setup_signals
from winsize import set_pty_size


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
    try: termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
    except: pass

def interactive_setup():
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
        if key: os.environ["OPENAI_API_KEY"] = key
    elif choice == "2":
        key = getpass.getpass("Enter Google Gemini Key: ").strip()
        if key: os.environ["GOOGLE_API_KEY"] = key
    elif choice == "3":
        key = getpass.getpass("Enter Anthropic API Key: ").strip()
        if key: os.environ["ANTHROPIC_API_KEY"] = key
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

    args, unknown = parser.parse_known_args()

    key_loaded = False

    # 2. Inject CLI Keys if present
    if args.openai_key:
        os.environ["OPENAI_API_KEY"] = args.openai_key
        key_loaded = True
    if args.anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = args.anthropic_key
        key_loaded = True
    if args.gemini_key:
        os.environ["GOOGLE_API_KEY"] = args.gemini_key
        key_loaded = True

    # 3. If no CLI keys, run Interactive Mode
    if not key_loaded:
        interactive_setup()

    # 4. Launch Shell
    print("\n🚀 ThinkShell Ready")
    fd = sys.stdin.fileno()
    try:
        old_attrs = termios.tcgetattr(fd)
    except:
        print("Error: Not running in a terminal.")
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
