from __future__ import annotations

import sqlite3
import stat
from datetime import timedelta
from pathlib import Path
from threading import Event

import pytest

from saas_preflight.storage import (
    AuthenticatedSQLitePlanRepository,
    DuplicateSnapshotError,
    HistoryRetentionNotApprovedError,
    SnapshotRetentionExpiredError,
    SQLitePlanRepository,
    StorageAnchorError,
    StorageCorruptionError,
    StorageIntegrityError,
)

from saas_preflight.models import FieldEvidence, PolicyDecision

from test_models import NOW, make_plan, make_pointer, make_policy


STORE_ID = "7" * 64
STATE_KEY = b"authenticated-plan-repository-state-key"


def _anchor_callbacks():
    state: dict[str, tuple[int, str] | None] = {"value": None}
    operations: dict[str, tuple[int, str]] = {}

    def read() -> tuple[int, str] | None:
        return state["value"]

    def compare_and_set(
        expected_revision: int | None,
        expected_digest: str | None,
        new_revision: int,
        new_digest: str,
        operation_id: str,
    ) -> bool:
        previous = operations.get(operation_id)
        if previous is not None:
            return previous == (new_revision, new_digest)
        expected = (
            None
            if expected_revision is None
            else (expected_revision, expected_digest)
        )
        if state["value"] != expected:
            return False
        state["value"] = (new_revision, new_digest)
        operations[operation_id] = (new_revision, new_digest)
        return True

    return state, read, compare_and_set


def test_repository_insert_get_and_filtered_list(tmp_path: Path) -> None:
    repository = SQLitePlanRepository(tmp_path / "private" / "plans.sqlite3")
    plan = make_plan()

    assert repository.insert(plan) == plan.snapshot_id
    assert repository.get(plan.snapshot_id) == plan
    assert repository.list(vendor_slug="example", plan_slug="basic") == (plan,)
    assert repository.list(vendor_slug="missing") == ()


def test_repository_rejects_snapshot_without_history_permission(tmp_path: Path) -> None:
    repository = SQLitePlanRepository(tmp_path / "plans.sqlite3")
    approved_plan = make_plan()
    unretained_evidence = tuple(
        FieldEvidence(
            field=item.field,
            pointers=(
                make_pointer(
                    field=item.field,
                    source_policy=make_policy(
                        field=item.field,
                        retain_history=PolicyDecision.UNREVIEWED,
                        retention_days=None,
                    ),
                ),
            ),
        )
        for item in approved_plan.field_evidence
    )
    plan = make_plan(field_evidence=unretained_evidence)

    with pytest.raises(HistoryRetentionNotApprovedError, match="history retention"):
        repository.insert(plan)
    assert repository.list() == ()


def test_repository_is_append_only(tmp_path: Path) -> None:
    database = tmp_path / "plans.sqlite3"
    repository = SQLitePlanRepository(database)
    plan = make_plan()
    repository.insert(plan)

    with pytest.raises(DuplicateSnapshotError):
        repository.insert(plan)

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE vendor_plan_snapshots SET plan_slug = 'changed' WHERE snapshot_id = ?",
                (str(plan.snapshot_id),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM vendor_plan_snapshots WHERE snapshot_id = ?",
                (str(plan.snapshot_id),),
            )


def test_database_is_owner_read_write_only(tmp_path: Path) -> None:
    database = tmp_path / "plans.sqlite3"
    SQLitePlanRepository(database)

    assert stat.S_IMODE(database.stat().st_mode) == 0o600


def test_repository_rejects_symbolic_link_database(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "link.sqlite3"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symbolic link"):
        SQLitePlanRepository(link)


def test_schema_has_no_raw_source_column(tmp_path: Path) -> None:
    database = tmp_path / "plans.sqlite3"
    SQLitePlanRepository(database)

    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(vendor_plan_snapshots)")
        }
    assert columns == {
        "snapshot_id",
        "vendor_slug",
        "plan_slug",
        "captured_at",
        "payload_sha256",
        "payload_json",
        "inserted_at",
    }
    assert not any(token in column for column in columns for token in ("raw", "html", "body"))


