"""Stable on-disk locations for VOID's local state.

Everything user-specific lives under ~/.void (override with VOID_HOME):
    config.json   connected places (cloud + optional local folder)
    library.db    SQLite catalog of documents and their copies
    cache/        files pulled down from the cloud for chat/summarise
"""

import os
from pathlib import Path


def _void_home() -> Path:
    override = os.getenv("VOID_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".void"


VOID_HOME = _void_home()
CONFIG_PATH = VOID_HOME / "config.json"
DB_PATH = VOID_HOME / "library.db"
CACHE_DIR = VOID_HOME / "cache"
OUTBOX_DIR = VOID_HOME / "outbox"


def ensure_dirs() -> None:
    VOID_HOME.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
