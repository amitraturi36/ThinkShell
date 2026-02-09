#!/bin/bash

# Configuration
INSTALL_DIR="$HOME/.thinkshell"
BIN_NAME="thinkshell"

# Stop on error
set -e

echo "🚀 Installing ThinkShell..."

# --- 0. MACOS BASH UPGRADE STEP ---
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "🍎 macOS detected. Checking Bash version..."

    # Check if modern bash exists
    MODERN_BASH=""
    if [ -x "/opt/homebrew/bin/bash" ]; then MODERN_BASH="/opt/homebrew/bin/bash"; fi
    if [ -x "/usr/local/bin/bash" ]; then MODERN_BASH="/usr/local/bin/bash"; fi

    if [ -z "$MODERN_BASH" ]; then
        echo "⚠️  Default macOS Bash is too old (v3.2) for silent error handling."
        echo "   Installing modern Bash via Homebrew..."

        # Check for Homebrew
        if ! command -v brew &> /dev/null; then
            echo "🍺 Homebrew not found. Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi

        # Install Bash
        echo "📦 Installing bash..."
        brew install bash

        echo "✅ Modern Bash installed!"
    else
        echo "✅ Modern Bash found at $MODERN_BASH"
    fi
fi
# -----------------------------------

# 1. Create Installation Directory
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
fi
mkdir -p "$INSTALL_DIR"

# 2. Copy Files
# 2. Copy Files
echo "📂 Copying files to $INSTALL_DIR..."

# Copy flat files
cp *.py "$INSTALL_DIR/" 2>/dev/null

# Handle 'controller' folder structure if it exists
if [ -f "controller/thinkshellctl.py" ]; then
    echo "   Copying controller/thinkshellctl.py to root..."
    cp "controller/thinkshellctl.py" "$INSTALL_DIR/"
fi

# Final check
if [ ! -f "$INSTALL_DIR/thinkshellctl.py" ]; then
    echo "❌ Error: thinkshellctl.py failed to copy. Check your folder structure!"
    exit 1
fi

# 3. Create Virtual Environment
echo "🐍 Setting up Python Virtual Environment..."
python3 -m venv "$INSTALL_DIR/venv"

# 4. Install Dependencies
echo "📦 Installing libraries..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip > /dev/null
"$INSTALL_DIR/venv/bin/pip" install openai google-generativeai anthropic > /dev/null

# 5. Create the Launcher
echo "🔗 Creating launcher script..."
cat <<EOF > "$INSTALL_DIR/$BIN_NAME"
#!/bin/bash
# Launch with the python environment
# We quote \$@ to handle arguments with spaces correctly
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/main.py" "\$@"
EOF
chmod +x "$INSTALL_DIR/$BIN_NAME"

# 6. Add to PATH
TARGET_BIN="/usr/local/bin/$BIN_NAME"
echo "🔧 Linking to $TARGET_BIN..."

if ln -sf "$INSTALL_DIR/$BIN_NAME" "$TARGET_BIN" 2>/dev/null; then
    echo "   Link created."
else
    echo "   Sudo required for linking..."
    if ! sudo ln -sf "$INSTALL_DIR/$BIN_NAME" "$TARGET_BIN"; then
        echo "❌ Failed to link. Aborting."
        exit 1
    fi
fi

echo ""
echo "✅ Installation Complete!"
echo "   $ thinkshell"
