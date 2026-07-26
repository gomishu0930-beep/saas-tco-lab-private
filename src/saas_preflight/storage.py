"""Append-only SQLite repository for validated pricing snapshots."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import stat
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import fcntl

from .models import PolicyAction, VendorPlan


class DuplicateSnapshotError(ValueError):
    """Raised when an immutable snapshot id is inserted more than once."""


class StorageCorruptionError(RuntimeError):
    """Raised when persisted JSON no longer matches its recorded digest."""


class HistoryRetentionNotApprovedError(PermissionError):
    """Raised when a snapshot lacks field-level history-retention approval."""


class SnapshotRetentionExpiredError(PermissionError):
    """Raised when a retained snapshot has reached its approved delete time."""


class StorageIntegrityError(StorageCorruptionError):
    """Raised when authenticated repository state or schema is inconsistent."""


class StorageAnchorError(StorageIntegrityError):
    """Raised when the external monotonic anchor is unavailable or conflicts."""


class SQLitePlanRepository:
    """A minimal repository that exposes no update or delete operation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        if str(self.path) == ":memory:":
            raise ValueError("a file-backed database is required for permission enforcement")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prepare_secure_file()
        self.initialize()

    def _prepare_secure_file(self) -> None:
        if self.path.is_symlink():
            raise ValueError("database path must not be a symbolic link")
        if self.path.exists():
            if not self.path.is_file():
                raise ValueError("database path must be a regular file")
            self._secure_permissions()
            return

        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, stat.S_IRUSR | stat.S_IWUSR)
        os.close(descriptor)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA temp_store = MEMORY")
            yield connection
        finally:
            connection.close()
            self._secure_permissions()

    def _secure_permissions(self) -> None:
        if self.path.exists():
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS vendor_plan_snapshots (
                    snapshot_id TEXT PRIMARY KEY NOT NULL,
                    vendor_slug TEXT NOT NULL,
                    plan_slug TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
                    payload_json TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                ) STRICT;

                CREATE INDEX IF NOT EXISTS idx_plan_vendor_capture
                    ON vendor_plan_snapshots(vendor_slug, plan_slug, captured_at);

                CREATE TRIGGER IF NOT EXISTS vendor_plan_snapshots_no_update
                BEFORE UPDATE ON vendor_plan_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'vendor_plan_snapshots is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS vendor_plan_snapshots_no_delete
                BEFORE DELETE ON vendor_plan_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'vendor_plan_snapshots is append-only');
                END;
                """
            )
            connection.commit()

    def insert(self, plan: VendorPlan) -> UUID:
        denied_fields = sorted(
            {
                item.field
                for item in plan.field_evidence
                if any(
                    not pointer.source_policy.permits(
                        PolicyAction.RETAIN_HISTORY,
                        at=plan.captured_at,
                    )
                    for pointer in item.pointers
                )
            }
        )
        if denied_fields:
            raise HistoryRetentionNotApprovedError(
                "history retention is not approved for fields: " + ", ".join(denied_fields)
            )

        payload = plan.model_dump_json()
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        inserted_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO vendor_plan_snapshots (
                        snapshot_id, vendor_slug, plan_slug, captured_at,
                        payload_sha256, payload_json, inserted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(plan.snapshot_id),
                        plan.vendor_slug,
                        plan.plan_slug,
                        plan.captured_at.isoformat(),
                        digest,
                        payload,
                        inserted_at,
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise DuplicateSnapshotError(f"snapshot already exists: {plan.snapshot_id}") from exc
        return plan.snapshot_id

    def get(self, snapshot_id: UUID | str) -> VendorPlan:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM vendor_plan_snapshots
                WHERE snapshot_id = ?
                """,
                (str(snapshot_id),),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown snapshot: {snapshot_id}")
        return self._decode(row["payload_json"], row["payload_sha256"])

    def list(
        self,
        *,
        vendor_slug: str | None = None,
        plan_slug: str | None = None,
        limit: int | None = None,
    ) -> tuple[VendorPlan, ...]:
        if limit is not None and (isinstance(limit, bool) or limit < 1):
            raise ValueError("limit must be a positive integer")

        clauses: list[str] = []
        parameters: list[str | int] = []
        if vendor_slug is not None:
            clauses.append("vendor_slug = ?")
            parameters.append(vendor_slug)
        if plan_slug is not None:
            clauses.append("plan_slug = ?")
            parameters.append(plan_slug)

        query = "SELECT payload_json, payload_sha256 FROM vendor_plan_snapshots"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY captured_at DESC, snapshot_id ASC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._decode(row["payload_json"], row["payload_sha256"]) for row in rows)

    @staticmethod
    def _decode(payload: str, expected_digest: str) -> VendorPlan:
        actual_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if actual_digest != expected_digest:
            raise StorageCorruptionError("snapshot payload digest mismatch")
        return VendorPlan.model_validate_json(payload)


