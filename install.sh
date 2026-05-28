#!/usr/bin/env bash
# repo-brain installer — Mac / Linux
# Usage: curl -fsSL <url-to-this-file> | bash
set -euo pipefail

GITHUB_REPO="https://github.com/YOUR_USERNAME/repo-brain"
INSTALL_DIR="$HOME/.repo-brain"
BIN_DIR="$HOME/.local/bin"
RELEASE_ZIP="$INSTALL_DIR/repo-brain.zip"

# ---- helpers ---------------------------------------------------------------
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n'  "$*"; }

fail() { red "error: $*"; exit 1; }

# ---- Python check ----------------------------------------------------------
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c 'import sys; print(sys.version_info >= (3,10))' 2>/dev/null || echo False)
        if [ "$ver" = "True" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done
[ -n "$PYTHON" ] || fail "Python 3.10+ is required. Install it from https://python.org"

bold "Installing repo-brain..."
echo "  Python: $($PYTHON --version)"

# ---- download latest release -----------------------------------------------
LATEST_URL="$GITHUB_REPO/releases/latest/download/repo-brain.zip"
echo "  Downloading $LATEST_URL"
mkdir -p "$INSTALL_DIR"
if command -v curl &>/dev/null; then
    curl -fsSL "$LATEST_URL" -o "$RELEASE_ZIP"
elif command -v wget &>/dev/null; then
    wget -q "$LATEST_URL" -O "$RELEASE_ZIP"
else
    fail "curl or wget is required"
fi

# ---- unzip -----------------------------------------------------------------
unzip -qo "$RELEASE_ZIP" -d "$INSTALL_DIR"
rm "$RELEASE_ZIP"

# ---- virtual environment ---------------------------------------------------
echo "  Creating virtual environment..."
"$PYTHON" -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# ---- launcher script -------------------------------------------------------
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/repo-brain" <<'LAUNCHER'
#!/usr/bin/env bash
exec "$HOME/.repo-brain/.venv/bin/python" "$HOME/.repo-brain/main.py" "$@"
LAUNCHER
chmod +x "$BIN_DIR/repo-brain"

# ---- PATH reminder ---------------------------------------------------------
green "Done! repo-brain installed."
echo ""
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "  Add this to your shell profile (~/.bashrc or ~/.zshrc):"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "  Then restart your terminal, or run:"
    echo "    source ~/.bashrc   # or ~/.zshrc"
    echo ""
fi
echo "  Set your API key:"
echo "    export OPENAI_API_KEY=sk-..."
echo "    # or ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY, etc."
echo ""
echo "  Run on any repo:"
echo "    repo-brain /path/to/your/repo"
echo "    repo-brain /path/to/your/repo --model claude-3-5-haiku-20241022"
echo "    repo-brain /path/to/your/repo --no-llm"
echo ""
