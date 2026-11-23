"""Library facade: the only storage API the rest of VOID needs.

It hides providers, the catalog, deduplication, conflict handling and the
offline outbox behind a few verbs: sync, import, open, delete.

Places are symmetric: VOID Cloud, an optional local folder, Google Drive and
GitHub. Any connected place is mirrored automatically.
"""

import mimetypes
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from colorama import Fore, init

from catalog import Catalog
from sources.base import sha256_bytes, sha256_file
from sources.cloud import CloudProvider
from sources.gdrive import GoogleDriveProvider
from sources.github import GitHubProvider
from sources.local import LocalProvider
from storage_config import (
    github_place,
    gdrive_place,
    load_config,
    local_place,
)
from void_paths import CACHE_DIR, DB_PATH, OUTBOX_DIR, ensure_dirs

init(autoreset=True)

TOMBSTONE_DAYS = 30


def _conflict_name(filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    stamp = time.strftime("%Y-%m-%d %H%M%S")
    return f"{stem} (conflict {stamp} {uuid.uuid4().hex[:4]}){ext}"


def _subject_from_rel(relative_path: str) -> str:
    parts = Path(relative_path).parts
    if len(parts) >= 2:
        return parts[0].strip().upper()
    return "UNSORTED"


@dataclass
class _Obs:
    location: dict
    exists: bool
    checksum: str | None = None
    version: str | None = None
    modified: float = 0.0
    size: int = 0
    data: bytes | None = None
    error: str | None = None
    detached: bool = False


class Library:
    def __init__(self, user_id: str):
        ensure_dirs()
        self.user_id = user_id
        self.cfg = load_config()
        self.catalog = Catalog(DB_PATH)
        self.cloud = CloudProvider(user_id)
        self.local = None
        self.gdrive = None
        self.github = None
        self._known = {kind: None for kind in self._kinds()}
        self.reload(prune=False)

    @staticmethod
    def _kinds():
        return ("cloud", "local", "gdrive", "github")

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def reload(self, prune: bool = True) -> None:
        self.cfg = load_config()

        root = local_place()
        self.local = LocalProvider(root) if root else None

        gdrive = gdrive_place()
        self.gdrive = GoogleDriveProvider(gdrive) if gdrive else None

        github = github_place()
        self.github = GitHubProvider(github) if github else None

        if prune:
            for location in self.catalog.all_locations("local", self.user_id):
                if not self._local_inside(location["path"]):
                    self.catalog.delete_location(location["id"])
            self._prune_orphans()

    def _local_inside(self, path: str) -> bool:
        if not self.local:
            return False
        return path == self.local.root or path.startswith(self.local.root + os.sep)

    def _prune_orphans(self) -> None:
        for document in self.catalog.documents(self.user_id):
            if not self.catalog.locations(document["id"]):
                self.catalog.delete_document(document["id"])

    def _provider(self, kind: str):
        return {
            "cloud": self.cloud,
            "local": self.local,
            "gdrive": self.gdrive,
            "github": self.github,
        }.get(kind)

    def _places(self):
        """Connected writable places, in display/priority order."""
        places = []
        for kind in self._kinds():
            provider = self._provider(kind)
            if provider is not None and getattr(provider, "writable", True):
                places.append((kind, provider))
        return places

    def _is_active(self, location: dict) -> bool:
        if self._provider(location["kind"]) is None:
            return False
        if location["kind"] == "local" and not self._local_inside(location["path"]):
            return False
        return True

    def _remember(self, kind: str, path: str) -> None:
        known = self._known.get(kind)
        if isinstance(known, set):
            known.add(path)

    def _conflict_path(self, provider, document: dict) -> str:
        alternative = dict(document)
        alternative["title"] = _conflict_name(document.get("title") or "file")
        return provider.path_for(alternative)

    def _path_for_document(self, kind: str, provider, document: dict) -> str:
        path = provider.path_for(document)
        for _ in range(8):
            owner = self.catalog.document_by_location(kind, path)
            if owner and owner["id"] == document["id"]:
                return path
            if owner and owner["id"] != document["id"]:
                path = self._conflict_path(provider, document)
                continue

            known = self._known.get(kind)
            if known is None:
                try:
                    exists = provider.exists(path)
                except Exception:
                    exists = False
            else:
                exists = path in known
            if exists:
                path = self._conflict_path(provider, document)
                continue
            return path
        return path

    # ------------------------------------------------------------------
    # sync
    # ------------------------------------------------------------------
    def sync(self, quiet: bool = True):
        self._known = {kind: None for kind in self._kinds()}

        if self.cloud is not None:
            try:
                self.cloud.reset_cache()
            except Exception:
                pass
        if self.gdrive is not None:
            try:
                self.gdrive.invalidate()
            except Exception:
                pass

        self.catalog.prune_tombstones(TOMBSTONE_DAYS)
        replayed, _ = self._retry_outbox()

        if self.cloud is not None:
            self._sync_cloud(quiet=quiet)
        if self.local is not None:
            self._sync_local(quiet=quiet)
        for kind in ("gdrive", "github"):
            provider = self._provider(kind)
            if provider is not None:
                self._sync_remote(kind, provider, quiet=quiet)

        report = {
            "upload": 0,
            "download": 0,
            "conflict": 0,
            "pending": 0,
            "missing": 0,
            "error": 0,
        }
        for document in self.catalog.documents(self.user_id):
            self._sync_document(document, report)

        self._prune_orphans()

        if not quiet:
            print(
                f"{Fore.GREEN}~ Sync: ↑{report['upload']} upload · "
                f"↓{report['download']} download · "
                f"⚠{report['conflict']} conflict · "
                f"⏳{report['pending']} pending · "
                f"✗{report['missing']} missing"
            )
            if replayed:
                print(f"{Fore.CYAN}~ Replayed {replayed} queued change(s).")
        return report

    def _sync_cloud(self, quiet: bool = True) -> None:
        if self.cloud is None:
            self._known["cloud"] = None
            return
        try:
            import authentication as athu

            rows = (
                athu.supabase.table("USERS_DATA")
                .select("*")
                .eq("USER_ID", self.user_id)
                .execute()
                .data
            )
        except Exception as exc:
            self._known["cloud"] = None
            if not quiet:
                print(f"{Fore.RED}~ Cloud sync skipped: {exc}")
            return

        known = set()
        indexed = 0
        for row in rows:
            storage_path = row.get("storage_path")
            if not storage_path:
                continue
            known.add(storage_path)

            if self.catalog.is_tombstoned(
                self.user_id, "cloud", storage_path, None, TOMBSTONE_DAYS
            ):
                self._queue_delete("cloud", storage_path, None, None)
                continue

            filename = os.path.basename(storage_path)
            subject = (row.get("subject") or "UNSORTED").strip().upper()
            existing = self.catalog.location_by_path("cloud", storage_path)
            entry = self.cloud.stat(storage_path)

            if existing:
                self.catalog.update_document_metadata(
                    existing["document_id"],
                    title=filename,
                    subject=subject,
                    doc_type=row.get("document_type"),
                    summary=row.get("summary"),
                    mime=mimetypes.guess_type(filename)[0],
                )
                if entry:
                    changed = existing.get("remote_version") != entry.version
                    self.catalog.update_location(
                        existing["id"],
                        size=entry.size,
                        modified_at=entry.modified,
                        remote_version=entry.version,
                        clear_checksum=bool(
                            changed and existing.get("checksum")
                        ),
                    )
                indexed += 1
                continue

            doc_id = self.catalog.upsert_document(
                self.user_id,
                filename,
                subject,
                row.get("document_type"),
                row.get("summary"),
                mimetypes.guess_type(filename)[0],
                entry.size if entry else None,
                None,
            )
            self.catalog.add_location(
                doc_id,
                "cloud",
                storage_path,
                size=entry.size if entry else None,
                modified_at=entry.modified if entry else None,
                remote_version=entry.version if entry else None,
            )
            indexed += 1

        self._known["cloud"] = known
        if not quiet:
            print(f"{Fore.GREEN}~ Cloud: {indexed} file(s) indexed")

    def _sync_local(self, quiet: bool = True) -> None:
        if not self.local:
            self._known["local"] = None
            return

        added = 0
        known = set()
        try:
            entries = list(self.local.list())
        except Exception as exc:
            self._known["local"] = None
            if not quiet:
                print(f"{Fore.RED}~ Local folder skipped: {exc}")
            return

        for entry in entries:
            absolute = os.path.join(self.local.root, entry.path)
            known.add(absolute)
            if self.catalog.is_tombstoned(
                self.user_id, "local", absolute, None, TOMBSTONE_DAYS
            ):
                continue

            existing = self.catalog.location_by_path("local", absolute)
            if (
                existing
                and existing.get("remote_version")
                and existing["remote_version"] == entry.version
            ):
                continue

            checksum = sha256_file(absolute)
            if self.catalog.is_tombstoned(
                self.user_id, "local", absolute, checksum, TOMBSTONE_DAYS
            ):
                continue

            subject = _subject_from_rel(entry.path)
            mime = mimetypes.guess_type(entry.name)[0]

            document = self.catalog.document_by_checksum(self.user_id, checksum)
            if document is None:
                document = self.catalog.document_by_subject_title(
                    self.user_id, subject, entry.name
                )
            if document is None:
                doc_id = self.catalog.upsert_document(
                    self.user_id,
                    entry.name,
                    subject,
                    "LOCAL",
                    entry.name,
                    mime,
                    entry.size,
                    checksum,
                )
            else:
                doc_id = document["id"]
                if not document.get("checksum"):
                    self.catalog.update_document_metadata(doc_id, checksum=checksum)

            if existing and existing["document_id"] != doc_id:
                self.catalog.delete_location(existing["id"])

            self.catalog.add_location(
                doc_id,
                "local",
                absolute,
                checksum,
                entry.size,
                entry.modified,
                remote_version=entry.version,
            )
            added += 1

        self._known["local"] = known
        for location in self.catalog.all_locations("local", self.user_id):
            if not os.path.exists(location["path"]):
                self.catalog.delete_location(location["id"])

        if not quiet:
            print(f"{Fore.GREEN}~ Local folder: {added} new/changed file(s) indexed")

    def _sync_remote(self, kind: str, provider, quiet: bool = True) -> None:
        known = set()
        indexed = 0
        try:
            entries = list(provider.list())
        except Exception as exc:
            self._known[kind] = None
            if not quiet:
                print(f"{Fore.RED}~ {provider.label} skipped: {exc}")
            return

        for entry in entries:
            path = entry.path
            known.add(path)

            if self.catalog.is_tombstoned(
                self.user_id, kind, path, None, TOMBSTONE_DAYS
            ):
                self._queue_delete(kind, path, None, None)
                continue

            existing = self.catalog.location_by_path(kind, path)
            if (
                existing
                and existing.get("remote_version")
                and existing["remote_version"] == entry.version
            ):
                continue
            if existing and existing.get("remote_version") != entry.version:
                # The bytes may have changed; force the next observation to
                # read and hash the file instead of trusting the old checksum.
                self.catalog.update_location(
                    existing["id"], clear_checksum=bool(existing.get("checksum"))
                )

            subject = provider.subject_from_path(path)
            filename = entry.name or os.path.basename(path)
            document = self.catalog.document_by_subject_title(
                self.user_id, subject, filename
            )
            if document is None:
                doc_id = self.catalog.upsert_document(
                    self.user_id,
                    filename,
                    subject,
                    kind.upper(),
                    filename,
                    mimetypes.guess_type(filename)[0],
                    entry.size,
                    None,
                )
            else:
                doc_id = document["id"]

            if existing and existing["document_id"] != doc_id:
                self.catalog.delete_location(existing["id"])

            self.catalog.add_location(
                doc_id,
                kind,
                path,
                size=entry.size,
                modified_at=entry.modified,
                remote_version=entry.version,
            )
            indexed += 1

        self._known[kind] = known
        if not quiet:
            print(f"{Fore.GREEN}~ {provider.label}: {indexed} file(s) indexed")

    def _sync_document(self, document: dict, report: dict) -> None:
        locations = self.catalog.locations(document["id"])
        active = []
        for location in locations:
            if self._is_active(location):
                active.append(location)
            else:
                self.catalog.update_location(location["id"], state="detached")

        if not active:
            return

        # Keep every connected place in sync: add a missing copy for any place
        # that does not have this document yet.
        active_kinds = {location["kind"] for location in active}
        for kind, provider in self._places():
            if kind in active_kinds:
                continue
            path = self._path_for_document(kind, provider, document)
            if self.catalog.is_tombstoned(
                self.user_id, kind, path, None, TOMBSTONE_DAYS
            ):
                continue
            self.catalog.add_location(document["id"], kind, path, state="missing")
            self._remember(kind, path)
            active_kinds.add(kind)

        active = [
            location
            for location in self.catalog.locations(document["id"])
            if self._is_active(location)
        ]
        if not active:
            return

        base = document.get("checksum")

        # First run optimisation: if a cloud copy has no checksum yet but any
        # copy matches the known base, assume the cloud copy matches too. This
        # avoids downloading every existing file just to hash it.
        if base:
            for location in active:
                if (
                    location["kind"] == "cloud"
                    and not location.get("checksum")
                    and not location.get("last_synced_at")
                    and any(
                        other.get("checksum") == base
                        for other in active
                        if other is not location
                    )
                ):
                    entry = self.cloud.stat(location["path"])
                    if entry:
                        self.catalog.update_location(
                            location["id"],
                            checksum=base,
                            size=entry.size,
                            modified_at=entry.modified,
                            remote_version=entry.version,
                        )
            active = [
                location
                for location in self.catalog.locations(document["id"])
                if self._is_active(location)
            ]

        observations = [self._observe(location) for location in active]
        existing = [obs for obs in observations if obs.exists and obs.checksum]

        if not existing:
            for obs in observations:
                self._mark(obs, "detached" if obs.detached else "missing")
            report["missing"] += sum(
                1 for obs in observations if not obs.exists and not obs.detached
            )
            return

        if len(active) < 2:
            winner = existing[0]
            self._mark(winner, "in_sync")
            self.catalog.update_document_metadata(
                document["id"], checksum=winner.checksum
            )
            return

        changed = (
            [obs for obs in existing if obs.checksum != base]
            if base
            else list(existing)
        )
        groups = {}
        for obs in changed:
            groups.setdefault(obs.checksum, []).append(obs)

        if not changed:
            winner = next(
                (obs for obs in existing if obs.checksum == base), existing[0]
            )
            self._propagate(document, winner, observations, report)
        elif len(groups) == 1:
            winner = next(iter(groups.values()))[0]
            self._propagate(document, winner, observations, report)
        else:
            winner = max(existing, key=lambda obs: obs.modified or 0.0)
            self._resolve_conflict(document, winner, observations, report)

    def _observe(self, location: dict) -> _Obs:
        provider = self._provider(location["kind"])
        if provider is None:
            return _Obs(location, exists=False, detached=True)

        try:
            entry = provider.stat(location["path"])
        except Exception as exc:
            return _Obs(location, exists=False, error=str(exc))

        if entry is None:
            return _Obs(location, exists=False)

        if location.get("checksum") and location.get("remote_version") == entry.version:
            return _Obs(
                location,
                exists=True,
                checksum=location["checksum"],
                version=entry.version,
                modified=entry.modified,
                size=entry.size,
            )

        try:
            data = provider.read(location["path"]).read()
        except Exception as exc:
            return _Obs(location, exists=False, error=str(exc))

        return _Obs(
            location,
            exists=True,
            checksum=sha256_bytes(data),
            version=entry.version,
            modified=entry.modified,
            size=entry.size,
            data=data,
        )

    def _read_obs(self, obs: _Obs) -> bytes:
        if obs.data is not None:
            return obs.data
        provider = self._provider(obs.location["kind"])
        if provider is None:
            raise RuntimeError(f"{obs.location['kind']} is not connected")
        return provider.read(obs.location["path"]).read()

    def _write_location(self, location: dict, data: bytes):
        provider = self._provider(location["kind"])
        if provider is None:
            raise RuntimeError(f"{location['kind']} is not connected")
        if location["kind"] == "local" and not self._local_inside(location["path"]):
            raise ValueError("copy is outside the connected folder")
        return provider.write(location["path"], data)

    def _mark_after_write(self, location: dict, checksum: str, size: int) -> None:
        provider = self._provider(location["kind"])
        version = None
        modified = time.time()
        actual_size = size
        try:
            entry = provider.stat(location["path"]) if provider else None
            if entry:
                version = entry.version
                modified = entry.modified
                actual_size = entry.size or size
        except Exception:
            pass
        self.catalog.update_location(
            location["id"],
            checksum=checksum,
            size=actual_size,
            modified_at=modified,
            remote_version=version,
            state="in_sync",
            synced=True,
        )

    def _mark(self, obs: _Obs, state: str) -> None:
        self.catalog.update_location(
            obs.location["id"],
            checksum=obs.checksum,
            size=obs.size,
            modified_at=obs.modified,
            remote_version=obs.version,
            state=state,
            synced=(state == "in_sync"),
        )

    def _propagate(self, document, winner: _Obs, observations, report) -> None:
        base = document.get("checksum")
        winner_data = None

        for obs in observations:
            if obs.detached:
                self._mark(obs, "detached")
                continue
            if obs.error:
                self._mark(obs, "error")
                report["error"] += 1
                continue
            if obs.exists and obs.checksum == winner.checksum:
                self._mark(obs, "in_sync")
                continue
            if (
                obs.exists
                and obs.checksum
                and base
                and obs.checksum != base
                and obs.checksum != winner.checksum
            ):
                # A third version appeared mid-sync; never overwrite it silently.
                self._mark(obs, "conflict")
                report["conflict"] += 1
                continue

            if winner_data is None:
                winner_data = self._read_obs(winner)

            try:
                self._write_location(obs.location, winner_data)
                self._mark_after_write(
                    obs.location, winner.checksum, len(winner_data)
                )
                report[
                    "download" if obs.location["kind"] == "local" else "upload"
                ] += 1
            except Exception as exc:
                self._queue_upload(document, obs.location, winner_data, exc)
                report["pending"] += 1

        self.catalog.update_document_metadata(
            document["id"], checksum=winner.checksum
        )

    def _resolve_conflict(self, document, winner: _Obs, observations, report) -> None:
        base = document.get("checksum")
        winner_data = self._read_obs(winner)

        for obs in observations:
            if obs.detached:
                self._mark(obs, "detached")
                continue
            if obs.error:
                self._mark(obs, "error")
                report["error"] += 1
                continue
            if obs.exists and obs.checksum == winner.checksum:
                self._mark(obs, "in_sync")
                continue

            if obs.exists and obs.checksum and obs.checksum != base:
                try:
                    self._preserve_conflict(document, obs)
                    report["conflict"] += 1
                except Exception:
                    self._mark(obs, "conflict")
                    report["error"] += 1
                    continue

            try:
                self._write_location(obs.location, winner_data)
                self._mark_after_write(
                    obs.location, winner.checksum, len(winner_data)
                )
                report[
                    "download" if obs.location["kind"] == "local" else "upload"
                ] += 1
            except Exception as exc:
                self._queue_upload(document, obs.location, winner_data, exc)
                report["pending"] += 1

        self.catalog.update_document_metadata(
            document["id"], checksum=winner.checksum
        )

    def _preserve_conflict(self, document, obs: _Obs) -> None:
        data = self._read_obs(obs)
        loser_checksum = obs.checksum or sha256_bytes(data)

        already_safe = self.catalog.document_by_checksum(
            self.user_id, loser_checksum
        )
        if already_safe and already_safe["id"] != document["id"]:
            return

        kind = obs.location["kind"]
        provider = self._provider(kind)
        if provider is None:
            raise RuntimeError(f"{kind} is not connected")

        conflict_title = _conflict_name(document["title"])
        alternative = dict(document)
        alternative["title"] = conflict_title
        path = provider.path_for(alternative)
        for _ in range(8):
            occupied = provider.exists(path) or bool(
                self.catalog.document_by_location(kind, path)
            )
            if not occupied:
                break
            conflict_title = _conflict_name(document["title"])
            alternative["title"] = conflict_title
            path = provider.path_for(alternative)

        subject = document["subject"] or "UNSORTED"
        mime = document.get("mime") or mimetypes.guess_type(conflict_title)[0]
        summary = f"Conflict copy of {document['title']}"
        new_doc_id = self.catalog.upsert_document(
            self.user_id,
            conflict_title,
            subject,
            document.get("doc_type"),
            summary,
            mime,
            len(data),
            loser_checksum,
        )

        entry = provider.write(path, data)
        if kind == "cloud":
            self._upsert_cloud_row(
                path, subject, document.get("doc_type"), summary
            )
        self.catalog.add_location(
            new_doc_id,
            kind,
            path,
            loser_checksum,
            entry.size or len(data),
            entry.modified or time.time(),
            remote_version=entry.version,
            state="in_sync",
        )
        self._remember(kind, path)

    # ------------------------------------------------------------------
    # outbox
    # ------------------------------------------------------------------
    def _queue_upload(self, document, location, data: bytes, exc) -> None:
        existing = self.catalog.outbox_entry(
            self.user_id, location["kind"], location["path"], "upload"
        )
        if existing and existing.get("payload_path"):
            try:
                os.remove(existing["payload_path"])
            except OSError:
                pass

        payload = OUTBOX_DIR / uuid.uuid4().hex
        payload.write_bytes(data)
        self.catalog.enqueue_outbox(
            self.user_id,
            document.get("id"),
            location["kind"],
            location["path"],
            "upload",
            checksum=sha256_bytes(data),
            size=len(data),
            payload_path=str(payload),
            last_error=str(exc),
        )
        self.catalog.update_location(location["id"], state="pending")

    def _queue_delete(self, kind, path, checksum=None, document_id=None) -> None:
        self.catalog.enqueue_outbox(
            self.user_id,
            document_id,
            kind,
            path,
            "delete",
            checksum=checksum,
        )

    def _retry_outbox(self):
        entries = self.catalog.pending_outbox(self.user_id)
        replayed = 0
        for entry in entries:
            try:
                kind = entry["kind"]
                path = entry["path"]
                op = entry["op"]
                provider = self._provider(kind)
                if provider is None:
                    raise RuntimeError(f"{kind} is not connected")

                if op == "delete":
                    provider.delete(path)
                    if kind == "cloud":
                        self._delete_cloud_row(path)
                else:
                    payload_path = entry.get("payload_path")
                    if not payload_path or not os.path.exists(payload_path):
                        raise FileNotFoundError("queued payload is missing")
                    data = Path(payload_path).read_bytes()

                    location = self.catalog.location_by_path(kind, path)
                    if location is None:
                        doc_id = entry.get("document_id")
                        if doc_id and self.catalog.document_by_id(doc_id):
                            self.catalog.add_location(
                                doc_id,
                                kind,
                                path,
                                checksum=entry.get("checksum"),
                                size=entry.get("size"),
                                state="pending",
                            )
                            location = self.catalog.location_by_path(kind, path)
                    if location is None:
                        raise RuntimeError("document no longer exists")

                    self._write_location(location, data)
                    self._mark_after_write(
                        location,
                        entry.get("checksum") or sha256_bytes(data),
                        len(data),
                    )
                    self._remember(kind, path)

                self.catalog.remove_outbox(entry["id"])
                if entry.get("payload_path"):
                    try:
                        os.remove(entry["payload_path"])
                    except OSError:
                        pass
                replayed += 1
            except Exception as exc:
                self.catalog.mark_outbox_failed(entry["id"], exc)
        return replayed, []

    def _delete_cloud_row(self, storage_path: str) -> None:
        try:
            import authentication as athu

            (
                athu.supabase.table("USERS_DATA")
                .delete()
                .eq("USER_ID", self.user_id)
                .eq("storage_path", storage_path)
                .execute()
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # import (upload)
    # ------------------------------------------------------------------
    def _import_path(self, kind, provider, document, doc_id, file_path):
        path = provider.path_for(document)
        for _ in range(10):
            current = self.catalog.location_by_path(kind, path)
            if current and current["document_id"] == doc_id:
                return path

            is_source = (
                kind == "local"
                and os.path.realpath(file_path) == os.path.realpath(path)
            )
            if is_source:
                return path

            owner = self.catalog.document_by_location(kind, path)
            try:
                exists = provider.exists(path)
            except Exception:
                exists = False
            if not owner and not exists:
                return path

            document = dict(document)
            document["title"] = _conflict_name(document.get("title") or "file")
            path = provider.path_for(document)
        return path

    def import_file(self, file_path, subject, doc_type=None, summary=None):
        subject = (subject or "UNSORTED").strip().upper()
        filename = os.path.basename(file_path)
        checksum = sha256_file(file_path)
        size = os.path.getsize(file_path)
        mime = mimetypes.guess_type(filename)[0]

        with open(file_path, "rb") as handle:
            data = handle.read()

        doc_id = self.catalog.upsert_document(
            self.user_id, filename, subject, doc_type, summary, mime, size, checksum
        )
        self.catalog.update_document_metadata(doc_id, checksum=checksum)

        document = {
            "id": doc_id,
            "title": filename,
            "subject": subject,
            "doc_type": doc_type,
            "summary": summary,
        }
        results = []
        errors = []

        for kind, provider in self._places():
            path = self._import_path(
                kind, provider, document, doc_id, file_path
            )
            self.catalog.clear_tombstones(self.user_id, kind, path, checksum)
            self.catalog.add_location(
                doc_id, kind, path, checksum, size, state="pending"
            )
            location = self.catalog.location_by_path(kind, path)

            try:
                is_source = (
                    kind == "local"
                    and os.path.realpath(file_path) == os.path.realpath(path)
                )
                if is_source:
                    entry = provider.stat(path)
                    if entry is None:
                        entry = provider.write(path, data)
                else:
                    entry = provider.write(path, data)

                if kind == "cloud":
                    self._upsert_cloud_row(path, subject, doc_type, summary)

                self._mark_after_write(location, checksum, size)
                self._remember(kind, path)
                results.append((kind, path, "ok"))
            except Exception as exc:
                self._queue_upload({"id": doc_id}, location, data, exc)
                results.append((kind, path, "pending"))
                errors.append(f"{provider.label}: {exc}")

        return doc_id, results, errors

    def _upsert_cloud_row(self, storage_path, subject, doc_type, summary) -> None:
        try:
            import authentication as athu

            existing = (
                athu.supabase.table("USERS_DATA")
                .select("*")
                .eq("USER_ID", self.user_id)
                .eq("storage_path", storage_path)
                .execute()
            )
            if existing.data:
                return
            athu.supabase.table("USERS_DATA").insert(
                {
                    "USER_ID": self.user_id,
                    "subject": subject,
                    "document_type": doc_type,
                    "summary": summary,
                    "storage_path": storage_path,
                }
            ).execute()
        except Exception as exc:
            print(f"{Fore.YELLOW}~ Metadata warning: {exc}")

    # ------------------------------------------------------------------
    # read
    # ------------------------------------------------------------------
    def open_document(self, doc_id: str) -> str:
        locations = self.catalog.locations(doc_id)
        if not locations:
            raise FileNotFoundError("No copies of this file are known.")

        for location in locations:
            if location["kind"] == "local" and os.path.exists(location["path"]):
                return location["path"]

        last_error = None
        for location in locations:
            if location["kind"] == "local":
                continue
            provider = self._provider(location["kind"])
            if provider is None:
                continue
            cached = self._cache_path(
                doc_id, location["kind"], location["path"]
            )
            if cached.exists():
                return str(cached)
            try:
                data = provider.read(location["path"]).read()
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(data)
                return str(cached)
            except Exception as exc:
                last_error = exc

        raise FileNotFoundError(f"No reachable copy of this file: {last_error}")

    def _cache_path(self, doc_id: str, kind: str, storage_path: str) -> Path:
        extension = os.path.splitext(storage_path)[1]
        return CACHE_DIR / f"{doc_id}-{kind}{extension}"

    # ------------------------------------------------------------------
    # delete / share
    # ------------------------------------------------------------------
    def delete_document(self, doc_id: str):
        document = self.catalog.document_by_id(doc_id)
        if not document:
            return []
        locations = self.catalog.locations(doc_id)
        errors = []

        for location in locations:
            self.catalog.add_tombstone(
                self.user_id,
                location["kind"],
                location["path"],
                location.get("checksum"),
            )
            provider = self._provider(location["kind"])
            if provider is None:
                self._queue_delete(
                    location["kind"],
                    location["path"],
                    location.get("checksum"),
                    doc_id,
                )
                errors.append(f"{location['kind']}: not connected (queued)")
                continue
            try:
                provider.delete(location["path"])
                if location["kind"] == "cloud":
                    self._delete_cloud_row(location["path"])
            except Exception as exc:
                self._queue_delete(
                    location["kind"],
                    location["path"],
                    location.get("checksum"),
                    doc_id,
                )
                errors.append(f"{location['kind']}: {exc} (queued)")

        self.catalog.delete_document(doc_id)
        for path in list(CACHE_DIR.glob(f"{doc_id}*")):
            try:
                path.unlink()
            except OSError:
                pass
        return errors

    def share_link(self, doc_id: str):
        for location in self.catalog.locations(doc_id):
            provider = self._provider(location["kind"])
            if provider is None:
                continue
            try:
                link = provider.share_link(location["path"])
            except Exception:
                link = None
            if link:
                return link
        return None

    # ------------------------------------------------------------------
    # browse
    # ------------------------------------------------------------------
    def subjects(self):
        return self.catalog.distinct_subjects(self.user_id)

    def list_documents(self, subject=None):
        documents = self.catalog.documents(self.user_id, subject)
        for document in documents:
            locations = self.catalog.locations(document["id"])
            document["doc_id"] = document["id"]
            document["places"] = sorted({location["kind"] for location in locations})
            document["states"] = sorted(
                {location.get("state") or "unknown" for location in locations}
            )
            document["storage_path"] = next(
                (
                    location["path"]
                    for location in locations
                    if location["kind"] == "cloud"
                ),
                None,
            ) or next(
                (
                    location["path"]
                    for location in locations
                    if location["kind"] != "local"
                ),
                None,
            )
        return documents

    def status(self):
        pending = self.catalog.count_outbox(self.user_id)
        places = []

        def add(kind, provider, name):
            if provider is None:
                places.append(
                    {"name": name, "connected": False, "detail": "not set"}
                )
                return
            configured = getattr(provider, "configured", True)
            if not configured:
                places.append(
                    {"name": name, "connected": False, "detail": "needs setup"}
                )
                return
            count = self.catalog.count_locations(kind, self.user_id)
            detail = f"{count} file(s)"
            if kind == "cloud":
                if pending:
                    detail += f", {pending} queued"
            elif kind == "local":
                detail = f"{provider.root} ({count} file(s))"
            elif kind in ("gdrive", "github"):
                detail = f"{provider.describe()} ({count} file(s))"
            places.append(
                {"name": name, "connected": True, "detail": detail}
            )

        add("cloud", self.cloud, "VOID Cloud")
        add("local", self.local, "Local folder")
        add("gdrive", self.gdrive, "Google Drive")
        add("github", self.github, "GitHub")
        return places

    # ------------------------------------------------------------------
    # one-time copy of existing files into the local folder
    # ------------------------------------------------------------------
    def mirror_all_to_local(self, progress=None):
        if not self.local:
            return 0, []

        copied = 0
        errors = []
        for document in self.catalog.documents(self.user_id):
            locations = self.catalog.locations(document["id"])
            if any(location["kind"] == "local" for location in locations):
                continue
            source = next(
                (
                    location
                    for location in locations
                    if location["kind"] != "local"
                ),
                None,
            )
            if source is None:
                continue
            provider = self._provider(source["kind"])
            if provider is None:
                continue
            try:
                data = provider.read(source["path"]).read()
                relative = os.path.join(
                    document["subject"] or "UNSORTED", document["title"]
                )
                absolute = os.path.join(self.local.root, relative)
                self.catalog.clear_tombstones(
                    self.user_id, "local", absolute, document.get("checksum")
                )
                if os.path.exists(absolute):
                    relative = os.path.join(
                        document["subject"] or "UNSORTED",
                        _conflict_name(document["title"]),
                    )
                    absolute = os.path.join(self.local.root, relative)
                os.makedirs(os.path.dirname(absolute), exist_ok=True)
                entry = self.local.write(relative, data)
                checksum = sha256_bytes(data)
                self.catalog.update_document_metadata(
                    document["id"], checksum=checksum
                )
                self.catalog.add_location(
                    document["id"],
                    "local",
                    absolute,
                    checksum,
                    entry.size,
                    entry.modified,
                    remote_version=entry.version,
                    state="in_sync",
                )
                copied += 1
                if progress:
                    progress(copied, document["title"])
            except Exception as exc:
                errors.append(f"{document['title']}: {exc}")
        return copied, errors


_current = None


def for_user(user_id: str) -> Library:
    global _current
    if _current is None or _current.user_id != user_id:
        _current = Library(user_id)
    return _current
