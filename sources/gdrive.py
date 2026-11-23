"""Google Drive storage provider (Drive API v3).

The user authorizes VOID once with an OAuth refresh token. Files live under a
single Drive folder (default ``VOID``); catalog paths are relative to it
(``SUBJECT/file.pdf``).

Large files use Drive's resumable upload endpoint, so PDFs over 5 MB work.
"""

import io
import os
import time
from datetime import datetime

import requests

from .base import Entry, StorageProvider

DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
FOLDER_MIME = "application/vnd.google-apps.folder"
FIELDS = (
    "nextPageToken, files(id,name,mimeType,size,modifiedTime,md5Checksum,"
    "webViewLink)"
)


def _parse_time(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _escape_q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveProvider(StorageProvider):
    kind = "gdrive"
    label = "Google Drive"
    writable = True

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.client_id = (config.get("client_id") or "").strip()
        self.client_secret = (config.get("client_secret") or "").strip()
        self.refresh_token = (config.get("refresh_token") or "").strip()
        self.folder_id = (config.get("folder_id") or "root").strip() or "root"
        self._access_token = (config.get("access_token") or "").strip()
        self._token_expiry = float(config.get("token_expiry") or 0)
        self._index = None
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # auth
    # ------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.refresh_token)

    def describe(self) -> str:
        if not self.configured:
            return "needs setup"
        return f"folder {self.folder_id}"

    def _token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token
        if not self.configured:
            raise RuntimeError("Google Drive is not authorized; reconnect it")
        payload = {
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        try:
            response = requests.post(TOKEN_URL, data=payload, timeout=30)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Google Drive is unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise RuntimeError(
                "Google Drive authorization expired; reconnect Google Drive "
                f"({response.text[:160]})"
            )
        data = response.json()
        self._access_token = data.get("access_token", "")
        self._token_expiry = time.time() + int(data.get("expires_in", 3600))
        if not self._access_token:
            raise RuntimeError("Google Drive did not return an access token")
        return self._access_token

    def _request(self, method: str, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {self._token()}"
        try:
            response = self.session.request(
                method, url, headers=headers, timeout=120, **kwargs
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Google Drive is unreachable: {exc}") from exc
        if response.status_code == 401:
            self._access_token = ""
            self._token_expiry = 0
            raise RuntimeError("Google Drive authorization expired; reconnect it")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise RuntimeError(
                f"Google Drive error {response.status_code}: {response.text[:200]}"
            )
        return response

    # ------------------------------------------------------------------
    # listing / lookup
    # ------------------------------------------------------------------
    def _list_children(self, folder_id: str):
        files = []
        page_token = None
        while True:
            params = {
                "q": f"'{_escape_q(folder_id)}' in parents and trashed=false",
                "fields": FIELDS,
                "pageSize": 1000,
            }
            if page_token:
                params["pageToken"] = page_token
            response = self._request("GET", f"{DRIVE}/files", params=params)
            if response is None:
                return files
            data = response.json()
            files.extend(data.get("files") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                return files

    def _build_index(self, force: bool = False) -> dict:
        if self._index is not None and not force:
            return self._index
        index = {}
        stack = [(self.folder_id, "")]
        seen_folders = set()
        while stack:
            folder_id, prefix = stack.pop()
            if folder_id in seen_folders:
                continue
            seen_folders.add(folder_id)
            for item in self._list_children(folder_id):
                name = item.get("name") or ""
                relative = f"{prefix}/{name}" if prefix else name
                if item.get("mimeType") == FOLDER_MIME:
                    stack.append((item.get("id"), relative))
                else:
                    index[relative] = item
        self._index = index
        return index

    def invalidate(self) -> None:
        self._index = None

    def _entry(self, path: str, item: dict) -> Entry:
        size = item.get("size") or 0
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 0
        modified = _parse_time(item.get("modifiedTime", ""))
        version = "|".join(
            [
                item.get("modifiedTime", ""),
                str(size),
                item.get("md5Checksum", ""),
            ]
        )
        return Entry(
            path=path,
            name=os.path.basename(path),
            size=size,
            modified=modified,
            version=version,
            remote_id=item.get("id"),
        )

    # ------------------------------------------------------------------
    # provider interface
    # ------------------------------------------------------------------
    def list(self):
        if not self.configured:
            return
        for path, item in self._build_index(force=True).items():
            yield self._entry(path, item)

    def stat(self, path: str):
        if not self.configured:
            return None
        path = str(path).replace("\\", "/").strip("/")
        if not path:
            return None
        item = self._build_index().get(path)
        if item is None:
            return None
        return self._entry(path, item)

    def read(self, path: str):
        entry = self.stat(path)
        if entry is None or not entry.remote_id:
            raise FileNotFoundError(path)
        response = self._request(
            "GET", f"{DRIVE}/files/{entry.remote_id}", params={"alt": "media"}
        )
        if response is None:
            raise FileNotFoundError(path)
        return io.BytesIO(response.content)

    def _find_child(self, parent_id: str, name: str, folders_only: bool = False):
        query = (
            f"'{_escape_q(parent_id)}' in parents and name='{_escape_q(name)}' "
            "and trashed=false"
        )
        if folders_only:
            query += f" and mimeType='{FOLDER_MIME}'"
        response = self._request(
            "GET",
            f"{DRIVE}/files",
            params={"q": query, "fields": "files(id,name,mimeType)", "pageSize": 10},
        )
        if response is None:
            return None
        files = response.json().get("files") or []
        return files[0] if files else None

    def _ensure_folder(self, segments) -> str:
        parent = self.folder_id
        for name in segments:
            name = (name or "").strip()
            if not name:
                continue
            existing = self._find_child(parent, name, folders_only=True)
            if existing:
                parent = existing["id"]
                continue
            response = self._request(
                "POST",
                f"{DRIVE}/files",
                json={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
            )
            if response is None:
                raise RuntimeError(f"Could not create Drive folder {name!r}")
            parent = response.json()["id"]
        return parent

    def ensure_folder(self, path: str) -> str:
        """Create a folder path under the root and return its id."""
        segments = [part for part in str(path).split("/") if part]
        return self._ensure_folder(segments)

    def _upload_media(self, file_id, name, parent, data: bytes) -> None:
        headers = {
            "X-Upload-Content-Type": "application/octet-stream",
            "X-Upload-Content-Length": str(len(data)),
        }
        if file_id:
            response = self._request(
                "PATCH",
                f"{UPLOAD}/files/{file_id}?uploadType=resumable",
                json={},
                headers=headers,
            )
        else:
            response = self._request(
                "POST",
                f"{UPLOAD}/files?uploadType=resumable",
                json={"name": name, "parents": [parent]},
                headers=headers,
            )
        if response is None:
            raise RuntimeError(f"Could not start a Drive upload for {name}")
        session_url = response.headers.get("Location")
        if not session_url:
            raise RuntimeError("Google Drive did not return an upload session")
        put = self.session.put(
            session_url,
            data=data,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(data)),
                "Authorization": f"Bearer {self._token()}",
            },
            timeout=600,
        )
        if put.status_code not in (200, 201):
            raise RuntimeError(
                f"Google Drive upload failed ({put.status_code}): "
                f"{put.text[:200]}"
            )

    def write(self, path: str, data, message: str = "") -> Entry:
        if not self.configured:
            raise RuntimeError("Google Drive is not authorized")
        if hasattr(data, "read"):
            data = data.read()
        data = bytes(data)
        path = str(path).replace("\\", "/").strip("/")
        segments = [part for part in path.split("/") if part]
        if not segments:
            raise ValueError("empty Drive path")
        name = segments[-1]
        existing = self._build_index().get(path)
        parent = None
        if existing is None:
            parent = self._ensure_folder(segments[:-1])
        self._upload_media(
            existing.get("id") if existing else None, name, parent, data
        )
        self._index = None
        return self.stat(path) or Entry(path=path, name=name, size=len(data))

    def delete(self, path: str) -> None:
        entry = self.stat(path)
        if entry is None or not entry.remote_id:
            return
        self._request("DELETE", f"{DRIVE}/files/{entry.remote_id}")
        self._index = None

    def share_link(self, path: str):
        entry = self.stat(path)
        if entry is None or not entry.remote_id:
            return None
        return f"https://drive.google.com/file/d/{entry.remote_id}/view"

    def test(self) -> None:
        if not self.configured:
            raise RuntimeError("Google Drive is not authorized")
        self._list_children(self.folder_id)
