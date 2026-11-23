#!/usr/bin/env python3
"""VOID local web dashboard.

A tiny, dependency-free HTTP server that exposes the ``library.Library``
facade to the browser.  Only the Python standard library is used, and every
library call runs on a dedicated, single-owner worker thread so SQLite sees
one connection per thread.

Run with::

    python3 web/server.py --host 127.0.0.1 --port 8000

The user is resolved per request from ``VOID_USER_ID``, then ``?user=``, then
the first user id in ``~/.void/library.db``, and finally ``"local"``.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import queue
import shutil
import sqlite3
import sys
import tempfile
import threading
import traceback
import urllib.parse
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / library import
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import library  # noqa: E402  (import must follow the sys.path setup)
import storage_config  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

MAX_UPLOAD = 100 * 1024 * 1024  # 100 MiB request body limit
MAX_JSON = 1024 * 1024

STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/favicon.ico": ("favicon.svg", "image/svg+xml"),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class HttpFailure(Exception):
    """An error that is safe to show to the browser."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Per-user library worker
# ---------------------------------------------------------------------------

_WORKERS: dict[str, "_LibraryWorker"] = {}
_WORKERS_LOCK = threading.Lock()
_LIBRARY_INIT_LOCK = threading.Lock()


class WorkerUnavailable(RuntimeError):
    pass


class _LibraryWorker:
    """Owns one Library instance and executes every call on its thread."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._jobs: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._init_error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"void-library-{user_id[:24]}",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()
        if self._init_error is not None:
            raise WorkerUnavailable(str(self._init_error)) from self._init_error

    def _run(self) -> None:
        try:
            with _LIBRARY_INIT_LOCK:
                lib = library.for_user(self.user_id)
        except BaseException as exc:  # noqa: BLE001 - report to the waiting request
            self._init_error = exc
            self._ready.set()
            return

        self._ready.set()
        while True:
            fn, args, kwargs, box = self._jobs.get()
            try:
                box["value"] = fn(lib, *args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - relayed to the caller
                box["error"] = exc
            finally:
                box["event"].set()

    def call(self, fn, *args, **kwargs):
        box: dict = {"event": threading.Event()}
        self._jobs.put((fn, args, kwargs, box))
        box["event"].wait()
        if "error" in box:
            raise box["error"]
        return box.get("value")


def library_worker(user_id: str) -> _LibraryWorker:
    with _WORKERS_LOCK:
        worker = _WORKERS.get(user_id)
        if worker is None:
            worker = _LibraryWorker(user_id)
            _WORKERS[user_id] = worker
        return worker


# ---------------------------------------------------------------------------
# Worker-side library operations (public Library API only)
# ---------------------------------------------------------------------------


def _snapshot(lib, user_id: str) -> dict:
    documents = lib.list_documents()
    places = lib.status()
    subjects = lib.subjects()

    pending = 0
    for document in documents:
        states = {str(state).lower() for state in (document.get("states") or [])}
        if "pending" in states:
            pending += 1

    return {
        "user_id": user_id,
        "places": places,
        "documents": len(documents),
        "subjects": subjects,
        "pending": pending,
    }


def _list_documents(lib, subject: str | None, query: str | None) -> list[dict]:
    documents = lib.list_documents(subject=subject or None)
    needle = (query or "").strip().lower()
    if not needle:
        return documents

    matches = []
    for document in documents:
        title = str(document.get("title") or "").lower()
        summary = str(document.get("summary") or "").lower()
        if needle in title or needle in summary:
            matches.append(document)
    return matches


def _sync_and_snapshot(lib, user_id: str) -> dict:
    report = lib.sync(quiet=True) or {}
    return {"report": report, "status": _snapshot(lib, user_id)}


def _download_target(lib, doc_id: str) -> tuple[str, str]:
    path = lib.open_document(doc_id)
    title = None
    try:
        for document in lib.list_documents():
            if document.get("doc_id") == doc_id or document.get("id") == doc_id:
                title = document.get("title")
                break
    except Exception:
        title = None
    filename = title or os.path.basename(path) or "download"
    return path, filename


def _delete_document(lib, doc_id: str) -> list[str]:
    errors = lib.delete_document(doc_id) or []
    return [str(error) for error in errors]


def _import_file(lib, path: str, subject: str, doc_type, summary):
    doc_id, results, errors = lib.import_file(
        path,
        subject,
        doc_type=doc_type,
        summary=summary,
    )
    clean_results = []
    for item in results or []:
        try:
            kind, location, status = item[0], item[1], item[2]
        except (IndexError, KeyError, TypeError):
            continue
        clean_results.append(
            {
                "place": str(kind),
                "path": str(location),
                "status": str(status),
            }
        )
    return {
        "doc_id": doc_id,
        "results": clean_results,
        "errors": [str(error) for error in (errors or [])],
    }


# ---------------------------------------------------------------------------
# User resolution
# ---------------------------------------------------------------------------


def _void_home() -> Path:
    override = os.environ.get("VOID_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".void"


def _db_user_id() -> str | None:
    db_path = _void_home() / "library.db"
    if not db_path.is_file():
        return None
    try:
        connection = sqlite3.connect(
            f"{db_path.as_uri()}?mode=ro", uri=True, timeout=1.0
        )
        try:
            row = connection.execute(
                """
                SELECT user_id FROM documents
                WHERE user_id IS NOT NULL AND user_id != ''
                ORDER BY created_at LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, OSError, ValueError):
        return None
    if row and str(row[0]).strip():
        return str(row[0]).strip()
    return None


