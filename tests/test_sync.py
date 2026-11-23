"""Integration tests for the VOID storage engine (V2.1).

Runs entirely offline: a FakeCloud implements the provider interface, so no
Supabase credentials or network access are needed.

    python3 tests/test_sync.py
"""

import hashlib
import io
import os
import shutil
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp(prefix="voidtest-")
os.environ["VOID_HOME"] = HOME
sys.path.insert(0, ROOT)

# Fake authentication module so importing the engine never touches Supabase.
import types

athu = types.ModuleType("authentication")
athu.UUID = "user-1"
athu.ACCESS_TOKEN = "token"
athu.supabase = None
sys.modules["authentication"] = athu

from sources.base import Entry
import catalog
import library
import storage_config

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


class FakeCloud:
    kind = "cloud"
    label = "VOID Cloud"
    writable = True
    configured = True

    def __init__(self):
        self.files = {}
        self.fail_write = False
        self.fail_delete = False

    def reset_cache(self):
        pass

    def invalidate(self):
        pass

    def describe(self):
        return "fake cloud"

    def path_for(self, document):
        subject = (document.get("subject") or "UNSORTED").strip().upper()
        return f"user-1/{subject}/{document.get('title') or 'file'}"

    def subject_from_path(self, path):
        parts = str(path).split("/")
        return parts[1].strip().upper() if len(parts) >= 3 else "UNSORTED"

    def _version(self, data):
        return f"{len(data)}:{hashlib.sha256(data).hexdigest()[:12]}"

    def _entry(self, path, data):
        return Entry(
            path=path,
            name=os.path.basename(path),
            size=len(data),
            modified=float(len(data)),
            version=self._version(data),
        )

    def list(self):
        for path, data in self.files.items():
            yield self._entry(path, data)

    def stat(self, path):
        if path not in self.files:
            return None
        return self._entry(path, self.files[path])

    def read(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return io.BytesIO(self.files[path])

    def write(self, path, data, message=""):
        if self.fail_write:
            raise ConnectionError("cloud offline")
        if hasattr(data, "read"):
            data = data.read()
        self.files[path] = data
        return self._entry(path, data)

    def delete(self, path):
        if self.fail_delete:
            raise ConnectionError("cloud offline")
        self.files.pop(path, None)

    def exists(self, path):
        return path in self.files

    def share_link(self, path):
        return f"https://fake/{path}"


class FakeRemote:
    """A second/third remote place (Google Drive, GitHub) for integration tests."""

    kind = "remote"
    label = "Remote"
    writable = True
    configured = True

    def __init__(self, kind, label):
        self.kind = kind
        self.label = label
        self.files = {}
        self.fail_write = False
        self.fail_delete = False

    def reset_cache(self):
        pass

    def invalidate(self):
        pass

    def describe(self):
        return self.label

    def test(self):
        pass

    def path_for(self, document):
        subject = (document.get("subject") or "UNSORTED").strip().upper()
        return f"{subject}/{document.get('title') or 'file'}"

    def subject_from_path(self, path):
        parts = [part for part in str(path).replace("\\", "/").split("/") if part]
        return parts[0].strip().upper() if len(parts) >= 2 else "UNSORTED"

    def _entry(self, path, data):
        return Entry(
            path=path,
            name=os.path.basename(path),
            size=len(data),
            modified=float(len(data)),
            version=hashlib.sha256(data).hexdigest(),
        )

    def list(self):
        for path, data in self.files.items():
            yield self._entry(path, data)

    def stat(self, path):
        if path not in self.files:
            return None
        return self._entry(path, self.files[path])

    def read(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return io.BytesIO(self.files[path])

    def write(self, path, data, message=""):
        if self.fail_write:
            raise ConnectionError(f"{self.label} offline")
        if hasattr(data, "read"):
            data = data.read()
        data = bytes(data)
        self.files[path] = data
        return self._entry(path, data)

    def delete(self, path):
        if self.fail_delete:
            raise ConnectionError(f"{self.label} offline")
        self.files.pop(path, None)

    def exists(self, path):
        return path in self.files

    def share_link(self, path):
        return f"https://fake/{self.kind}/{path}"


def fresh_library(local_root=None, gdrive=False, github=False):
    if local_root:
        storage_config.set_local_place(local_root)
    else:
        storage_config.remove_local_place()
    lib = library.Library("user-1")
    lib.cloud = FakeCloud()
    lib._sync_cloud = lambda quiet=True: None
    lib._upsert_cloud_row = lambda *a, **k: None
    lib._delete_cloud_row = lambda *a, **k: None
    lib.gdrive = FakeRemote("gdrive", "Google Drive") if gdrive else None
    lib.github = FakeRemote("github", "GitHub") if github else None
    return lib


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def test_import_pushes_everywhere():
    print("\n[1] import_file stores in cloud + local")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    src = os.path.join(HOME, "notes.pdf")
    write(src, b"hello world")

    doc_id, results, errors = lib.import_file(src, "MATH", "NOTES", "sum")
    check("no errors", errors == [], errors)
    check("two results", len(results) == 2, results)
    check("all ok", all(r[2] == "ok" for r in results), results)
    check("cloud has copy", len(lib.cloud.files) == 1, lib.cloud.files)
    check("local has copy", os.path.exists(os.path.join(local, "MATH", "notes.pdf")))
    locations = lib.catalog.locations(doc_id)
    check("two catalog copies", len(locations) == 2, locations)
    check(
        "all in_sync",
        all(location["state"] == "in_sync" for location in locations),
        [(location["kind"], location["state"]) for location in locations],
    )


def test_cloud_pull():
    print("\n[2] cloud-only document is pulled into the local folder")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    data = b"cloud only content"
    path = "user-1/BIO/bio.txt"
    lib.cloud.files[path] = data

    doc_id = lib.catalog.upsert_document(
        "user-1", "bio.txt", "BIO", "NOTES", "cloud", "text/plain", len(data), None
    )
    lib.catalog.add_location(doc_id, "cloud", path, size=len(data))

    report = lib.sync(quiet=True)
    check("downloaded 1", report["download"] == 1, report)
    check("local file exists", os.path.exists(os.path.join(local, "BIO", "bio.txt")))
    with open(os.path.join(local, "BIO", "bio.txt"), "rb") as handle:
        check("content matches", handle.read() == data)
    check(
        "doc checksum set",
        lib.catalog.document_by_id(doc_id)["checksum"]
        == hashlib.sha256(data).hexdigest(),
    )


def test_local_push():
    print("\n[3] local-only document is uploaded when upload_existing is on")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    config = storage_config.load_config()
    config["local"]["upload_existing"] = True
    storage_config.save_config(config)
    lib.reload()

    write(os.path.join(local, "PHYS", "lab.txt"), b"lab notes")
    report = lib.sync(quiet=True)
    check("uploaded 1", report["upload"] == 1, report)
    check("cloud file exists", "user-1/PHYS/lab.txt" in lib.cloud.files, lib.cloud.files)
    check("cloud content", lib.cloud.files.get("user-1/PHYS/lab.txt") == b"lab notes")


def test_conflict_keep_both():
    print("\n[4] conflicting edits keep both copies")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    src = os.path.join(HOME, "shared.txt")
    write(src, b"base version")
    doc_id, _, errors = lib.import_file(src, "CS", "NOTES", "base")
    check("import ok", errors == [], errors)

    cloud_path = next(iter(lib.cloud.files))
    local_path = os.path.join(local, "CS", "shared.txt")

    write(local_path, b"local edit version")
    lib.cloud.files[cloud_path] = b"cloud edit version"

    report = lib.sync(quiet=True)
    check("conflict reported", report["conflict"] >= 1, report)

    docs = lib.catalog.documents("user-1")
    titles = [document["title"] for document in docs]
    check("conflict copy created", any("(conflict" in title for title in titles), titles)

    all_data = []
    for document in docs:
        for location in lib.catalog.locations(document["id"]):
            provider = lib.local if location["kind"] == "local" else lib.cloud
            try:
                all_data.append(provider.read(location["path"]).read())
            except Exception:
                pass
    check(
        "both edits preserved",
        b"local edit version" in all_data and b"cloud edit version" in all_data,
        all_data,
    )
    check("original doc still has 2 copies", len(lib.catalog.locations(doc_id)) == 2)


def test_outbox_retry():
    print("\n[5] unreachable cloud write is queued and retried")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    lib.cloud.fail_write = True

    src = os.path.join(HOME, "offline.txt")
    write(src, b"queued payload")
    _, results, _ = lib.import_file(src, "ENG", "NOTES", "offline")
    statuses = {result[0]: result[2] for result in results}
    check("cloud pending", statuses.get("cloud") == "pending", results)
    check("local ok", statuses.get("local") == "ok", results)
    check(
        "outbox has 1",
        lib.catalog.count_outbox("user-1") == 1,
        lib.catalog.pending_outbox("user-1"),
    )

    lib.cloud.fail_write = False
    lib.sync(quiet=True)
    check(
        "outbox drained",
        lib.catalog.count_outbox("user-1") == 0,
        lib.catalog.pending_outbox("user-1"),
    )
    check("cloud now has file", any("offline.txt" in p for p in lib.cloud.files))


def test_tombstone_suppresses_return():
    print("\n[6] deleted file does not come back from the folder")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    src = os.path.join(HOME, "gone.txt")
    write(src, b"delete me")
    doc_id, _, _ = lib.import_file(src, "HIST", "NOTES", "gone")
    local_path = os.path.join(local, "HIST", "gone.txt")

    lib.delete_document(doc_id)
    check("local file removed", not os.path.exists(local_path))
    check("cloud file removed", not any("gone.txt" in p for p in lib.cloud.files))

    write(local_path, b"delete me")
    lib.sync(quiet=True)
    check(
        "tombstone blocks re-index",
        not any(
            document["title"] == "gone.txt"
            for document in lib.catalog.documents("user-1")
        ),
        [document["title"] for document in lib.catalog.documents("user-1")],
    )


def test_delete_propagation_and_outbox():
    print("\n[7] delete propagates; unreachable delete is queued")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    src = os.path.join(HOME, "both.txt")
    write(src, b"two copies")
    doc_id, _, _ = lib.import_file(src, "ART", "NOTES", "both")
    check("cloud copy exists", any("both.txt" in p for p in lib.cloud.files))

    lib.cloud.fail_delete = True
    lib.delete_document(doc_id)
    check(
        "delete queued",
        lib.catalog.count_outbox("user-1") == 1,
        lib.catalog.pending_outbox("user-1"),
    )
    check("local removed", not os.path.exists(os.path.join(local, "ART", "both.txt")))
    check("cloud still there (offline)", any("both.txt" in p for p in lib.cloud.files))

    lib.cloud.fail_delete = False
    lib.sync(quiet=True)
    check(
        "queued delete drained",
        lib.catalog.count_outbox("user-1") == 0,
        lib.catalog.pending_outbox("user-1"),
    )
    check("cloud copy gone", not any("both.txt" in p for p in lib.cloud.files))


def test_catalog_migration():
    print("\n[8] old catalog schema migrates in place")
    path = os.path.join(HOME, "old.db")
    import sqlite3

    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE documents (id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            title TEXT NOT NULL, subject TEXT NOT NULL, doc_type TEXT,
            summary TEXT, mime TEXT, size INTEGER, checksum TEXT,
            created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE TABLE locations (id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
            kind TEXT NOT NULL, path TEXT NOT NULL, checksum TEXT, size INTEGER,
            modified_at REAL, last_seen REAL NOT NULL,
            UNIQUE(document_id, kind, path));
        """
    )
    conn.commit()
    conn.close()

    cat = catalog.Catalog(path)
    columns = {row["name"] for row in cat.conn.execute("PRAGMA table_info(locations)")}
    check("remote_version added", "remote_version" in columns, columns)
    check("state added", "state" in columns, columns)
    check("last_synced_at added", "last_synced_at" in columns, columns)
    check(
        "outbox table exists",
        cat.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='outbox'"
        ).fetchone()
        is not None,
    )
    check(
        "tombstones table exists",
        cat.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tombstones'"
        ).fetchone()
        is not None,
    )
    cat.close()


def test_import_writes_to_all_places():
    print("\n[9] import_file writes to cloud + local + Drive + GitHub")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local, gdrive=True, github=True)
    src = os.path.join(HOME, "all.txt")
    write(src, b"all places")

    doc_id, results, errors = lib.import_file(src, "BIO", "NOTES", "all")
    check("no errors", errors == [], errors)
    check("four results", len(results) == 4, results)
    check("all ok", all(r[2] == "ok" for r in results), results)
    check("cloud copy", "user-1/BIO/all.txt" in lib.cloud.files)
    check("gdrive copy", "BIO/all.txt" in lib.gdrive.files, lib.gdrive.files)
    check("github copy", "BIO/all.txt" in lib.github.files, lib.github.files)
    check("local copy", os.path.exists(os.path.join(local, "BIO", "all.txt")))
    check("four catalog copies", len(lib.catalog.locations(doc_id)) == 4)


def test_new_places_auto_mirror():
    print("\n[10] connecting a new place auto-mirrors existing documents")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local)
    src = os.path.join(HOME, "mirror.txt")
    write(src, b"mirror me")
    doc_id, _, _ = lib.import_file(src, "CS", "NOTES", "mirror")
    check("starts with two copies", len(lib.catalog.locations(doc_id)) == 2)

    lib.gdrive = FakeRemote("gdrive", "Google Drive")
    lib.github = FakeRemote("github", "GitHub")
    report = lib.sync(quiet=True)
    check("uploaded to both", report["upload"] >= 2, report)
    check("gdrive mirrored", "CS/mirror.txt" in lib.gdrive.files, lib.gdrive.files)
    check("github mirrored", "CS/mirror.txt" in lib.github.files, lib.github.files)
    check("four catalog copies", len(lib.catalog.locations(doc_id)) == 4)


def test_delete_every_place():
    print("\n[11] delete removes copies from every place")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local, gdrive=True, github=True)
    src = os.path.join(HOME, "everywhere.txt")
    write(src, b"everywhere")
    doc_id, _, _ = lib.import_file(src, "ART", "NOTES", "everywhere")

    errors = lib.delete_document(doc_id)
    check("no delete errors", errors == [], errors)
    check("cloud empty", lib.cloud.files == {}, lib.cloud.files)
    check("gdrive empty", lib.gdrive.files == {}, lib.gdrive.files)
    check("github empty", lib.github.files == {}, lib.github.files)
    check(
        "local gone",
        not os.path.exists(os.path.join(local, "ART", "everywhere.txt")),
    )
    check("catalog gone", lib.catalog.document_by_id(doc_id) is None)


def test_remote_outbox_retry():
    print("\n[12] a remote place that is offline is queued and retried")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local, gdrive=True)
    lib.gdrive.fail_write = True
    src = os.path.join(HOME, "remote-offline.txt")
    write(src, b"remote queue")
    _, results, _ = lib.import_file(src, "ENG", "NOTES", "remote")
    statuses = {result[0]: result[2] for result in results}
    check("gdrive pending", statuses.get("gdrive") == "pending", results)
    check("outbox has one", lib.catalog.count_outbox("user-1") == 1)
    check("gdrive empty", lib.gdrive.files == {}, lib.gdrive.files)

    lib.gdrive.fail_write = False
    lib.sync(quiet=True)
    check("outbox drained", lib.catalog.count_outbox("user-1") == 0)
    check(
        "gdrive has file",
        "ENG/remote-offline.txt" in lib.gdrive.files,
        lib.gdrive.files,
    )


def test_conflict_on_remote():
    print("\n[13] a conflicting edit in Drive keeps both versions")
    local = tempfile.mkdtemp(prefix="loc-")
    lib = fresh_library(local, gdrive=True)
    src = os.path.join(HOME, "drive-conflict.txt")
    write(src, b"base")
    lib.import_file(src, "PHY", "NOTES", "base")

    write(os.path.join(local, "PHY", "drive-conflict.txt"), b"local version")
    lib.gdrive.files["PHY/drive-conflict.txt"] = b"drive version"

    report = lib.sync(quiet=True)
    check("conflict reported", report["conflict"] >= 1, report)
    titles = [document["title"] for document in lib.catalog.documents("user-1")]
    check("conflict copy", any("(conflict" in title for title in titles), titles)
    check(
        "drive has conflict copy",
        any("(conflict" in path for path in lib.gdrive.files),
        lib.gdrive.files,
    )

    all_data = []
    for document in lib.catalog.documents("user-1"):
        for location in lib.catalog.locations(document["id"]):
            provider = lib.local if location["kind"] == "local" else lib._provider(
                location["kind"]
            )
            try:
                all_data.append(provider.read(location["path"]).read())
            except Exception:
                pass
    check(
        "both versions survive",
        b"local version" in all_data and b"drive version" in all_data,
        all_data,
    )


def test_provider_path_mapping():
    print("\n[14] provider path mapping and subject extraction")
    from sources.cloud import CloudProvider
    from sources.gdrive import GoogleDriveProvider
    from sources.github import GitHubProvider
    from sources.local import LocalProvider

    document = {"subject": "math", "title": "notes.pdf"}
    github = GitHubProvider({"token": "t", "repo": "o/r", "root": "VOID"})
    check("github path", github.path_for(document) == "MATH/notes.pdf")
    check(
        "github remote",
        github._remote("MATH/notes.pdf") == "VOID/MATH/notes.pdf",
    )
    check(
        "github relative",
        github._relative("VOID/MATH/notes.pdf") == "MATH/notes.pdf",
    )
    check("github subject", github.subject_from_path("MATH/notes.pdf") == "MATH")

    drive = GoogleDriveProvider({"client_id": "c", "refresh_token": "r"})
    check("drive path", drive.path_for(document) == "MATH/notes.pdf")
    check("drive subject", drive.subject_from_path("MATH/notes.pdf") == "MATH")

    cloud = CloudProvider("user-1")
    check("cloud path", cloud.path_for(document) == "user-1/MATH/notes.pdf")
    check(
        "cloud subject",
        cloud.subject_from_path("user-1/MATH/notes.pdf") == "MATH",
    )

    local_root = tempfile.mkdtemp(prefix="path-")
    local = LocalProvider(local_root)
    local_path = local.path_for(document)
    check("local path is absolute", os.path.isabs(local_path), local_path)
    check("local subject", local.subject_from_path(local_path) == "MATH")


def test_place_config_roundtrip():
    print("\n[15] provider config round-trips")
    storage_config.set_github_place("tok", "owner/repo", "dev", "VOID")
    github = storage_config.github_place()
    check("github enabled", bool(github) and github["token"] == "tok")
    check("github branch", github and github["branch"] == "dev")
    storage_config.remove_github_place()
    check("github removed", storage_config.github_place() is None)

    storage_config.set_gdrive_place("cid", "sec", "refresh", "folder")
    drive = storage_config.gdrive_place()
    check("gdrive enabled", bool(drive) and drive["refresh_token"] == "refresh")
    storage_config.remove_gdrive_place()
    check("gdrive removed", storage_config.gdrive_place() is None)


def main():
    tests = [
        test_import_pushes_everywhere,
        test_cloud_pull,
        test_local_push,
        test_conflict_keep_both,
        test_outbox_retry,
        test_tombstone_suppresses_return,
        test_delete_propagation_and_outbox,
        test_catalog_migration,
        test_import_writes_to_all_places,
        test_new_places_auto_mirror,
        test_delete_every_place,
        test_remote_outbox_retry,
        test_conflict_on_remote,
        test_provider_path_mapping,
        test_place_config_roundtrip,
    ]
    for test in tests:
        try:
            test()
        except Exception:
            global FAIL
            FAIL += 1
            print(f"  ERROR in {test.__name__}")
            traceback.print_exc()

    print(f"\n{'=' * 50}\n{PASS} passed, {FAIL} failed")
    shutil.rmtree(HOME, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
