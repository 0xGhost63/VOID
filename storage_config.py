"""Tiny JSON config for connected storage places.

The user sees named places ("VOID Cloud", "Local folder", "Google Drive",
"GitHub"). Nothing here exposes buckets, tokens or sync policies in the UI.

Tokens live in this file too, so it is written with owner-only permissions.
For a stricter setup, keep the whole file in a private directory (VOID_HOME).
"""

import json
import os
from copy import deepcopy

from void_paths import CONFIG_PATH, ensure_dirs

DEFAULT_CONFIG = {
    "version": 3,
    "cloud": {"enabled": True},
    "local": {"enabled": False, "root": ""},
    "gdrive": {
        "enabled": False,
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
        "folder_id": "",
    },
    "github": {
        "enabled": False,
        "token": "",
        "repo": "",
        "branch": "main",
        "root": "VOID",
    },
    "advanced": False,
}


def _merge(base: dict, incoming: dict) -> dict:
    for key, value in incoming.items():
        if key not in base:
            continue
        if isinstance(base[key], dict) and isinstance(value, dict):
            base[key].update(value)
        else:
            base[key] = value
    return base


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return deepcopy(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return _merge(deepcopy(DEFAULT_CONFIG), data if isinstance(data, dict) else {})


def save_config(config: dict) -> None:
    ensure_dirs()
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(CONFIG_PATH)


# ----------------------------------------------------------------------
# local folder
# ----------------------------------------------------------------------
def local_place() -> str | None:
    config = load_config()
    local = config.get("local", {})
    if local.get("enabled") and local.get("root"):
        return local["root"]
    return None


def set_local_place(root: str) -> str:
    root = os.path.abspath(os.path.expanduser(root))
    os.makedirs(root, exist_ok=True)
    config = load_config()
    config["local"] = {"enabled": True, "root": root}
    save_config(config)
    return root


def remove_local_place() -> None:
    config = load_config()
    config["local"] = {"enabled": False, "root": ""}
    save_config(config)


# ----------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------
def github_place() -> dict | None:
    config = load_config()
    github = config.get("github", {})
    if github.get("enabled") and github.get("token") and github.get("repo"):
        return github
    return None


def set_github_place(
    token: str,
    repo: str,
    branch: str = "main",
    root: str = "VOID",
) -> dict:
    config = load_config()
    config["github"] = {
        "enabled": True,
        "token": token.strip(),
        "repo": repo.strip(),
        "branch": (branch or "main").strip(),
        "root": (root or "VOID").strip("/") or "VOID",
    }
    save_config(config)
    return config["github"]


def remove_github_place() -> None:
    config = load_config()
    config["github"] = deepcopy(DEFAULT_CONFIG["github"])
    save_config(config)


# ----------------------------------------------------------------------
# Google Drive
# ----------------------------------------------------------------------
def gdrive_place() -> dict | None:
    config = load_config()
    gdrive = config.get("gdrive", {})
    if (
        gdrive.get("enabled")
        and gdrive.get("client_id")
        and gdrive.get("refresh_token")
        and gdrive.get("folder_id")
    ):
        return gdrive
    return None


def set_gdrive_place(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    folder_id: str,
) -> dict:
    config = load_config()
    config["gdrive"] = {
        "enabled": True,
        "client_id": client_id.strip(),
        "client_secret": (client_secret or "").strip(),
        "refresh_token": refresh_token.strip(),
        "folder_id": folder_id.strip() or "root",
    }
    save_config(config)
    return config["gdrive"]


def remove_gdrive_place() -> None:
    config = load_config()
    config["gdrive"] = deepcopy(DEFAULT_CONFIG["gdrive"])
    save_config(config)
