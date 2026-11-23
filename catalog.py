"""SQLite catalog: one logical document, many physical copies.

The UI never talks to this directly. `library.Library` is the facade.
"""

import sqlite3
import time
import uuid

from void_paths import ensure_dirs

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    subject TEXT NOT NULL,
    doc_type TEXT,
    summary TEXT,
    mime TEXT,
    size INTEGER,
    checksum TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_checksum
    ON documents(user_id, checksum)
    WHERE checksum IS NOT NULL;

CREATE TABLE IF NOT EXISTS locations (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    checksum TEXT,
    size INTEGER,
    modified_at REAL,
    last_seen REAL NOT NULL,
    remote_version TEXT,
    state TEXT DEFAULT 'unknown',
    last_synced_at REAL,
    UNIQUE(document_id, kind, path)
);

CREATE INDEX IF NOT EXISTS idx_locations_document ON locations(document_id);
CREATE INDEX IF NOT EXISTS idx_locations_kind_path ON locations(kind, path);

CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    document_id TEXT,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    op TEXT NOT NULL,
    checksum TEXT,
    size INTEGER,
    payload_path TEXT,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at REAL NOT NULL,
    UNIQUE(user_id, kind, path, op)
);

CREATE TABLE IF NOT EXISTS tombstones (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    checksum TEXT,
    deleted_at REAL NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tomb_path
    ON tombstones(user_id, kind, path)
    WHERE kind <> '*';

CREATE UNIQUE INDEX IF NOT EXISTS idx_tomb_sum
    ON tombstones(user_id, checksum)
    WHERE kind = '*';
"""


class Catalog:
    def __init__(self, path):
        ensure_dirs()
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        self._add_columns(
            "locations",
            {
                "remote_version": "TEXT",
                "state": "TEXT DEFAULT 'unknown'",
                "last_synced_at": "REAL",
            },
        )

    def _add_columns(self, table, columns) -> None:
        existing = {
            row["name"]
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, ddl in columns.items():
            if name not in existing:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------
    def upsert_document(
        self,
        user_id,
        title,
        subject,
        doc_type=None,
        summary=None,
        mime=None,
        size=None,
        checksum=None,
    ) -> str:
        now = time.time()
        subject = (subject or "UNSORTED").strip().upper()

        row = None
        if checksum:
            row = self._one(
                "SELECT id FROM documents WHERE user_id=? AND checksum=?",
                (user_id, checksum),
            )
        if row:
            self.update_document_metadata(
                row["id"],
                title=title,
                subject=subject,
                doc_type=doc_type,
                summary=summary,
                mime=mime,
                size=size,
            )
            return row["id"]

        doc_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO documents
               (id, user_id, title, subject, doc_type, summary, mime, size,
                checksum, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                doc_id,
                user_id,
                title,
                subject,
                doc_type,
                summary,
                mime,
                size,
                checksum,
                now,
                now,
            ),
        )
        self.conn.commit()
        return doc_id

    def update_document_metadata(
        self,
        document_id,
        title=None,
        subject=None,
        doc_type=None,
        summary=None,
        mime=None,
        size=None,
        checksum=None,
    ) -> None:
        now = time.time()
        self.conn.execute(
            """UPDATE documents SET
                 title   = COALESCE(?, title),
                 subject = COALESCE(?, subject),
                 doc_type= COALESCE(?, doc_type),
                 summary = COALESCE(?, summary),
                 mime    = COALESCE(?, mime),
                 size    = COALESCE(?, size),
                 checksum= COALESCE(?, checksum),
                 updated_at = ?
               WHERE id=?""",
            (title, subject, doc_type, summary, mime, size, checksum, now, document_id),
        )
        self.conn.commit()

    def documents(self, user_id, subject=None):
        if subject:
            rows = self.conn.execute(
                """SELECT * FROM documents
                   WHERE user_id=? AND subject=?
                   ORDER BY title COLLATE NOCASE""",
                (user_id, subject),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT * FROM documents
                   WHERE user_id=?
                   ORDER BY subject, title COLLATE NOCASE""",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def document_by_id(self, document_id):
        row = self._one("SELECT * FROM documents WHERE id=? LIMIT 1", (document_id,))
        return dict(row) if row else None

    def document_by_checksum(self, user_id, checksum):
        if not checksum:
            return None
        row = self._one(
            "SELECT * FROM documents WHERE user_id=? AND checksum=? LIMIT 1",
            (user_id, checksum),
        )
        return dict(row) if row else None

    def document_by_subject_title(self, user_id, subject, title):
        row = self._one(
            """SELECT * FROM documents
               WHERE user_id=? AND subject=? AND title=? LIMIT 1""",
            (user_id, subject, title),
        )
        return dict(row) if row else None

    def document_by_location(self, kind, path):
        row = self._one(
            """SELECT d.* FROM documents d
               JOIN locations l ON l.document_id = d.id
               WHERE l.kind=? AND l.path=? LIMIT 1""",
            (kind, path),
        )
        return dict(row) if row else None

    def distinct_subjects(self, user_id):
        rows = self.conn.execute(
            "SELECT DISTINCT subject FROM documents WHERE user_id=? ORDER BY subject",
            (user_id,),
        ).fetchall()
        return [row["subject"] for row in rows if row["subject"]]

    def delete_document(self, document_id) -> None:
        self.conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # locations (copies)
    # ------------------------------------------------------------------
    def add_location(
        self,
        document_id,
        kind,
        path,
        checksum=None,
        size=None,
        modified_at=None,
        remote_version=None,
        state="unknown",
    ) -> None:
        now = time.time()
        self.conn.execute(
            """INSERT INTO locations
               (id, document_id, kind, path, checksum, size, modified_at,
                last_seen, remote_version, state)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(document_id, kind, path) DO UPDATE SET
                   checksum       = COALESCE(excluded.checksum, locations.checksum),
                   size           = COALESCE(excluded.size, locations.size),
                   modified_at    = COALESCE(excluded.modified_at, locations.modified_at),
                   remote_version = COALESCE(excluded.remote_version, locations.remote_version),
                   state          = excluded.state,
                   last_seen      = excluded.last_seen""",
            (
                str(uuid.uuid4()),
                document_id,
                kind,
                path,
                checksum,
                size,
                modified_at,
                now,
                remote_version,
                state,
            ),
        )
        self.conn.commit()

    def update_location(
        self,
        location_id,
        checksum=None,
        size=None,
        modified_at=None,
        remote_version=None,
        state=None,
        synced=False,
        clear_checksum=False,
    ) -> None:
        fields = []
        params = []
        if clear_checksum:
            fields.append("checksum=NULL")
        for column, value in (
            ("checksum", checksum),
            ("size", size),
            ("modified_at", modified_at),
            ("remote_version", remote_version),
            ("state", state),
        ):
            if value is not None:
                fields.append(f"{column}=?")
                params.append(value)
        if synced:
            fields.append("last_synced_at=?")
            params.append(time.time())
        if not fields:
            return
        params.append(location_id)
        self.conn.execute(
            f"UPDATE locations SET {', '.join(fields)} WHERE id=?", params
        )
        self.conn.commit()

    def locations(self, document_id):
        rows = self.conn.execute(
            "SELECT * FROM locations WHERE document_id=? ORDER BY kind, path",
            (document_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def location_by_path(self, kind, path):
        row = self._one(
            """SELECT * FROM locations
               WHERE kind=? AND path=?
               ORDER BY last_seen DESC LIMIT 1""",
            (kind, path),
        )
        return dict(row) if row else None

    def all_locations(self, kind, user_id):
        rows = self.conn.execute(
            """SELECT l.* FROM locations l
               JOIN documents d ON d.id = l.document_id
               WHERE l.kind=? AND d.user_id=?""",
            (kind, user_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_locations(self, kind, user_id) -> int:
        row = self._one(
            """SELECT COUNT(*) AS n FROM locations l
               JOIN documents d ON d.id = l.document_id
               WHERE l.kind=? AND d.user_id=?""",
            (kind, user_id),
        )
        return row["n"] if row else 0

    def count_state(self, state, user_id) -> int:
        row = self._one(
            """SELECT COUNT(*) AS n FROM locations l
               JOIN documents d ON d.id = l.document_id
               WHERE l.state=? AND d.user_id=?""",
            (state, user_id),
        )
        return row["n"] if row else 0

    def delete_location(self, location_id) -> None:
        self.conn.execute("DELETE FROM locations WHERE id=?", (location_id,))
        self.conn.commit()

    # ------------------------------------------------------------------
    # outbox (writes/deletes waiting for an unreachable place)
    # ------------------------------------------------------------------
    def outbox_entry(self, user_id, kind, path, op):
        row = self._one(
            """SELECT * FROM outbox
               WHERE user_id=? AND kind=? AND path=? AND op=? LIMIT 1""",
            (user_id, kind, path, op),
        )
        return dict(row) if row else None

    def enqueue_outbox(
        self,
        user_id,
        document_id,
        kind,
        path,
        op,
        checksum=None,
        size=None,
        payload_path=None,
        last_error=None,
    ) -> str:
        now = time.time()
        existing = self.outbox_entry(user_id, kind, path, op)
        if existing:
            self.conn.execute(
                """UPDATE outbox SET
                     document_id=?, checksum=?, size=?, payload_path=?,
                     last_error=?, created_at=?
                   WHERE id=?""",
                (
                    document_id,
                    checksum,
                    size,
                    payload_path,
                    last_error,
                    now,
                    existing["id"],
                ),
            )
            self.conn.commit()
            return existing["id"]

        outbox_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO outbox
               (id, user_id, document_id, kind, path, op, checksum, size,
                payload_path, attempts, last_error, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,0,?,?)""",
            (
                outbox_id,
                user_id,
                document_id,
                kind,
                path,
                op,
                checksum,
                size,
                payload_path,
                last_error,
                now,
            ),
        )
        self.conn.commit()
        return outbox_id

    def pending_outbox(self, user_id):
        rows = self.conn.execute(
            "SELECT * FROM outbox WHERE user_id=? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_outbox(self, user_id) -> int:
        row = self._one(
            "SELECT COUNT(*) AS n FROM outbox WHERE user_id=?", (user_id,)
        )
        return row["n"] if row else 0

    def remove_outbox(self, outbox_id) -> None:
        self.conn.execute("DELETE FROM outbox WHERE id=?", (outbox_id,))
        self.conn.commit()

    def mark_outbox_failed(self, outbox_id, error) -> None:
        self.conn.execute(
            "UPDATE outbox SET attempts=attempts+1, last_error=? WHERE id=?",
            (str(error)[:500], outbox_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # tombstones (prevent deleted files from coming back)
    # ------------------------------------------------------------------
    def add_tombstone(self, user_id, kind, path, checksum=None) -> None:
        now = time.time()
        if kind != "*":
            self.conn.execute(
                """INSERT OR REPLACE INTO tombstones
                   (id, user_id, kind, path, checksum, deleted_at)
                   VALUES (?,?,?,?,?,?)""",
                (str(uuid.uuid4()), user_id, kind, path, checksum, now),
            )
        if checksum:
            self.conn.execute(
                """INSERT OR REPLACE INTO tombstones
                   (id, user_id, kind, path, checksum, deleted_at)
                   VALUES (?,?,?,?,?,?)""",
                (str(uuid.uuid4()), user_id, "*", "", checksum, now),
            )
        self.conn.commit()

    def is_tombstoned(self, user_id, kind, path, checksum=None, days=30) -> bool:
        cutoff = time.time() - days * 86400
        row = self._one(
            """SELECT 1 FROM tombstones
               WHERE user_id=? AND deleted_at>?
                 AND ((kind=? AND path=?)
                      OR (kind='*' AND checksum IS NOT NULL AND checksum=?))
               LIMIT 1""",
            (user_id, cutoff, kind, path, checksum),
        )
        return row is not None

    def clear_tombstones(self, user_id, kind, path, checksum=None) -> None:
        self.conn.execute(
            """DELETE FROM tombstones
               WHERE user_id=?
                 AND ((kind=? AND path=?)
                      OR (checksum IS NOT NULL AND checksum=?))""",
            (user_id, kind, path, checksum),
        )
        self.conn.commit()

    def prune_tombstones(self, days=30) -> None:
        cutoff = time.time() - days * 86400
        self.conn.execute("DELETE FROM tombstones WHERE deleted_at < ?", (cutoff,))
        self.conn.commit()