def test_repository_detects_payload_corruption(tmp_path: Path) -> None:
    database = tmp_path / "plans.sqlite3"
    repository = SQLitePlanRepository(database)
    plan = make_plan()
    repository.insert(plan)

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER vendor_plan_snapshots_no_update")
        connection.execute(
            "UPDATE vendor_plan_snapshots SET payload_json = '{}' WHERE snapshot_id = ?",
            (str(plan.snapshot_id),),
        )
        connection.commit()

    with pytest.raises(StorageCorruptionError, match="digest mismatch"):
        repository.get(plan.snapshot_id)


def test_repository_rejects_missing_id_and_invalid_limit(tmp_path: Path) -> None:
    repository = SQLitePlanRepository(tmp_path / "plans.sqlite3")

    with pytest.raises(KeyError, match="unknown snapshot"):
        repository.get("00000000-0000-0000-0000-000000000000")
    with pytest.raises(ValueError, match="positive integer"):
        repository.list(limit=0)


def test_authenticated_repository_round_trip_and_retention_cohort(
    tmp_path: Path,
) -> None:
    state, read, compare_and_set = _anchor_callbacks()
    database = tmp_path / "authenticated.sqlite3"
    repository = AuthenticatedSQLitePlanRepository.create(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    plan = make_plan()

    assert repository.insert(plan) == plan.snapshot_id
    assert state["value"] is not None and state["value"][0] == 2
    assert repository.get(plan.snapshot_id) == plan
    assert repository.list(vendor_slug="example") == (plan,)

    reopened = AuthenticatedSQLitePlanRepository(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    assert reopened.list() == (plan,)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT retention_delete_after,inserted_at "
            "FROM vendor_plan_snapshots_v2"
        ).fetchone()
    assert row == (
        (NOW + timedelta(days=30)).isoformat(),
        NOW.isoformat(),
    )


def test_authenticated_repository_uses_trusted_insert_time_for_rights(
    tmp_path: Path,
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    repository = AuthenticatedSQLitePlanRepository.create(
        tmp_path / "rights.sqlite3",
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW + timedelta(days=31),
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )

    with pytest.raises(
        HistoryRetentionNotApprovedError, match="current history retention"
    ):
        repository.insert(make_plan())


def test_rejected_insert_still_anchors_time_against_reopen_backdating(
    tmp_path: Path,
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    database = tmp_path / "rejected-time.sqlite3"
    repository = AuthenticatedSQLitePlanRepository.create(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW + timedelta(days=31),
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    with pytest.raises(HistoryRetentionNotApprovedError):
        repository.insert(make_plan())

    reopened = AuthenticatedSQLitePlanRepository(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    with pytest.raises(StorageIntegrityError, match="clock moved backwards"):
        reopened.insert(make_plan())


def test_authenticated_repository_rechecks_rights_at_read_time(
    tmp_path: Path,
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    clock = {"now": NOW}
    repository = AuthenticatedSQLitePlanRepository.create(
        tmp_path / "read-rights.sqlite3",
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: clock["now"],
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    plan = make_plan()
    repository.insert(plan)
    clock["now"] = NOW + timedelta(days=30)

    with pytest.raises(SnapshotRetentionExpiredError, match="retention expired"):
        repository.get(plan.snapshot_id)


def test_authenticated_repository_rejects_backdated_clock(
    tmp_path: Path,
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    clock = {"now": NOW}
    database = tmp_path / "clock-rollback.sqlite3"
    repository = AuthenticatedSQLitePlanRepository.create(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: clock["now"],
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    plan = make_plan()
    repository.insert(plan)
    clock["now"] = NOW + timedelta(days=29)
    assert repository.get(plan.snapshot_id) == plan

    backdated_clock = {"now": NOW + timedelta(days=1)}
    reopened = AuthenticatedSQLitePlanRepository(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: backdated_clock["now"],
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )

    with pytest.raises(StorageIntegrityError, match="clock moved backwards"):
        reopened.list()


def test_authenticated_repository_rejects_expired_retention_cohort(
    tmp_path: Path,
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    repository = AuthenticatedSQLitePlanRepository.create(
        tmp_path / "expired.sqlite3",
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW + timedelta(days=1),
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    original = make_plan()
    evidence = tuple(
        FieldEvidence(
            field=item.field,
            pointers=(
                make_pointer(
                    field=item.field,
                    source_policy=make_policy(
                        field=item.field,
                        retention_days=1,
                        review_due_at=NOW + timedelta(days=400),
                    ),
                ),
            ),
        )
        for item in original.field_evidence
    )
    plan = make_plan(field_evidence=evidence)

    with pytest.raises(SnapshotRetentionExpiredError, match="already expired"):
        repository.insert(plan)


def test_authenticated_repository_rejects_mixed_retention_cohorts(
    tmp_path: Path,
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    repository = AuthenticatedSQLitePlanRepository.create(
        tmp_path / "mixed-cohort.sqlite3",
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    repository.insert(make_plan())
    original = make_plan()
    earlier_evidence = tuple(
        FieldEvidence(
            field=item.field,
            pointers=(
                make_pointer(
                    field=item.field,
                    source_policy=make_policy(
                        field=item.field,
                        review_due_at=NOW + timedelta(days=20),
                    ),
                ),
            ),
        )
        for item in original.field_evidence
    )

    with pytest.raises(StorageIntegrityError, match="different retention cohort"):
        repository.insert(make_plan(field_evidence=earlier_evidence))


def test_authenticated_repository_detects_schema_and_state_tampering(
    tmp_path: Path,
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    database = tmp_path / "tamper.sqlite3"
    repository = AuthenticatedSQLitePlanRepository.create(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    repository.insert(make_plan())
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER vendor_plan_snapshots_v2_no_update")
        connection.execute(
            "UPDATE vendor_plan_snapshots_v2 SET payload_json='{}'"
        )
        connection.commit()

    with pytest.raises(StorageIntegrityError, match="schema or metadata"):
        AuthenticatedSQLitePlanRepository(
            database,
            store_id_sha256=STORE_ID,
            state_authentication_key=STATE_KEY,
            trusted_clock=lambda: NOW,
            anchor_read=read,
            anchor_compare_and_set=compare_and_set,
        )


def test_authenticated_repository_detects_database_rollback(tmp_path: Path) -> None:
    state, read, compare_and_set = _anchor_callbacks()
    database = tmp_path / "rollback.sqlite3"
    repository = AuthenticatedSQLitePlanRepository.create(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    before_insert = database.read_bytes()
    repository.insert(make_plan())
    assert state["value"] is not None and state["value"][0] == 2
    database.write_bytes(before_insert)
    database.chmod(0o600)

    with pytest.raises(StorageAnchorError, match="rollback or anchor mismatch"):
        AuthenticatedSQLitePlanRepository(
            database,
            store_id_sha256=STORE_ID,
            state_authentication_key=STATE_KEY,
            trusted_clock=lambda: NOW,
            anchor_read=read,
            anchor_compare_and_set=compare_and_set,
        )


def test_authenticated_repository_recovers_one_ahead_database(
    tmp_path: Path,
) -> None:
    state, read, compare_and_set = _anchor_callbacks()
    database = tmp_path / "recover.sqlite3"
    repository = AuthenticatedSQLitePlanRepository.create(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    assert repository.list() == ()
    reject = {"value": True}

    def fail_once(*args) -> bool:
        if reject["value"]:
            reject["value"] = False
            return False
        return compare_and_set(*args)

    repository._anchor_compare_and_set = fail_once
    plan = make_plan()
    with pytest.raises(StorageAnchorError, match="CAS was rejected"):
        repository.insert(plan)
    assert state["value"] is not None and state["value"][0] == 1

    reopened = AuthenticatedSQLitePlanRepository(
        database,
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    assert state["value"] is not None and state["value"][0] == 2
    assert reopened.list() == (plan,)


def test_authenticated_repository_anchor_timeout_quarantines_instance(
    tmp_path: Path, monkeypatch
) -> None:
    _state, read, compare_and_set = _anchor_callbacks()
    repository = AuthenticatedSQLitePlanRepository.create(
        tmp_path / "anchor-timeout.sqlite3",
        store_id_sha256=STORE_ID,
        state_authentication_key=STATE_KEY,
        trusted_clock=lambda: NOW,
        anchor_read=read,
        anchor_compare_and_set=compare_and_set,
    )
    release = Event()

    def hung_read():
        release.wait()
        return read()

    repository._anchor_read = hung_read
    monkeypatch.setattr(repository, "_COORDINATION_TIMEOUT_SECONDS", 0.05)
    try:
        with pytest.raises(StorageAnchorError, match="timed out"):
            repository.list()
        with pytest.raises(StorageAnchorError, match="quarantined"):
            repository.list()
    finally:
        release.set()
