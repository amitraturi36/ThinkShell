# 🚀 ThinkShell: The Agentic Terminal

> **Turn your terminal into an intelligent agent.** ThinkShell intercepts "Command Not Found" errors and uses LLMs (OpenAI, Gemini, Claude) to auto-correct mistakes, understand natural language intent, and execute complex multi-step tasks.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue) ![Bash](https://img.shields.io/badge/Shell-Bash-green) ![License](https://img.shields.io/badge/License-MIT-purple)

## 🌟 Features

*   **🤖 Silent Auto-Correction:** Type `list files` instead of `ls -la`? ThinkShell fixes it instantly without an error message (requires Bash 4+).
*   **🧠 Natural Language Command:** Just ask: `?? deploy docker container`. The agent plans and executes the shell commands for you.
*   **🔌 Multi-LLM Support:** Native support for **OpenAI (GPT-4o)**, **Google Gemini**, and **Anthropic Claude**.
*   **🛡️ Agentic Safety:** Dangerous commands (e.g., `rm -rf /`) are intercepted and blocked before execution.
*   **🍏 macOS & Linux Native:** Works with native PTY (Pseudo-Terminal) hooks for a seamless experience (vim, nano, htop work perfectly).

---

## 🛠️ Installation

### Quick Install (Mac/Linux)

```bash
git clone https://github.com/YOUR_USERNAME/ThinkShell.git
cd ThinkShell
chmod +x install.sh
./install.sh
```
This script will:

Set up a Python virtual environment.

Install required dependencies (openai, anthropic, google-generativeai).

macOS Users: Automatically install Homebrew Bash (v5+) to enable silent error interception.

Create the global thinkshell command.

# 🚀 Usage
1. Launch
Start the shell. You can pass keys directly or set them up interactively.
## Interactive Setup (First Run)
```bash
thinkshell

## Or launch with a specific key
thinkshell --openai_key sk-proj-123...
thinkshell --gemini_key AIzaSy...
```
# 2. Auto-Correction (The Magic)
   ThinkShell intercepts command not found errors.
```bash
# User types natural language:
$ show me docker containers

# Agent intercepts, translates to 'docker ps -a', and runs it:
CONTAINER ID   IMAGE     COMMAND   ...
```

# ⚠️ Requirements
* Python 3.8+

* Bash 4.0+ (Installed automatically on macOS via Homebrew by install.sh)

* API Key (OpenAI, Anthropic, or Gemini)
