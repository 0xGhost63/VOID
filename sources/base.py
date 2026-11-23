"""Provider interface shared by every storage place."""

import hashlib
from dataclasses import dataclass
from typing import BinaryIO, Optional


@dataclass
class Entry:
    path: str
    name: str
    size: int = 0
    modified: float = 0.0
    checksum: Optional[str] = None
    remote_id: Optional[str] = None
    is_dir: bool = False
    version: Optional[str] = None


class StorageProvider:
    kind = "base"
    label = "Storage"
    writable = False

    def list(self):
        raise NotImplementedError

    def stat(self, path) -> Optional[Entry]:
        return None

    def read(self, path) -> BinaryIO:
        raise NotImplementedError

    def write(self, path, data, message="") -> Entry:
        raise NotImplementedError

    def delete(self, path) -> None:
        raise NotImplementedError

    def exists(self, path) -> bool:
        return self.stat(path) is not None

    def share_link(self, path) -> Optional[str]:
        return None

    def path_for(self, document: dict) -> str:
        """Canonical catalog path for a logical document (relative to the place)."""
        subject = (document.get("subject") or "UNSORTED").strip().upper()
        title = document.get("title") or "file"
        return f"{subject}/{title}"

    def subject_from_path(self, path: str) -> str:
        """Infer the subject from a catalog path."""
        parts = [part for part in str(path).replace("\\", "/").split("/") if part]
        if len(parts) >= 2:
            return parts[0].strip().upper()
        return "UNSORTED"

    def describe(self) -> str:
        return self.label

    def test(self) -> None:
        """Raise a helpful error if the place is not reachable/authorized."""
        self.list()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(stream, chunk_size=1024 * 1024) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(chunk_size), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256_file(path) -> str:
    with open(path, "rb") as handle:
        return sha256_stream(handle)