def resolve_user_id(query: str) -> str:
    from_env = os.environ.get("VOID_USER_ID", "").strip()
    if from_env:
        return from_env

    params = urllib.parse.parse_qs(query, keep_blank_values=False)
    from_query = (params.get("user") or [""])[0].strip()
    if from_query:
        return from_query

    from_db = _db_user_id()
    if from_db:
        return from_db
    return "local"


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class VoidHandler(BaseHTTPRequestHandler):
    server_version = "VoidDashboard/1.0"
    protocol_version = "HTTP/1.0"  # simple, safe connection-per-request

    # -- low-level response helpers ----------------------------------------

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: int = 200,
        cache_control: str = "no-store",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self._security_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send_bytes(
            body,
            "application/json; charset=utf-8",
            status=status,
            cache_control="no-store",
        )

    def _plain(self, text: str, status: int = 200) -> None:
        self._send_bytes(
            text.encode("utf-8", errors="replace"),
            "text/plain; charset=utf-8",
            status=status,
            cache_control="no-store",
        )

    def _serve_static(self, name: str) -> None:
        route = STATIC_ROUTES.get(name)
        if route is None:
            raise HttpFailure(404, "Not found")
        filename, content_type = route
        path = (STATIC_DIR / filename).resolve()
        if STATIC_DIR.resolve() not in path.parents or not path.is_file():
            raise HttpFailure(404, "Not found")
        try:
            body = path.read_bytes()
        except OSError:
            raise HttpFailure(404, "Not found")
        self._send_bytes(body, content_type, cache_control="no-cache")

    # -- request body helpers ----------------------------------------------

    def _content_length(self, limit: int) -> int:
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise HttpFailure(411, "Content-Length header required")
        try:
            length = int(raw)
        except (TypeError, ValueError):
            raise HttpFailure(400, "Invalid Content-Length header")
        if length < 0:
            raise HttpFailure(400, "Invalid Content-Length header")
        if length > limit:
            raise HttpFailure(
                413,
                f"Request body too large (limit {limit // (1024 * 1024)} MB)",
            )
        return length

    def _read_body(self, limit: int) -> bytes:
        length = self._content_length(limit)
        try:
            body = self.rfile.read(length)
        except OSError:
            raise HttpFailure(400, "Could not read request body")
        if len(body) != length:
            raise HttpFailure(400, "Incomplete request body")
        return body

    def _read_json(self) -> dict:
        body = self._read_body(MAX_JSON)
        if not body:
            return {}
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HttpFailure(400, "Request body must be valid JSON")
        if not isinstance(payload, dict):
            raise HttpFailure(400, "Request body must be a JSON object")
        return payload

    # -- routing ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._guarded(self._handle_get)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._guarded(self._handle_post)

    def _guarded(self, handler) -> None:
        try:
            handler()
        except HttpFailure as exc:
            self._json({"error": exc.message}, status=exc.status)
        except FileNotFoundError as exc:
            message = str(exc).strip() or "File not found"
            self._json({"error": message}, status=404)
        except PermissionError:
            self._json({"error": "Permission denied"}, status=403)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001 - never leak a traceback
            print(
                f"[void] {self.command} {self.path} failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            traceback.print_exc()
            self._json({"error": "Internal server error"}, status=500)

    def _handle_get(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = parsed.query

        if path in STATIC_ROUTES:
            self._serve_static(path)
            return

        if path == "/api/health":
            self._json({"ok": True})
            return

        if path == "/api/status":
            user_id = resolve_user_id(query)
            worker = library_worker(user_id)
            self._json(worker.call(_snapshot, user_id))
            return

        if path == "/api/documents":
            user_id = resolve_user_id(query)
            params = urllib.parse.parse_qs(query)
            subject = (params.get("subject") or [""])[0].strip() or None
            search = (params.get("q") or [""])[0]
            worker = library_worker(user_id)
            self._json({"documents": worker.call(_list_documents, subject, search)})
            return

        if path == "/api/subjects":
            user_id = resolve_user_id(query)
            worker = library_worker(user_id)
            self._json({"subjects": worker.call(_snapshot, user_id)["subjects"]})
            return

        if path.startswith("/api/download/"):
            doc_id = urllib.parse.unquote(path[len("/api/download/") :]).strip()
            if not doc_id:
                raise HttpFailure(400, "Missing document id")
            user_id = resolve_user_id(query)
            worker = library_worker(user_id)
            target, filename = worker.call(_download_target, doc_id)
            self._stream_download(target, filename)
            return

        if path == "/api/config":
            self._handle_get_config()
            return

        if path == "/api/config/local":
            self._handle_post_config_local()
            return

        if path == "/api/config/github":
            self._handle_post_config_github()
            return

        if path == "/api/config/gdrive":
            self._handle_post_config_gdrive()
            return

        if path.startswith("/api/"):
            raise HttpFailure(404, "Unknown endpoint")

        self._plain("Not found", status=404)

    def _handle_post(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = parsed.query

        if path == "/api/sync":
            user_id = resolve_user_id(query)
            worker = library_worker(user_id)
            self._json(worker.call(_sync_and_snapshot, user_id))
            return

        if path == "/api/upload":
            self._handle_upload(query)
            return

        if path.startswith("/api/delete/"):
            doc_id = urllib.parse.unquote(path[len("/api/delete/") :]).strip()
            if not doc_id:
                raise HttpFailure(400, "Missing document id")
            if self.headers.get("Content-Length") in (None, "0"):
                raise HttpFailure(400, "Confirmation required")
            payload = self._read_json()
            if payload.get("confirm") is not True:
                raise HttpFailure(400, "Confirmation required")
            user_id = resolve_user_id(query)
            worker = library_worker(user_id)
            self._json({"errors": worker.call(_delete_document, doc_id)})
            return

        if path == "/api/config/local":
            self._handle_post_config_local()
            return

        if path == "/api/config/github":
            self._handle_post_config_github()
            return

        if path == "/api/config/gdrive":
            self._handle_post_config_gdrive()
            return

        if path.startswith("/api/"):
            raise HttpFailure(404, "Unknown endpoint")

        raise HttpFailure(404, "Not found")

    # -- config endpoints ---------------------------------------------------

    def _handle_get_config(self) -> None:
        try:
            cfg = storage_config.load_config()
        except Exception as exc:
            raise HttpFailure(500, f"Could not read config: {exc}") from exc

        def _bool(val):
            return bool(val)

        def _set(val):
            return bool(val and str(val).strip())

        cloud = cfg.get("cloud", {})
        local = cfg.get("local", {})
        gdrive = cfg.get("gdrive", {})
        github = cfg.get("github", {})

        payload = {
            "cloud": {"enabled": _bool(cloud.get("enabled", True))},
            "local": {
                "enabled": _bool(local.get("enabled", False)),
                "root": str(local.get("root", "") or ""),
            },
            "gdrive": {
                "enabled": _bool(gdrive.get("enabled", False)),
                "client_id": str(gdrive.get("client_id", "") or ""),
                "client_secret_set": _set(gdrive.get("client_secret", "")),
                "refresh_token_set": _set(gdrive.get("refresh_token", "")),
                "folder_id": str(gdrive.get("folder_id", "") or ""),
            },
            "github": {
                "enabled": _bool(github.get("enabled", False)),
                "token_set": _set(github.get("token", "")),
                "repo": str(github.get("repo", "") or ""),
                "branch": str(github.get("branch", "main") or "main"),
                "root": str(github.get("root", "VOID") or "VOID"),
            },
        }
        self._json(payload)

    def _handle_post_config_local(self) -> None:
        payload = self._read_json()
        root = str(payload.get("root", "") or "").strip()
        try:
            if root:
                storage_config.set_local_place(root)
            else:
                storage_config.remove_local_place()
        except Exception as exc:
            raise HttpFailure(500, f"Could not save local config: {exc}") from exc
        self._json({"ok": True})

    def _handle_post_config_github(self) -> None:
        payload = self._read_json()
        token = str(payload.get("token", "") or "").strip()
        repo = str(payload.get("repo", "") or "").strip()
        branch = str(payload.get("branch", "main") or "main").strip()
        root = str(payload.get("root", "VOID") or "VOID").strip()
        try:
            if token:
                storage_config.set_github_place(token, repo, branch, root)
            else:
                storage_config.remove_github_place()
        except Exception as exc:
            raise HttpFailure(500, f"Could not save GitHub config: {exc}") from exc
        self._json({"ok": True})

    def _handle_post_config_gdrive(self) -> None:
        payload = self._read_json()
        client_id = str(payload.get("client_id", "") or "").strip()
        client_secret = str(payload.get("client_secret", "") or "").strip()
        try:
            if client_id:
                cfg = storage_config.load_config()
                cfg["gdrive"]["enabled"] = True
                cfg["gdrive"]["client_id"] = client_id
                if client_secret:
                    cfg["gdrive"]["client_secret"] = client_secret
                storage_config.save_config(cfg)
            else:
                storage_config.remove_gdrive_place()
        except Exception as exc:
            raise HttpFailure(500, f"Could not save GDrive config: {exc}") from exc
        self._json({"ok": True})

    # -- downloads ----------------------------------------------------------

    def _stream_download(self, target: str, filename: str) -> None:
        path = Path(target)
        if not path.is_file():
            raise HttpFailure(404, "File is not available")
        try:
            size = path.stat().st_size
        except OSError:
            raise HttpFailure(404, "File is not available")

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        clean = "".join(
            char for char in filename if char not in '\r\n"\\' and char >= " "
        ).strip()
        clean = os.path.basename(clean)
        if clean in ("", ".", ".."):
            clean = "download"
        ascii_name = clean.encode("ascii", "ignore").decode("ascii") or "download"
        utf8_name = urllib.parse.quote(clean, safe="")
        disposition = (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{utf8_name}"
        )

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", disposition)
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()

        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError as exc:
            print(f"[void] download interrupted: {exc}", file=sys.stderr, flush=True)

    # -- uploads ------------------------------------------------------------

    def _handle_upload(self, query: str) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise HttpFailure(415, "Expected multipart/form-data")

        body = self._read_body(MAX_UPLOAD)
        fields, file_info = _parse_multipart(body, content_type)
        if file_info is None:
            raise HttpFailure(400, "Missing 'file' field")

        original_name, data = file_info
        if not data:
            raise HttpFailure(400, "The uploaded file is empty")

        filename = _safe_filename(original_name)
        subject = _safe_subject(fields.get("subject"))
        doc_type = (fields.get("doc_type") or "").strip()[:120] or None
        summary = (fields.get("summary") or "").strip()[:4000] or None

        user_id = resolve_user_id(query)
        worker = library_worker(user_id)

        temp_dir = tempfile.mkdtemp(prefix="void-upload-")
        temp_path = os.path.join(temp_dir, filename)
        try:
            with open(temp_path, "wb") as handle:
                handle.write(data)
            result = worker.call(_import_file, temp_path, subject, doc_type, summary)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self._json(result)

    # -- logging ------------------------------------------------------------

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        sys.stderr.write(
            f"[void] {self.address_string()} - {format % args}\n"
        )
        sys.stderr.flush()


# ---------------------------------------------------------------------------
# Multipart / filename helpers
# ---------------------------------------------------------------------------


def _parse_multipart(body: bytes, content_type: str):
    raw = (
        b"Content-Type: "
        + content_type.encode("latin-1", errors="replace")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception:
        raise HttpFailure(400, "Could not parse multipart body")

    if not message.is_multipart():
        raise HttpFailure(400, "Could not parse multipart body")

    fields: dict[str, str] = {}
    file_info: tuple[str, bytes] | None = None

    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        if payload is None:
            payload = b""

        if filename is not None:
            if name == "file" and file_info is None:
                file_info = (filename, payload)
            continue

        charset = part.get_content_charset() or "utf-8"
        try:
            fields[name] = payload.decode(charset, errors="replace")
        except LookupError:
            fields[name] = payload.decode("utf-8", errors="replace")

    return fields, file_info


def _safe_filename(name: str) -> str:
    base = os.path.basename(str(name).replace("\\", "/")).strip()
    base = "".join(char for char in base if char >= " " and char != "\x7f")
    if base in ("", ".", ".."):
        base = "upload.bin"
    stem, extension = os.path.splitext(base)
    extension = extension[:20]
    stem = stem[:140] or "upload"
    return stem + extension


def _safe_subject(value) -> str:
    subject = str(value or "").strip()
    subject = "".join(
        char for char in subject if char >= " " and char not in "/\\"
    ).strip()
    subject = subject[:120].strip()
    return subject or "UNSORTED"


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class VoidHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _default_port() -> int:
    raw = os.environ.get("PORT", "8000").strip() or "8000"
    try:
        port = int(raw)
    except ValueError:
        print(f"[void] Ignoring invalid PORT={raw!r}; using 8000", file=sys.stderr)
        return 8000
    if not 0 <= port <= 65535:
        print(f"[void] Ignoring out-of-range PORT={port}; using 8000", file=sys.stderr)
        return 8000
    return port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the local VOID dashboard.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (localhost only by default)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_default_port(),
        help="Port to listen on (or set PORT)",
    )
    args = parser.parse_args(argv)

    host = args.host or "127.0.0.1"
    try:
        server = VoidHTTPServer((host, args.port), VoidHandler)
    except OSError as exc:
        print(
            f"[void] Could not bind {host}:{args.port}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    actual_port = server.server_address[1]
    display_host = host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    url = f"http://{display_host}:{actual_port}"

    print("")
    print(f"  VOID dashboard → {url}")
    print(f"  Serving      → {STATIC_DIR}")
    print("  Stop         → Ctrl+C")
    print("", flush=True)

    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n[void] Shutting down…", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