_ZERO_SHA256 = "0" * 64
_AUTHENTICATED_SCHEMA = """
CREATE TABLE plan_repository_meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE vendor_plan_snapshots_v2 (
    snapshot_id TEXT PRIMARY KEY NOT NULL,
    vendor_slug TEXT NOT NULL,
    plan_slug TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    retention_delete_after TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    previous_head_sha256 TEXT NOT NULL CHECK(length(previous_head_sha256) = 64),
    row_head_sha256 TEXT NOT NULL UNIQUE CHECK(length(row_head_sha256) = 64)
) STRICT;
CREATE INDEX idx_plan_v2_vendor_capture
    ON vendor_plan_snapshots_v2(vendor_slug, plan_slug, captured_at);
CREATE TRIGGER vendor_plan_snapshots_v2_no_update
BEFORE UPDATE ON vendor_plan_snapshots_v2 BEGIN
    SELECT RAISE(ABORT, 'vendor_plan_snapshots_v2 is append-only');
END;
CREATE TRIGGER vendor_plan_snapshots_v2_no_delete
BEFORE DELETE ON vendor_plan_snapshots_v2 BEGIN
    SELECT RAISE(ABORT, 'vendor_plan_snapshots_v2 is append-only');
END;
"""
_AUTHENTICATED_META_KEYS = {
    "schema_version",
    "store_id_sha256",
    "schema_fingerprint_sha256",
    "revision",
    "snapshot_count",
    "head_sha256",
    "previous_anchor_revision",
    "previous_anchor_sha256",
    "last_trusted_at",
    "cohort_delete_after",
    "state_mac_sha256",
}


