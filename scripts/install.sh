#!/usr/bin/env bash
set -euo pipefail

ZIP_URL="https://github.com/0xGhost63/VOID/archive/refs/heads/main.zip"
INSTALL_DIR="${HOME}/.void-cli"
BIN_DIR="${HOME}/.local/bin"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# ── progress bar ─────────────────────────────────────────────────────────────
# usage: bar <0-100> <label>
bar() {
    local pct="$1"
    local label="$2"
    local width=28
    local filled=$(( pct * width / 100 ))
    local empty=$(( width - filled ))
    local i
    local fill=""
    local gap=""
    for ((i = 0; i < filled; i++)); do fill+="#"; done
    for ((i = 0; i < empty; i++)); do gap+="-"; done
    printf "\r  [%s%s] %3d%%  %-40s" "$fill" "$gap" "$pct" "$label"
    if [ "$pct" -ge 100 ]; then
        printf "\n"
    fi
}

die() { printf "\n!! %s\n" "$*" >&2; exit 1; }

say() { printf "%s\n" "$*"; }

# ── banner ───────────────────────────────────────────────────────────────────
say ""
say "  VOID  —  terminal install"
say "  --------------------------------"
say "  target : ${INSTALL_DIR}"
say "  no git : zip pull from GitHub"
say ""

# ── 1. deps check ────────────────────────────────────────────────────────────
bar 5 "checking python..."
command -v python3 >/dev/null 2>&1 || die "python3 (3.10+) missing — https://www.python.org/downloads/"
python3 -c "import venv" >/dev/null 2>&1 || die "venv module missing — try: sudo apt install python3-venv"

bar 10 "checking downloader..."
DOWNLOADER=""
if command -v curl >/dev/null 2>&1; then
    DOWNLOADER="curl"
elif command -v wget >/dev/null 2>&1; then
    DOWNLOADER="wget"
else
    die "need curl or wget to fetch the package"
fi

# ── 2. fetch zip ─────────────────────────────────────────────────────────────
bar 18 "downloading VOID (main)..."
ZIP_PATH="${TMP_DIR}/void.zip"
if [ "$DOWNLOADER" = "curl" ]; then
    curl -fsSL --progress-bar "$ZIP_URL" -o "$ZIP_PATH" 2>/dev/null \
        || curl -fsSL "$ZIP_URL" -o "$ZIP_PATH" \
        || die "download failed — check your network"
else
    wget -q -O "$ZIP_PATH" "$ZIP_URL" || die "download failed — check your network"
fi
[ -s "$ZIP_PATH" ] || die "downloaded archive is empty"

bar 35 "unpacking archive..."
python3 - "$ZIP_PATH" "$TMP_DIR" <<'PY'
import sys, zipfile
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PY

SRC=""
for candidate in "${TMP_DIR}/VOID-main" "${TMP_DIR}/VOID-master"; do
    if [ -d "$candidate" ]; then
        SRC="$candidate"
        break
    fi
done
[ -n "$SRC" ] || die "unexpected archive layout from GitHub"

# ── 3. install files (keep existing .env) ────────────────────────────────────
bar 48 "staging files..."
KEEP_ENV=""
if [ -f "${INSTALL_DIR}/.env" ]; then
    KEEP_ENV="${TMP_DIR}/saved.env"
    cp "${INSTALL_DIR}/.env" "$KEEP_ENV"
fi

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
# copy tree; skip any accidental nested venv from the zip
cp -a "${SRC}/." "$INSTALL_DIR/"
rm -rf "${INSTALL_DIR}/venv" "${INSTALL_DIR}/.git" 2>/dev/null || true

if [ -n "$KEEP_ENV" ]; then
    cp "$KEEP_ENV" "${INSTALL_DIR}/.env"
elif [ -f "${INSTALL_DIR}/.env.example" ]; then
    cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
fi

cd "$INSTALL_DIR"
[ -f main.py ] || die "main.py missing after extract — bad archive?"

bar 55 "config ready"

# ── 4. venv + deps ──────────────────────────────────────────────────────────
bar 60 "building virtualenv..."
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

bar 72 "upgrading pip..."
pip install --upgrade pip >/dev/null

bar 80 "installing packages (this takes a bit)..."
pip install -r requirements.txt >/dev/null
deactivate

# ── 5. launcher ──────────────────────────────────────────────────────────────
bar 92 "wiring 'void' command..."
mkdir -p "$BIN_DIR"
cat > "${BIN_DIR}/void" << 'EOF'
#!/usr/bin/env bash
set -e
INSTALL_DIR="${HOME}/.void-cli"
cd "$INSTALL_DIR" || { echo "VOID is not installed. Re-run the installer."; exit 1; }
if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
fi
# shellcheck disable=SC1091
source venv/bin/activate
exec python main.py "$@"
EOF
chmod +x "${BIN_DIR}/void" 2>/dev/null || true

bar 100 "done"
say ""
say "  installed -> ${INSTALL_DIR}"
say "  launcher  -> ${BIN_DIR}/void"
say ""

if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
    say "  PATH tip (add once, then open a new terminal):"
    say "      export PATH=\"\$HOME/.local/bin:\$PATH\""
    say ""
fi

say "  launch :  void"
say "  update :  re-run this installer (your .env is kept)"
say "  remove :"
say "      rm -rf ~/.void-cli && rm -f ~/.local/bin/void"
say ""
