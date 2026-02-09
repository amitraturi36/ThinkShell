#!/bin/bash
echo "🗑️  Uninstalling ThinkShell..."
rm -rf "$HOME/.thinkshell"
sudo rm -f "/usr/local/bin/thinkshell"
echo "Think shell successfully uninstalled."