class AuthenticatedSQLitePlanRepository:
    """Authenticated, rollback-detecting repository for production candidates.

    Bootstrap owns the authentication key, trusted-clock callback and external
    compare-and-set anchor.  They are never discovered from SQLite, CLI or the
    environment.  A timed-out clock/anchor instance is quarantined; recovery
    requires reopening with working services.  The CAS operation id makes a
    late anchor mutation idempotent.
    """

    _COORDINATION_TIMEOUT_SECONDS = 5.0
    _LOCK_POLL_SECONDS = 0.01

    def __init__(
        self,
        path: str | Path,
        *,
        store_id_sha256: str,
        state_authentication_key: bytes,
        trusted_clock: Callable[[], datetime],
        anchor_read: Callable[[], tuple[int, str] | None],
        anchor_compare_and_set: Callable[
            [int | None, str | None, int, str, str], bool
        ],
    ) -> None:
        self._configure(
            path,
            store_id_sha256=store_id_sha256,
            state_authentication_key=state_authentication_key,
            trusted_clock=trusted_clock,
            anchor_read=anchor_read,
            anchor_compare_and_set=anchor_compare_and_set,
        )
        if not self.path.is_file() or self.path.is_symlink():
            raise StorageIntegrityError("authenticated repository is missing or unsafe")
        self._secure_permissions()
        with self._file_lock(), self._connection() as connection:
            self._assert_integrity(connection, recover_anchor=True)

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        store_id_sha256: str,
        state_authentication_key: bytes,
        trusted_clock: Callable[[], datetime],
        anchor_read: Callable[[], tuple[int, str] | None],
        anchor_compare_and_set: Callable[
            [int | None, str | None, int, str, str], bool
        ],
    ) -> AuthenticatedSQLitePlanRepository:
        repository = cls.__new__(cls)
        repository._configure(
            path,
            store_id_sha256=store_id_sha256,
            state_authentication_key=state_authentication_key,
            trusted_clock=trusted_clock,
            anchor_read=anchor_read,
            anchor_compare_and_set=anchor_compare_and_set,
        )
        repository.path.parent.mkdir(parents=True, exist_ok=True)
        if repository.path.exists():
            raise StorageIntegrityError("authenticated repository already exists")
        repository._prepare_secure_file()
        try:
            with repository._file_lock(), repository._connection() as connection:
                connection.executescript(_AUTHENTICATED_SCHEMA)
                schema_fingerprint = repository._schema_fingerprint(connection)
                meta = {
                    "schema_version": "2.0",
                    "store_id_sha256": store_id_sha256,
                    "schema_fingerprint_sha256": schema_fingerprint,
                    "revision": "0",
                    "snapshot_count": "0",
                    "head_sha256": _ZERO_SHA256,
                    "previous_anchor_revision": "-1",
                    "previous_anchor_sha256": _ZERO_SHA256,
                    "last_trusted_at": "",
                    "cohort_delete_after": "",
                    "state_mac_sha256": _ZERO_SHA256,
                }
                connection.executemany(
                    "INSERT INTO plan_repository_meta(key,value) VALUES (?,?)",
                    tuple(meta.items()),
                )
                mac = repository._state_mac(connection)
                connection.execute(
                    "UPDATE plan_repository_meta SET value=? "
                    "WHERE key='state_mac_sha256'",
                    (mac,),
                )
                connection.commit()
                anchor = repository._anchor_digest(0, _ZERO_SHA256, mac)
            if repository._read_anchor() is not None:
                raise StorageAnchorError("authenticated repository anchor already exists")
            repository._commit_anchor(None, None, 0, anchor)
            if repository._read_anchor() != (0, anchor):
                raise StorageAnchorError("authenticated repository anchor was not durable")
            with repository._file_lock(), repository._connection() as connection:
                repository._assert_integrity(connection, recover_anchor=False)
        except BaseException:
            repository._anchor_quarantined = True
            raise
        return repository

    def _configure(
        self,
        path: str | Path,
        *,
        store_id_sha256: str,
        state_authentication_key: bytes,
        trusted_clock: Callable[[], datetime],
        anchor_read: Callable[[], tuple[int, str] | None],
        anchor_compare_and_set: Callable[
            [int | None, str | None, int, str, str], bool
        ],
    ) -> None:
        selected = Path(path).expanduser()
        if str(selected) == ":memory:":
            raise ValueError("a file-backed authenticated repository is required")
        if (
            len(store_id_sha256) != 64
            or any(character not in "0123456789abcdef" for character in store_id_sha256)
        ):
            raise ValueError("store_id_sha256 must be lowercase SHA-256")
        if not isinstance(state_authentication_key, bytes) or len(state_authentication_key) < 32:
            raise ValueError("state authentication key must contain at least 32 bytes")
        if (
            not callable(trusted_clock)
            or not callable(anchor_read)
            or not callable(anchor_compare_and_set)
        ):
            raise TypeError(
                "trusted clock and external anchor read/compare-and-set are required"
            )
        self.path = selected
        self._lock_path = selected.with_name(f".{selected.name}.lock")
        self._store_id_sha256 = store_id_sha256
        self._state_authentication_key = bytes(state_authentication_key)
        self._trusted_clock = trusted_clock
        self._anchor_read = anchor_read
        self._anchor_compare_and_set = anchor_compare_and_set
        self._anchor_quarantined = False
        self._clock_quarantined = False
        self._last_trusted_at: datetime | None = None
        self._thread_lock = threading.RLock()

    def _prepare_secure_file(self) -> None:
        if self.path.is_symlink():
            raise ValueError("database path must not be a symbolic link")
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, stat.S_IRUSR | stat.S_IWUSR)
        os.close(descriptor)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=self._COORDINATION_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA temp_store = MEMORY")
            yield connection
        finally:
            connection.close()
            self._secure_permissions()

    def _secure_permissions(self) -> None:
        if self.path.exists():
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        if self._lock_path.exists():
            os.chmod(self._lock_path, stat.S_IRUSR | stat.S_IWUSR)

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        with self._thread_lock:
            flags = os.O_CREAT | os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(
                self._lock_path, flags, stat.S_IRUSR | stat.S_IWUSR
            )
            try:
                deadline = time.monotonic() + self._COORDINATION_TIMEOUT_SECONDS
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError as error:
                        if time.monotonic() >= deadline:
                            raise StorageIntegrityError(
                                "authenticated repository lock timed out"
                            ) from error
                        time.sleep(self._LOCK_POLL_SECONDS)
                yield
            finally:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)

    def _anchor_call(self, callback: Callable[..., object], *args: object) -> object:
        if self._anchor_quarantined:
            raise StorageAnchorError("authenticated repository anchor is quarantined")
        output: list[tuple[bool, object]] = []
        ready = threading.Event()

        def invoke() -> None:
            try:
                output.append((True, callback(*args)))
            except BaseException as error:
                output.append((False, error))
            finally:
                ready.set()

        threading.Thread(target=invoke, daemon=True).start()
        if not ready.wait(self._COORDINATION_TIMEOUT_SECONDS):
            self._anchor_quarantined = True
            raise StorageAnchorError("authenticated repository anchor timed out")
        succeeded, value = output[0]
        if not succeeded:
            self._anchor_quarantined = True
            assert isinstance(value, BaseException)
            raise StorageAnchorError("authenticated repository anchor failed") from value
        return value

    def _trusted_now(self) -> datetime:
        if self._clock_quarantined:
            raise StorageIntegrityError(
                "authenticated repository trusted clock is quarantined"
            )
        output: list[tuple[bool, object]] = []
        ready = threading.Event()

        def invoke() -> None:
            try:
                output.append((True, self._trusted_clock()))
            except BaseException as error:
                output.append((False, error))
            finally:
                ready.set()

        threading.Thread(target=invoke, daemon=True).start()
        if not ready.wait(self._COORDINATION_TIMEOUT_SECONDS):
            self._clock_quarantined = True
            raise StorageIntegrityError(
                "authenticated repository trusted clock timed out"
            )
        succeeded, value = output[0]
        if not succeeded:
            self._clock_quarantined = True
            assert isinstance(value, BaseException)
            raise StorageIntegrityError(
                "authenticated repository trusted clock failed"
            ) from value
        try:
            instant = self._require_trusted_time(value)
        except (TypeError, ValueError) as error:
            self._clock_quarantined = True
            raise StorageIntegrityError(
                "authenticated repository trusted clock response is invalid"
            ) from error
        if self._last_trusted_at is not None and instant < self._last_trusted_at:
            self._clock_quarantined = True
            raise StorageIntegrityError(
                "authenticated repository trusted clock moved backwards"
            )
        self._last_trusted_at = instant
        return instant

    def _read_anchor(self) -> tuple[int, str] | None:
        value = self._anchor_call(self._anchor_read)
        if value is None:
            return None
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], int)
            or value[0] < 0
            or not isinstance(value[1], str)
            or len(value[1]) != 64
            or any(character not in "0123456789abcdef" for character in value[1])
        ):
            self._anchor_quarantined = True
            raise StorageAnchorError("authenticated repository anchor response is invalid")
        return value

    def _commit_anchor(
        self,
        expected_revision: int | None,
        expected_digest: str | None,
        new_revision: int,
        new_digest: str,
    ) -> None:
        operation_id = hashlib.sha256(
            json.dumps(
                {
                    "store_id_sha256": self._store_id_sha256,
                    "expected_revision": expected_revision,
                    "expected_digest": expected_digest,
                    "new_revision": new_revision,
                    "new_digest": new_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        accepted = self._anchor_call(
            self._anchor_compare_and_set,
            expected_revision,
            expected_digest,
            new_revision,
            new_digest,
            operation_id,
        )
        if accepted is not True:
            if self._read_anchor() == (new_revision, new_digest):
                return
            self._anchor_quarantined = True
            raise StorageAnchorError("authenticated repository anchor CAS was rejected")

    @staticmethod
    def _schema_descriptor(connection: sqlite3.Connection) -> tuple[tuple[str, str, str, str], ...]:
        return tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            ).fetchall()
        )

    @classmethod
    def _schema_fingerprint(cls, connection: sqlite3.Connection) -> str:
        return hashlib.sha256(
            json.dumps(
                cls._schema_descriptor(connection),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _state_mac(self, connection: sqlite3.Connection) -> str:
        meta = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT key,value FROM plan_repository_meta "
                "WHERE key!='state_mac_sha256' ORDER BY key"
            ).fetchall()
        )
        rows = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT snapshot_id,vendor_slug,plan_slug,captured_at,"
                "retention_delete_after,payload_sha256,payload_json,inserted_at,"
                "previous_head_sha256,row_head_sha256 "
                "FROM vendor_plan_snapshots_v2 ORDER BY rowid"
            ).fetchall()
        )
        payload = json.dumps(
            {"meta": meta, "rows": rows},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hmac.new(
            self._state_authentication_key, payload, hashlib.sha256
        ).hexdigest()

    def _anchor_digest(self, revision: int, head: str, mac: str) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "store_id_sha256": self._store_id_sha256,
                    "revision": revision,
                    "head_sha256": head,
                    "state_mac_sha256": mac,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _row_head(
        previous_head: str,
        *,
        snapshot_id: str,
        payload_sha256: str,
        captured_at: str,
        retention_delete_after: str,
        inserted_at: str,
    ) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "previous_head_sha256": previous_head,
                    "snapshot_id": snapshot_id,
                    "payload_sha256": payload_sha256,
                    "captured_at": captured_at,
                    "retention_delete_after": retention_delete_after,
                    "inserted_at": inserted_at,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _assert_integrity(
        self, connection: sqlite3.Connection, *, recover_anchor: bool
    ) -> dict[str, str]:
        try:
            meta = {
                row["key"]: row["value"]
                for row in connection.execute(
                    "SELECT key,value FROM plan_repository_meta ORDER BY key"
                )
            }
        except sqlite3.DatabaseError as error:
            raise StorageIntegrityError("authenticated repository schema is unavailable") from error
        if (
            set(meta) != _AUTHENTICATED_META_KEYS
            or meta["schema_version"] != "2.0"
            or meta["store_id_sha256"] != self._store_id_sha256
            or meta["schema_fingerprint_sha256"]
            != self._schema_fingerprint(connection)
        ):
            raise StorageIntegrityError("authenticated repository schema or metadata mismatch")
        if meta["last_trusted_at"]:
            try:
                stored_trusted_at = self._require_trusted_time(
                    datetime.fromisoformat(meta["last_trusted_at"])
                )
            except (TypeError, ValueError) as error:
                raise StorageIntegrityError(
                    "authenticated repository trusted-time state is invalid"
                ) from error
            if (
                self._last_trusted_at is None
                or stored_trusted_at > self._last_trusted_at
            ):
                self._last_trusted_at = stored_trusted_at
        if meta["cohort_delete_after"]:
            try:
                self._require_trusted_time(
                    datetime.fromisoformat(meta["cohort_delete_after"])
                )
            except (TypeError, ValueError) as error:
                raise StorageIntegrityError(
                    "authenticated repository retention cohort is invalid"
                ) from error
        previous_head = _ZERO_SHA256
        rows = connection.execute(
            "SELECT * FROM vendor_plan_snapshots_v2 ORDER BY rowid"
        ).fetchall()
        for row in rows:
            if row["previous_head_sha256"] != previous_head:
                raise StorageIntegrityError("authenticated repository history chain mismatch")
            if hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() != row[
                "payload_sha256"
            ]:
                raise StorageIntegrityError("authenticated snapshot payload digest mismatch")
            try:
                item = VendorPlan.model_validate_json(row["payload_json"])
            except ValueError as error:
                raise StorageIntegrityError("authenticated snapshot payload is invalid") from error
            if (
                str(item.snapshot_id) != row["snapshot_id"]
                or item.vendor_slug != row["vendor_slug"]
                or item.plan_slug != row["plan_slug"]
                or item.captured_at.isoformat() != row["captured_at"]
                or row["retention_delete_after"]
                != meta["cohort_delete_after"]
            ):
                raise StorageIntegrityError("authenticated snapshot index mismatch")
            expected_head = self._row_head(
                previous_head,
                snapshot_id=row["snapshot_id"],
                payload_sha256=row["payload_sha256"],
                captured_at=row["captured_at"],
                retention_delete_after=row["retention_delete_after"],
                inserted_at=row["inserted_at"],
            )
            if row["row_head_sha256"] != expected_head:
                raise StorageIntegrityError("authenticated repository row head mismatch")
            previous_head = expected_head
        revision = int(meta["revision"])
        snapshot_count = int(meta["snapshot_count"])
        if (
            revision < snapshot_count
            or snapshot_count != len(rows)
            or meta["head_sha256"] != previous_head
            or (bool(rows) is not bool(meta["cohort_delete_after"]))
        ):
            raise StorageIntegrityError("authenticated repository revision mismatch")
        mac = self._state_mac(connection)
        if not hmac.compare_digest(mac, meta["state_mac_sha256"]):
            raise StorageIntegrityError("authenticated repository state MAC mismatch")
        current_anchor = self._anchor_digest(revision, previous_head, mac)
        observed = self._read_anchor()
        if observed == (revision, current_anchor):
            return meta
        previous_revision = int(meta["previous_anchor_revision"])
        previous_anchor = meta["previous_anchor_sha256"]
        if recover_anchor and observed == (previous_revision, previous_anchor):
            self._commit_anchor(
                previous_revision,
                previous_anchor,
                revision,
                current_anchor,
            )
            if self._read_anchor() == (revision, current_anchor):
                return meta
        self._anchor_quarantined = True
        raise StorageAnchorError("authenticated repository rollback or anchor mismatch")

    @staticmethod
    def _require_trusted_time(value: object) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError("trusted repository time must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("trusted repository time must be timezone-aware")
        return value.astimezone(timezone.utc)

    def _advance_trusted_time(
        self,
        connection: sqlite3.Connection,
        meta: dict[str, str],
        instant: datetime,
    ) -> dict[str, str]:
        stored = (
            None
            if not meta["last_trusted_at"]
            else self._require_trusted_time(
                datetime.fromisoformat(meta["last_trusted_at"])
            )
        )
        if stored is not None and instant < stored:
            self._clock_quarantined = True
            raise StorageIntegrityError(
                "authenticated repository trusted clock moved backwards"
            )
        if stored == instant:
            connection.commit()
            return meta
        revision = int(meta["revision"])
        old_anchor = self._anchor_digest(
            revision, meta["head_sha256"], meta["state_mac_sha256"]
        )
        connection.executemany(
            "UPDATE plan_repository_meta SET value=? WHERE key=?",
            (
                (str(revision + 1), "revision"),
                (str(revision), "previous_anchor_revision"),
                (old_anchor, "previous_anchor_sha256"),
                (instant.isoformat(), "last_trusted_at"),
            ),
        )
        mac = self._state_mac(connection)
        connection.execute(
            "UPDATE plan_repository_meta SET value=? "
            "WHERE key='state_mac_sha256'",
            (mac,),
        )
        connection.commit()
        new_anchor = self._anchor_digest(
            revision + 1, meta["head_sha256"], mac
        )
        self._commit_anchor(revision, old_anchor, revision + 1, new_anchor)
        if self._read_anchor() != (revision + 1, new_anchor):
            self._anchor_quarantined = True
            raise StorageAnchorError(
                "authenticated repository trusted-time anchor was not durable"
            )
        updated = dict(meta)
        updated.update(
            {
                "revision": str(revision + 1),
                "previous_anchor_revision": str(revision),
                "previous_anchor_sha256": old_anchor,
                "last_trusted_at": instant.isoformat(),
                "state_mac_sha256": mac,
            }
        )
        return updated

    @staticmethod
    def _retention_deadline(plan: VendorPlan, trusted_at: datetime) -> datetime:
        deadlines: list[datetime] = []
        denied_fields: set[str] = set()
        for evidence in plan.field_evidence:
            for pointer in evidence.pointers:
                policy = pointer.source_policy
                if (
                    not policy.permits(PolicyAction.RETAIN_HISTORY, at=plan.captured_at)
                    or not policy.permits(PolicyAction.RETAIN_HISTORY, at=trusted_at)
                    or policy.retention_days is None
                ):
                    denied_fields.add(evidence.field)
                    continue
                deadlines.append(
                    min(
                        plan.captured_at
                        + timedelta(days=policy.retention_days),
                        policy.review_due_at,
                    )
                )
        if denied_fields or not deadlines:
            raise HistoryRetentionNotApprovedError(
                "current history retention is not approved for fields: "
                + ", ".join(sorted(denied_fields))
            )
        deadline = min(deadlines).astimezone(timezone.utc)
        if trusted_at >= deadline:
            raise SnapshotRetentionExpiredError(
                "snapshot retention cohort is already expired"
            )
        return deadline

    def insert(self, plan: VendorPlan) -> UUID:
        item = VendorPlan.model_validate(plan.model_dump())
        payload = item.model_dump_json()
        payload_sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self._thread_lock, self._file_lock(), self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                meta = self._assert_integrity(connection, recover_anchor=True)
                inserted_at = self._trusted_now()
                meta = self._advance_trusted_time(
                    connection, meta, inserted_at
                )
                if inserted_at < item.captured_at.astimezone(timezone.utc):
                    raise ValueError("trusted insertion time cannot predate capture")
                delete_after = self._retention_deadline(item, inserted_at)
                if (
                    meta["cohort_delete_after"]
                    and meta["cohort_delete_after"] != delete_after.isoformat()
                ):
                    raise StorageIntegrityError(
                        "snapshot belongs to a different retention cohort"
                    )
                connection.execute("BEGIN IMMEDIATE")
                revision = int(meta["revision"])
                head = self._row_head(
                    meta["head_sha256"],
                    snapshot_id=str(item.snapshot_id),
                    payload_sha256=payload_sha256,
                    captured_at=item.captured_at.isoformat(),
                    retention_delete_after=delete_after.isoformat(),
                    inserted_at=inserted_at.isoformat(),
                )
                connection.execute(
                    "INSERT INTO vendor_plan_snapshots_v2("
                    "snapshot_id,vendor_slug,plan_slug,captured_at,"
                    "retention_delete_after,payload_sha256,payload_json,inserted_at,"
                    "previous_head_sha256,row_head_sha256) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(item.snapshot_id),
                        item.vendor_slug,
                        item.plan_slug,
                        item.captured_at.isoformat(),
                        delete_after.isoformat(),
                        payload_sha256,
                        payload,
                        inserted_at.isoformat(),
                        meta["head_sha256"],
                        head,
                    ),
                )
                old_anchor = self._anchor_digest(
                    revision, meta["head_sha256"], meta["state_mac_sha256"]
                )
                connection.executemany(
                    "UPDATE plan_repository_meta SET value=? WHERE key=?",
                    (
                        (str(revision + 1), "revision"),
                        (str(int(meta["snapshot_count"]) + 1), "snapshot_count"),
                        (head, "head_sha256"),
                        (str(revision), "previous_anchor_revision"),
                        (old_anchor, "previous_anchor_sha256"),
                        (inserted_at.isoformat(), "last_trusted_at"),
                        (delete_after.isoformat(), "cohort_delete_after"),
                    ),
                )
                mac = self._state_mac(connection)
                connection.execute(
                    "UPDATE plan_repository_meta SET value=? "
                    "WHERE key='state_mac_sha256'",
                    (mac,),
                )
                connection.commit()
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise DuplicateSnapshotError(
                    f"snapshot already exists: {item.snapshot_id}"
                ) from error
            except BaseException:
                connection.rollback()
                raise
        new_anchor = self._anchor_digest(revision + 1, head, mac)
        self._commit_anchor(revision, old_anchor, revision + 1, new_anchor)
        if self._read_anchor() != (revision + 1, new_anchor):
            self._anchor_quarantined = True
            raise StorageAnchorError("authenticated repository anchor was not durable")
        return item.snapshot_id

    @staticmethod
    def _decode_active(row: sqlite3.Row, trusted_at: datetime) -> VendorPlan:
        delete_after = datetime.fromisoformat(row["retention_delete_after"])
        if trusted_at >= delete_after:
            raise SnapshotRetentionExpiredError(
                f"snapshot retention expired: {row['snapshot_id']}"
            )
        item = VendorPlan.model_validate_json(row["payload_json"])
        denied_fields = sorted(
            {
                evidence.field
                for evidence in item.field_evidence
                if any(
                    not pointer.source_policy.permits(
                        PolicyAction.RETAIN_HISTORY, at=trusted_at
                    )
                    for pointer in evidence.pointers
                )
            }
        )
        if denied_fields:
            raise HistoryRetentionNotApprovedError(
                "current history retention is not approved for fields: "
                + ", ".join(denied_fields)
            )
        return item

    def get(self, snapshot_id: UUID | str) -> VendorPlan:
        with self._thread_lock, self._file_lock(), self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            meta = self._assert_integrity(connection, recover_anchor=True)
            instant = self._trusted_now()
            self._advance_trusted_time(connection, meta, instant)
            row = connection.execute(
                "SELECT * FROM vendor_plan_snapshots_v2 WHERE snapshot_id=?",
                (str(snapshot_id),),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown snapshot: {snapshot_id}")
        return self._decode_active(row, instant)

    def list(
        self,
        *,
        vendor_slug: str | None = None,
        plan_slug: str | None = None,
        limit: int | None = None,
    ) -> tuple[VendorPlan, ...]:
        if limit is not None and (isinstance(limit, bool) or limit < 1):
            raise ValueError("limit must be a positive integer")
        clauses: list[str] = []
        parameters: list[str | int] = []
        if vendor_slug is not None:
            clauses.append("vendor_slug=?")
            parameters.append(vendor_slug)
        if plan_slug is not None:
            clauses.append("plan_slug=?")
            parameters.append(plan_slug)
        query = "SELECT * FROM vendor_plan_snapshots_v2"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY captured_at DESC,snapshot_id ASC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        with self._thread_lock, self._file_lock(), self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            meta = self._assert_integrity(connection, recover_anchor=True)
            instant = self._trusted_now()
            self._advance_trusted_time(connection, meta, instant)
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._decode_active(row, instant) for row in rows)


__all__ = [
    "AuthenticatedSQLitePlanRepository",
    "DuplicateSnapshotError",
    "HistoryRetentionNotApprovedError",
    "SnapshotRetentionExpiredError",
    "SQLitePlanRepository",
    "StorageAnchorError",
    "StorageCorruptionError",
    "StorageIntegrityError",
]
