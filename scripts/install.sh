#!/usr/bin/env bash
set -euo pipefail

REPO="0xGhost63/VOID"
ZIP_URL="https://github.com/${REPO}/archive/refs/heads/main.zip"
API_URL="https://api.github.com/repos/${REPO}/commits/main"
WEB_URL="https://0xghost-void.vercel.app"
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

bar 60 "building virtualenv..."
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate

bar 72 "upgrading pip..."
pip install --upgrade pip >/dev/null

bar 80 "installing packages (this takes a bit)..."
pip install -r requirements.txt >/dev/null
deactivate

# ── stash the commit we just installed, so the launcher doesn't think ────────
# ── an update is available on its very first run ─────────────────────────────
bar 88 "recording version..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$API_URL" 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('sha',''))" 2>/dev/null \
        > "${INSTALL_DIR}/.void-commit" || true
fi

bar 92 "wiring 'void' command..."
mkdir -p "$BIN_DIR"
cat > "${BIN_DIR}/void" << LAUNCHER_EOF
#!/usr/bin/env bash
set -e
INSTALL_DIR="\${HOME}/.void-cli"
BIN_PATH="\${HOME}/.local/bin/void"
REPO="${REPO}"
API_URL="${API_URL}"
ZIP_URL="${ZIP_URL}"
WEB_URL="${WEB_URL}"

# ── --web : open the landing page ────────────────────────────────────────────
if [ "\${1:-}" = "--web" ]; then
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "\$WEB_URL" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then
        open "\$WEB_URL"
    elif command -v wslview >/dev/null 2>&1; then
        wslview "\$WEB_URL"
    else
        echo "Open this in your browser: \$WEB_URL"
    fi
    exit 0
fi

# ── --delete : wipe all app data ─────────────────────────────────────────────
if [ "\${1:-}" = "--delete" ]; then
    echo "This will permanently delete VOID and all its data:"
    echo "  \${INSTALL_DIR}"
    read -r -p "Are you sure? [y/N] " confirm
    case "\$confirm" in
        y|Y|yes|YES)
            rm -rf "\${INSTALL_DIR}"
            rm -f "\$BIN_PATH"
            echo "VOID has been removed."
            ;;
        *)
            echo "Cancelled."
            ;;
    esac
    exit 0
fi

cd "\$INSTALL_DIR" || { echo "VOID is not installed. Re-run the installer."; exit 1; }
if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
fi

# ── check for updates against the latest commit on main ──────────────────────
if command -v curl >/dev/null 2>&1; then
    LATEST_SHA="\$(curl -fsSL "\$API_URL" 2>/dev/null \\
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('sha',''))" 2>/dev/null || true)"
    LOCAL_SHA=""
    [ -f .void-commit ] && LOCAL_SHA="\$(cat .void-commit)"
    if [ -n "\$LATEST_SHA" ] && [ "\$LATEST_SHA" != "\$LOCAL_SHA" ]; then
        echo "Update found — updating VOID..."
        TMP_UPDATE="\$(mktemp -d)"
        if curl -fsSL "\$ZIP_URL" -o "\${TMP_UPDATE}/void.zip" 2>/dev/null; then
            python3 - "\${TMP_UPDATE}/void.zip" "\$TMP_UPDATE" <<'PY'
import sys, zipfile
zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])
PY
            UPD_SRC=""
            for candidate in "\${TMP_UPDATE}/VOID-main" "\${TMP_UPDATE}/VOID-master"; do
                [ -d "\$candidate" ] && UPD_SRC="\$candidate" && break
            done
            if [ -n "\$UPD_SRC" ]; then
                cp -a "\${UPD_SRC}/." "\$INSTALL_DIR/"
                echo "\$LATEST_SHA" > "\${INSTALL_DIR}/.void-commit"
                if [ -f requirements.txt ]; then
                    # shellcheck disable=SC1091
                    source venv/bin/activate
                    pip install -q --upgrade -r requirements.txt >/dev/null 2>&1 || true
                    deactivate
                fi
                echo "Updated to latest version."
            fi
        fi
        rm -rf "\$TMP_UPDATE"
    fi
fi

# shellcheck disable=SC1091
source venv/bin/activate
exec python main.py "\$@"
LAUNCHER_EOF
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

say "  launch        :  void"
say "  open webpage  :  void --web"
say "  wipe app data :  void --delete"
say ""