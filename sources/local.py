"""A folder on the user's machine."""

import os
import shutil

from .base import Entry, StorageProvider


class LocalProvider(StorageProvider):
    kind = "local"
    label = "Local folder"
    writable = True

    def __init__(self, root: str):
        self.root = os.path.realpath(os.path.expanduser(root))

    def path_for(self, document: dict) -> str:
        subject = (document.get("subject") or "UNSORTED").strip().upper()
        title = document.get("title") or "file"
        return os.path.join(self.root, subject, title)

    def subject_from_path(self, path: str) -> str:
        relative = path
        if os.path.isabs(path):
            try:
                relative = os.path.relpath(path, self.root)
            except ValueError:
                pass
        return super().subject_from_path(relative)

    def describe(self) -> str:
        return self.root

    def _abs(self, path: str) -> str:
        target = os.path.realpath(os.path.join(self.root, path))
        if target != self.root and not target.startswith(self.root + os.sep):
            raise ValueError("path escapes the local place")
        return target

    def list(self):
        if not os.path.isdir(self.root):
            return
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [
                name
                for name in dirnames
                if not name.startswith(".")
                and name not in {"node_modules", "__pycache__"}
            ]
            for name in filenames:
                if name.startswith("."):
                    continue
                absolute = os.path.join(dirpath, name)
                try:
                    stat = os.stat(absolute)
                except OSError:
                    continue
                yield Entry(
                    path=os.path.relpath(absolute, self.root),
                    name=name,
                    size=stat.st_size,
                    modified=stat.st_mtime,
                    version=f"{stat.st_mtime}:{stat.st_size}",
                )

    def stat(self, path: str):
        target = self._abs(path)
        if not os.path.isfile(target):
            return None
        stat = os.stat(target)
        return Entry(
            path=path,
            name=os.path.basename(path),
            size=stat.st_size,
            modified=stat.st_mtime,
            version=f"{stat.st_mtime}:{stat.st_size}",
        )

    def read(self, path: str):
        return open(self._abs(path), "rb")

    def write(self, path: str, data, message="") -> Entry:
        destination = self._abs(path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if hasattr(data, "read"):
            with open(destination, "wb") as handle:
                shutil.copyfileobj(data, handle)
        else:
            with open(destination, "wb") as handle:
                handle.write(data)
        stat = os.stat(destination)
        return Entry(
            path=path,
            name=os.path.basename(path),
            size=stat.st_size,
            modified=stat.st_mtime,
            version=f"{stat.st_mtime}:{stat.st_size}",
        )

    def delete(self, path: str) -> None:
        target = self._abs(path)
        if os.path.exists(target):
            os.remove(target)

    def exists(self, path: str) -> bool:
        return os.path.exists(self._abs(path))
