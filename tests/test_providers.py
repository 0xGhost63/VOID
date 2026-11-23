"""Provider-level tests for GitHub and Google Drive (no network).

These exercise the real adapter code with a fake HTTP layer, so path mapping,
listing, reads, writes, deletes and share links are covered without tokens.

    python3 tests/test_providers.py
"""

import base64
import hashlib
import io
import os
import sys
import time
import traceback
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sources.gdrive import GoogleDriveProvider
from sources.github import GitHubProvider

PASS = 0
FAIL = 0


def check(label, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}  {detail}")


class FakeResponse:
    def __init__(self, status=200, json_data=None, content=b"", headers=None):
        self.status_code = status
        self._json = json_data
        self.content = content
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._json


class GitHubHTTP:
    """Minimal in-memory Contents + Trees API."""

    def __init__(self):
        self.files = {}
        self.calls = []

    def sha(self, path):
        return hashlib.sha1(self.files[path]).hexdigest()

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if "/git/trees/" in url:
            tree = [
                {
                    "type": "blob",
                    "path": f"VOID/{path}",
                    "size": len(data),
                    "sha": self.sha(path),
                }
                for path, data in self.files.items()
            ]
            return FakeResponse(200, {"tree": tree, "truncated": False})

        if "/repos/o/r" in url and "/contents/" not in url:
            return FakeResponse(200, {"full_name": "o/r"})

        remote = unquote(url.split("/contents/", 1)[1])
        relative = remote[len("VOID/") :] if remote.startswith("VOID/") else remote

        if method == "GET":
            if relative not in self.files:
                return FakeResponse(404)
            if kwargs.get("headers", {}).get("Accept") == "application/vnd.github.raw":
                return FakeResponse(200, content=self.files[relative])
            return FakeResponse(
                200,
                {
                    "type": "file",
                    "path": remote,
                    "name": os.path.basename(relative),
                    "size": len(self.files[relative]),
                    "sha": self.sha(relative),
                    "content": "",
                },
            )

        if method == "PUT":
            payload = kwargs["json"]
            self.files[relative] = base64.b64decode(payload["content"])
            return FakeResponse(200, {"content": {"path": remote}})

        if method == "DELETE":
            self.files.pop(relative, None)
            return FakeResponse(200, {})
        return FakeResponse(400)


def test_github():
    print("\n[GitHub] adapter with a fake Contents API")
    provider = GitHubProvider(
        {"token": "t", "repo": "o/r", "branch": "main", "root": "VOID"}
    )
    http = GitHubHTTP()
    provider._request = http

    entry = provider.write("MATH/notes.pdf", b"hello")
    check("write created file", http.files.get("MATH/notes.pdf") == b"hello")
    check("write returned an entry", entry is not None and entry.size == 5, entry)
    check("version is the blob sha", entry.version == http.sha("MATH/notes.pdf"))

    listed = list(provider.list())
    check("list sees the file", [item.path for item in listed] == ["MATH/notes.pdf"])
    check("list size", listed[0].size == 5, listed[0])

    check("stat finds it", provider.stat("MATH/notes.pdf") is not None)
    check("stat missing", provider.stat("MATH/nope.pdf") is None)
    check("read bytes", provider.read("MATH/notes.pdf").read() == b"hello")
    check(
        "share link",
        provider.share_link("MATH/notes.pdf")
        == "https://github.com/o/r/blob/main/VOID/MATH/notes.pdf",
    )

    provider.write("MATH/notes.pdf", b"updated")
    check("overwrite updates bytes", http.files["MATH/notes.pdf"] == b"updated")

    provider.delete("MATH/notes.pdf")
    check("delete removes file", "MATH/notes.pdf" not in http.files)
    provider.delete("MATH/missing.pdf")
    check("delete missing is a no-op", True)

    provider.test()
    check("test() reaches the repo", True)


class DriveHTTP:
    """In-memory Drive files+folders for _list_children and media reads."""

    def __init__(self):
        self.root = [
            {
                "id": "F1",
                "name": "MATH",
                "mimeType": "application/vnd.google-apps.folder",
            }
        ]
        self.math = [
            {
                "id": "D1",
                "name": "notes.pdf",
                "mimeType": "application/pdf",
                "size": "5",
                "modifiedTime": "2026-01-02T03:04:05Z",
                "md5Checksum": "abc",
            }
        ]
        self.deleted = []

    def list_children(self, folder_id):
        if folder_id == "root":
            return self.root
        if folder_id == "F1":
            return self.math
        return []


def test_gdrive():
    print("\n[Google Drive] adapter with an in-memory folder tree")
    provider = GoogleDriveProvider(
        {
            "client_id": "cid",
            "refresh_token": "refresh",
            "folder_id": "root",
            "access_token": "token",
            "token_expiry": time.time() + 3600,
        }
    )
    http = DriveHTTP()
    provider._list_children = http.list_children

    index = provider._build_index(force=True)
    check("index finds the file", list(index) == ["MATH/notes.pdf"], list(index))
    check("stat finds it", provider.stat("MATH/notes.pdf") is not None)
    check("stat missing", provider.stat("MATH/nope.pdf") is None)

    media = FakeResponse(200, content=b"hello")
    provider._request = lambda method, url, **kwargs: media
    check("read bytes", provider.read("MATH/notes.pdf").read() == b"hello")
    check(
        "share link",
        provider.share_link("MATH/notes.pdf")
        == "https://drive.google.com/file/d/D1/view",
    )

    uploads = []

    def fake_ensure_folder(segments):
        return "F1"

    def fake_upload(file_id, name, parent, data):
        uploads.append((file_id, name, parent, data))

    provider._ensure_folder = fake_ensure_folder
    provider._upload_media = fake_upload
    provider._index = {}
    provider.write("MATH/new.pdf", b"new bytes")
    check(
        "new file upload",
        uploads == [(None, "new.pdf", "F1", b"new bytes")],
        uploads,
    )

    uploads.clear()
    provider._index = {"MATH/notes.pdf": {"id": "D1"}}
    provider.write("MATH/notes.pdf", b"replacement")
    check(
        "existing file update",
        uploads == [("D1", "notes.pdf", None, b"replacement")],
        uploads,
    )

    deletions = []
    provider._index = {"MATH/notes.pdf": {"id": "D1"}}

    def fake_request(method, url, **kwargs):
        deletions.append((method, url))
        return FakeResponse(200, {})

    provider._request = fake_request
    provider.delete("MATH/notes.pdf")
    check(
        "delete calls the API",
        any(method == "DELETE" and "D1" in url for method, url in deletions),
        deletions,
    )

    provider._list_children = http.list_children
    provider.test()
    check("test() lists the root", True)


def main():
    tests = [test_github, test_gdrive]
    for test in tests:
        try:
            test()
        except Exception:
            global FAIL
            FAIL += 1
            print(f"  ERROR in {test.__name__}")
            traceback.print_exc()

    print(f"\n{'=' * 50}\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
