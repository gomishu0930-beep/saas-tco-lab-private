from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from saas_preflight.cli import run
from saas_preflight.models import BillingPeriod, FieldEvidence, PolicyAction, PolicyDecision
from saas_preflight.preview import FitStatus, PreviewPage, PreviewPlan

from test_models import make_plan


def _write_plan(path: Path, *, derive: PolicyDecision = PolicyDecision.APPROVED) -> None:
    now = datetime.now(timezone.utc)
    plan = make_plan()
    evidence_items: list[FieldEvidence] = []
    for evidence in plan.field_evidence:
        pointers = []
        for pointer in evidence.pointers:
            policy = pointer.source_policy.model_copy(
                update={
                    "derive": derive,
                    "reviewed_at": min(
                        now - timedelta(days=1),
                        pointer.retrieved_at - timedelta(days=1),
                    ),
                    "review_due_at": now + timedelta(days=30),
                }
            )
            if derive is not PolicyDecision.APPROVED:
                assert not policy.permits(PolicyAction.DERIVE, at=now)
            pointers.append(pointer.model_copy(update={"source_policy": policy}))
        evidence_items.append(evidence.model_copy(update={"pointers": tuple(pointers)}))
    plan = plan.model_copy(update={"field_evidence": tuple(evidence_items)})
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")


def test_validate_plan_reports_rights_status(tmp_path: Path, capsys) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)

    assert run(["validate-plan", str(plan_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["derivable_now"] is True
    assert payload["publishable_now"] is True
    assert "base_price" in payload["material_fields"]


def test_init_store_and_list_emit_only_metadata(tmp_path: Path, capsys) -> None:
    plan_path = tmp_path / "plan.json"
    database = tmp_path / "plans.sqlite"
    _write_plan(plan_path)

    assert run(["init-db", "--db", str(database)]) == 0
    capsys.readouterr()
    assert run(["store-plan", str(plan_path), "--db", str(database)]) == 0
    stored = json.loads(capsys.readouterr().out)
    assert stored["status"] == "stored"
    assert "earliest_history_delete_after" in stored
    assert run(["list-plans", "--db", str(database)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1
    assert set(listed[0]) == {
        "captured_at",
        "plan_slug",
        "schema_version",
        "snapshot_id",
        "vendor_slug",
    }


def test_calculate_tco_returns_minor_units(tmp_path: Path, capsys) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)

    assert (
        run(
            [
                "calculate-tco",
                str(plan_path),
                "--seats",
                "1",
                "--months",
                "12",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["currency"] == "JPY"
    assert payload["listed_minor"] == 12_000
    assert payload["added_tax_minor"] == 1_200
    assert payload["total_minor"] == 13_200


def test_calculate_tco_fails_closed_without_current_derive_rights(
    tmp_path: Path, capsys
) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path, derive=PolicyDecision.PROHIBITED)

    assert run(["calculate-tco", str(plan_path), "--seats", "1"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "derivation is not currently approved" in captured.err
    assert "base_price" in captured.err


def test_invalid_plan_returns_safe_error(tmp_path: Path, capsys) -> None:
    plan_path = tmp_path / "invalid.json"
    plan_path.write_text('{"unexpected": true}', encoding="utf-8")

    assert run(["validate-plan", str(plan_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert "unexpected" not in captured.err
    assert "true" not in captured.err


def test_render_preview_writes_new_noindex_file_only(tmp_path: Path, capsys) -> None:
    now = datetime.now(timezone.utc)
    page = PreviewPage(
        title="Synthetic comparison",
        methodology="Precomputed canonical TCO fixture.",
        rendered_at=now,
        plans=(
            PreviewPlan(
                vendor_slug="sample",
                vendor_name="Sample",
                plan_slug="basic",
                plan_name="Basic",
                scenario_name="one seat",
                region="JP",
                tax_note="synthetic tax included",
                currency="JPY",
                billing_period=BillingPeriod.MONTHLY,
                commitment_months=12,
                minor_unit_digits=0,
                total_minor=12000,
                fit_status=FitStatus.FIT,
                fit_reason="Synthetic scenario requirements are met.",
                evidence_url="https://example.com/pricing",
                evidence_retrieved_at=now,
                data_expires_at=now + timedelta(days=7),
                rights_expires_at=now + timedelta(days=30),
            ),
        ),
    )
    page_path = tmp_path / "page.json"
    output = tmp_path / "index.html"
    page_path.write_text(page.model_dump_json(), encoding="utf-8")

    assert (
        run(["render-preview", str(page_path), "--output", str(output)]) == 0
    )
    rendered = output.read_text(encoding="utf-8")
    assert "noindex,nofollow,noarchive" in rendered
    capsys.readouterr()

    assert (
        run(["render-preview", str(page_path), "--output", str(output)]) == 2
    )
    assert "File exists" in capsys.readouterr().err
