#!/usr/bin/env bash
# pdf-to-epub: Universal Installation Script for Linux and macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==============================================="
echo "   PDF-to-EPUB Conversion Suite Installer      "
echo "==============================================="

# 1. Detect System Package Manager & Poppler
echo "[1/4] Checking system utilities (poppler-utils / pdftoppm)..."
if ! command -v pdftoppm &> /dev/null; then
    echo "pdftoppm not found. Attempting to install poppler-utils..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y poppler-utils
    elif command -v pacman &> /dev/null; then
        sudo pacman -S --noconfirm poppler
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y poppler-utils
    elif command -v brew &> /dev/null; then
        brew install poppler
    else
        echo "[WARNING] Could not automatically install poppler. Please install poppler-utils manually."
    fi
else
    echo "  -> pdftoppm found at: $(which pdftoppm)"
fi

# 2. Python Environment & Dependencies
echo "[2/4] Setting up Python dependencies..."
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" &> /dev/null; then
    echo "[ERROR] Python 3 is required but not found."
    exit 1
fi

"$PYTHON_BIN" -m pip install --upgrade pip --quiet 2>/dev/null || true
"$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet

echo "  -> Python dependencies verified."

# 3. Install CLI wrapper to ~/.local/bin or /usr/local/bin
echo "[3/4] Installing CLI binary (pdf-to-epub)..."
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

cat << EOF > "$BIN_DIR/pdf-to-epub"
#!/usr/bin/env bash
exec "$PYTHON_BIN" "$SCRIPT_DIR/scripts/cli.py" "\$@"
EOF
chmod +x "$BIN_DIR/pdf-to-epub"

echo "  -> Installed CLI binary to: $BIN_DIR/pdf-to-epub"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "  [NOTE] Add $BIN_DIR to your PATH in ~/.bashrc or ~/.zshrc:"
    echo "         export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 4. Install Antigravity Skill if ~/.gemini exists
echo "[4/4] Checking Antigravity environment..."
SKILL_TARGET="$HOME/.gemini/config/skills/pdf-to-epub"
if [ -d "$HOME/.gemini" ]; then
    echo "Antigravity installation detected. Installing global skill..."
    mkdir -p "$SKILL_TARGET/scripts"
    cp "$SCRIPT_DIR/SKILL.md" "$SKILL_TARGET/SKILL.md"
    cp "$SCRIPT_DIR/scripts/collage_maker.py" "$SKILL_TARGET/scripts/"
    cp "$SCRIPT_DIR/scripts/epub_packager.py" "$SKILL_TARGET/scripts/"
    chmod +x "$SKILL_TARGET/scripts/"*.py
    echo "  -> Skill installed successfully to $SKILL_TARGET"
else
    echo "  -> ~/.gemini directory not present. Skipping skill installation."
fi

echo ""
echo "==============================================="
echo "  Installation Complete!                       "
echo "  Run: pdf-to-epub --help                      "
echo "==============================================="
