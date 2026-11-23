"""GitHub repository storage, using the Contents API.

The user supplies a fine-grained PAT with **Contents: read and write** on one
repository. VOID stores files under a configurable folder (default ``VOID/``)
so the rest of the repository stays untouched.

Catalog paths are relative to that folder (``SUBJECT/file.pdf``); the provider
prepends the folder for every API call.
"""

import base64
import io
import os
from urllib.parse import quote

import requests

from .base import Entry, StorageProvider

API = "https://api.github.com"
MAX_FILE_BYTES = 95 * 1024 * 1024  # GitHub hard limit is 100 MB per blob


class GitHubError(RuntimeError):
    pass


class GitHubProvider(StorageProvider):
    kind = "github"
    label = "GitHub"
    writable = True

    def __init__(self, config: dict | None = None):
        config = config or {}
        self.token = (config.get("token") or "").strip()
        self.repo = (config.get("repo") or "").strip()
        self.branch = (config.get("branch") or "main").strip()
        self.root = (config.get("root") or "VOID").strip("/")
        self.session = requests.Session()
        if self.token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "VOID-CLI",
                }
            )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.token and "/" in self.repo)

    def describe(self) -> str:
        if not self.configured:
            return "needs setup"
        return f"{self.repo} @ {self.branch}"

    def _remote(self, path: str) -> str:
        path = str(path).replace("\\", "/").lstrip("/")
        if not self.root:
            return path
        return f"{self.root}/{path}" if path else self.root

    def _relative(self, remote_path: str) -> str | None:
        remote_path = str(remote_path).replace("\\", "/").lstrip("/")
        prefix = f"{self.root}/" if self.root else ""
        if prefix and not remote_path.startswith(prefix):
            return None
        relative = remote_path[len(prefix) :]
        if not relative or relative.endswith("/"):
            return None
        return relative

    def _contents_url(self, path: str) -> str:
        remote = self._remote(path)
        encoded = quote(remote, safe="/")
        return f"{API}/repos/{self.repo}/contents/{encoded}"

    def _request(self, method: str, url: str, **kwargs):
        try:
            response = self.session.request(method, url, timeout=60, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise GitHubError(f"GitHub is unreachable: {exc}") from exc

        if response.status_code in (404, 409):
            # 404 = missing; 409 on the Trees API = empty repository.
            return None
        if response.status_code == 401:
            raise GitHubError("GitHub token is invalid or expired")
        if response.status_code == 403:
            if response.headers.get("X-RateLimit-Remaining") == "0":
                raise GitHubError(
                    "GitHub rate limit reached; try again later or use a PAT"
                )
            raise GitHubError(f"GitHub refused the request: {response.text[:200]}")
        if response.status_code >= 400:
            raise GitHubError(
                f"GitHub error {response.status_code}: {response.text[:200]}"
            )
        return response

    def _contents(self, path: str):
        response = self._request(
            "GET", self._contents_url(path), params={"ref": self.branch}
        )
        if response is None:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None  # a directory or an empty/missing payload
        if data.get("type") not in (None, "file"):
            return None
        return data

    def _entry_from_content(self, relative: str, data: dict) -> Entry:
        return Entry(
            path=relative,
            name=os.path.basename(relative),
            size=int(data.get("size") or 0),
            modified=0.0,
            version=data.get("sha"),
            remote_id=data.get("sha"),
        )

    # ------------------------------------------------------------------
    # provider interface
    # ------------------------------------------------------------------
    def list(self):
        if not self.configured:
            return
        # The Trees API returns the whole repository in one request.
        tree_url = (
            f"{API}/repos/{self.repo}/git/trees/"
            f"{quote(self.branch, safe='')}"
        )
        response = self._request("GET", tree_url, params={"recursive": "1"})
        if response is not None:
            data = response.json()
            if not data.get("truncated"):
                for item in data.get("tree") or []:
                    if item.get("type") != "blob":
                        continue
                    relative = self._relative(item.get("path", ""))
                    if relative is None:
                        continue
                    yield Entry(
                        path=relative,
                        name=os.path.basename(relative),
                        size=int(item.get("size") or 0),
                        modified=0.0,
                        version=item.get("sha"),
                        remote_id=item.get("sha"),
                    )
                return
        # Large or empty repo: fall back to walking the folder.
        yield from self._walk("")

    def _walk(self, remote_prefix: str):
        url = self._contents_url(remote_prefix)
        response = self._request("GET", url, params={"ref": self.branch})
        if response is None:
            return
        try:
            data = response.json()
        except ValueError:
            return
        if isinstance(data, dict):
            relative = self._relative(data.get("path", ""))
            if relative:
                yield self._entry_from_content(relative, data)
            return
        for item in data:
            if item.get("type") == "dir":
                yield from self._walk(item.get("path", ""))
            elif item.get("type") == "file":
                relative = self._relative(item.get("path", ""))
                if relative:
                    yield self._entry_from_content(relative, item)

    def stat(self, path: str):
        if not self.configured:
            return None
        data = self._contents(path)
        if data is None:
            return None
        return self._entry_from_content(path, data)

    def read(self, path: str):
        response = self._request(
            "GET",
            self._contents_url(path),
            params={"ref": self.branch},
            headers={"Accept": "application/vnd.github.raw"},
        )
        if response is None:
            raise FileNotFoundError(path)
        return io.BytesIO(response.content)

    def write(self, path: str, data, message: str = "") -> Entry:
        if hasattr(data, "read"):
            data = data.read()
        data = bytes(data)
        if len(data) > MAX_FILE_BYTES:
            raise GitHubError(
                f"GitHub rejects files over 100 MB ({len(data)} bytes); "
                "use Drive or a local folder for this one"
            )
        existing = self._contents(path)
        payload = {
            "message": message or f"VOID: update {self._remote(path)}",
            "content": base64.b64encode(data).decode("ascii"),
            "branch": self.branch,
        }
        if existing and existing.get("sha"):
            payload["sha"] = existing["sha"]
        response = self._request("PUT", self._contents_url(path), json=payload)
        if response is None:
            raise GitHubError(f"Could not write {path}")
        return self.stat(path) or Entry(
            path=path,
            name=os.path.basename(path),
            size=len(data),
        )

    def delete(self, path: str) -> None:
        existing = self._contents(path)
        if not existing:
            return
        self._request(
            "DELETE",
            self._contents_url(path),
            json={
                "message": f"VOID: delete {self._remote(path)}",
                "sha": existing.get("sha"),
                "branch": self.branch,
            },
        )

    def share_link(self, path: str):
        if not self.configured:
            return None
        remote = quote(self._remote(path), safe="/")
        return f"https://github.com/{self.repo}/blob/{quote(self.branch)}/{remote}"

    def test(self) -> None:
        if not self.configured:
            raise GitHubError("set a token and a repository (owner/name)")
        response = self._request("GET", f"{API}/repos/{self.repo}")
        if response is None:
            raise GitHubError(f"repository {self.repo} was not found")
