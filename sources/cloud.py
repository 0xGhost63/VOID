"""VOID Cloud, backed by the existing Supabase storage bucket."""

import io
import mimetypes
import os
from datetime import datetime

from .base import Entry, StorageProvider

BUCKET = "VOID_FILES"


def _parse_iso(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


class CloudProvider(StorageProvider):
    kind = "cloud"
    label = "VOID Cloud"
    writable = True

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._list_cache = {}

    def path_for(self, document: dict) -> str:
        subject = (document.get("subject") or "UNSORTED").strip().upper()
        title = document.get("title") or "file"
        return f"{self.user_id}/{subject}/{title}"

    def subject_from_path(self, path: str) -> str:
        parts = str(path).split("/")
        if len(parts) >= 3:
            return parts[1].strip().upper()
        return super().subject_from_path(path)

    def describe(self) -> str:
        return f"bucket {BUCKET}"

    @property
    def supabase(self):
        # Imported lazily so local-only use never touches Supabase.
        import authentication as athu

        return athu.supabase

    def reset_cache(self) -> None:
        self._list_cache = {}

    def _list(self, folder: str):
        if folder not in self._list_cache:
            self._list_cache[folder] = self.supabase.storage.from_(BUCKET).list(folder)
        return self._list_cache[folder]

    def _invalidate(self, path: str) -> None:
        self._list_cache.pop(os.path.dirname(path), None)

    def stat(self, path: str):
        folder = os.path.dirname(path)
        name = os.path.basename(path)
        try:
            items = self._list(folder)
        except Exception:
            return None
        for item in items:
            if item.get("name") != name:
                continue
            metadata = item.get("metadata") or {}
            raw_size = metadata.get("size") or item.get("size") or 0
            try:
                size = int(raw_size)
            except (TypeError, ValueError):
                size = 0
            updated = item.get("updated_at") or item.get("created_at") or ""
            etag = metadata.get("eTag") or metadata.get("etag") or ""
            return Entry(
                path=path,
                name=name,
                size=size,
                modified=_parse_iso(updated),
                remote_id=item.get("id"),
                version=f"{updated}|{size}|{etag}",
            )
        return None

    def read(self, path: str):
        data = self.supabase.storage.from_(BUCKET).download(path)
        return io.BytesIO(data)

    def write(self, path: str, data, message="") -> Entry:
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        payload = data if hasattr(data, "read") else io.BytesIO(data)
        self._invalidate(path)
        self.supabase.storage.from_(BUCKET).upload(
            path=path,
            file=payload,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        self._invalidate(path)
        size = 0
        try:
            payload.seek(0, os.SEEK_END)
            size = payload.tell()
        except Exception:
            pass
        return Entry(path=path, name=os.path.basename(path), size=size)

    def delete(self, path: str) -> None:
        self._invalidate(path)
        self.supabase.storage.from_(BUCKET).remove([path])
        self._invalidate(path)

    def exists(self, path: str) -> bool:
        return self.stat(path) is not None

    def list_names(self, folder: str):
        try:
            return {item.get("name") for item in self._list(folder)}
        except Exception:
            return set()

    def share_link(self, path: str):
        try:
            result = self.supabase.storage.from_(BUCKET).create_signed_url(path, 3600)
        except Exception:
            return None
        if isinstance(result, dict):
            return (
                result.get("signedURL")
                or result.get("signedUrl")
                or result.get("signed_url")
            )
        return None
