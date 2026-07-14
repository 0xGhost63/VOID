#!/usr/bin/env bash
set -e

REPO_URL="https://github.com/0xGhost63/VOID.git"
INSTALL_DIR="$HOME/.void-cli"
BIN_DIR="$HOME/.local/bin"

echo "Installing VOID..."

command -v git >/dev/null 2>&1 || { echo "git is required. Install it and re-run: https://git-scm.com/downloads"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 (3.10+) is required. Install it and re-run: https://www.python.org/downloads/"; exit 1; }

# Some Linux distros ship python3 without the venv module
if ! python3 -c "import venv" >/dev/null 2>&1; then
    echo "Python venv module is missing."
    echo "Debian/Ubuntu: sudo apt install python3-venv"
    echo "Fedora:        sudo dnf install python3"
    exit 1
fi

if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Existing install found, updating..."
    git -C "$INSTALL_DIR" pull --ff-only || git -C "$INSTALL_DIR" pull
else
    if [ -d "$INSTALL_DIR" ]; then
        echo "Removing incomplete install at $INSTALL_DIR ..."
        rm -rf "$INSTALL_DIR"
    fi
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Public app config only (publishable key). Never ships Groq/Gemini secrets —
# AI goes through the VOID web backend.
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Created .env from .env.example"
    else
        echo "Warning: no .env or .env.example found — login may fail until you add one."
    fi
fi

python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/void" << 'EOF'
#!/usr/bin/env bash
set -e
INSTALL_DIR="$HOME/.void-cli"
cd "$INSTALL_DIR" || { echo "VOID is not installed at $INSTALL_DIR"; exit 1; }

# Quiet update when online; stay on current copy if offline
if git pull --ff-only --quiet 2>/dev/null || git pull --quiet 2>/dev/null; then
    :
fi

if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
fi

# shellcheck disable=SC1091
source venv/bin/activate
pip install --quiet -r requirements.txt >/dev/null 2>&1 || true
python main.py "$@"
EOF
chmod +x "$BIN_DIR/void"

echo ""
echo "VOID installed to $INSTALL_DIR"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "Add this to ~/.bashrc or ~/.zshrc, then open a new terminal:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi
echo "Run it with:  void"
