#!/usr/bin/env bash
set -e

REPO_URL="https://github.com/0xGhost63/VOID.git"
INSTALL_DIR="$HOME/.void-cli"
BIN_DIR="$HOME/.local/bin"

echo "Installing VOID..."

command -v git >/dev/null 2>&1 || { echo "git is required. Install it and re-run."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required. Install it and re-run."; exit 1; }

if [ -d "$INSTALL_DIR" ]; then
    echo "Existing install found, updating..."
    git -C "$INSTALL_DIR" pull --quiet
else
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/void" << 'EOF'
#!/usr/bin/env bash
INSTALL_DIR="$HOME/.void-cli"
cd "$INSTALL_DIR"
git pull --quiet
source venv/bin/activate
python main.py "$@"
EOF
chmod +x "$BIN_DIR/void"

echo ""
echo "VOID installed."
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "Add this to ~/.bashrc or ~/.zshrc, then restart your terminal:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
echo "Run it with: void"