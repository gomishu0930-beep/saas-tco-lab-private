from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from saas_preflight.cli import run
from saas_preflight.preflight import ArtifactExpiries
from saas_preflight.readiness_builder import AffiliateDecisionBatch

from test_preflight import _dossier
from test_models import NOW
from test_readiness_builder import (
    _affiliates,
    _cohort_evidence,
    _demand_evidence,
    _operations_evidence,
    _plans,
)


def test_readiness_cli_emits_json_without_float_coercion(tmp_path: Path, capsys) -> None:
    now = datetime.now(timezone.utc)
    dossier = _dossier().model_copy(
        update={
            "as_of": now - timedelta(minutes=1),
            "provenance": _dossier().provenance.model_copy(
                update={"assembled_at": now - timedelta(minutes=1)}
            ),
            "expires_at": ArtifactExpiries(
                rights=now + timedelta(days=30),
                affiliate=now + timedelta(days=30),
                demand=now + timedelta(days=30),
                operations=now + timedelta(days=30),
                cohort=now + timedelta(days=30),
            ),
        }
    )
    path = tmp_path / "dossier.json"
    path.write_text(dossier.model_dump_json(indent=2), encoding="utf-8")

    assert run(["evaluate-readiness", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "go"
    assert payload["economics"]["confirmed_epc"] == "60"
    assert payload["economics"]["traffic_requirement"]["required_clicks"] == 3334


def test_assemble_readiness_cli_writes_v3_dossier_once(
    tmp_path: Path, capsys
) -> None:
    plan_paths: list[Path] = []
    for index, plan in enumerate(_plans()):
        path = tmp_path / f"plan-{index}.json"
        path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        plan_paths.append(path)

    inputs = {
        "affiliate.json": AffiliateDecisionBatch(decisions=_affiliates()),
        "demand.json": _demand_evidence(),
        "cohort.json": _cohort_evidence(),
        "operations.json": _operations_evidence(),
    }
    for filename, model in inputs.items():
        (tmp_path / filename).write_text(
            model.model_dump_json(indent=2), encoding="utf-8"
        )

    output = tmp_path / "dossier.json"
    args = ["assemble-readiness"]
    for path in plan_paths:
        args.extend(["--plan", str(path)])
    args.extend(
        [
            "--affiliate-decisions",
            str(tmp_path / "affiliate.json"),
            "--demand-evidence",
            str(tmp_path / "demand.json"),
            "--cohort-evidence",
            str(tmp_path / "cohort.json"),
            "--operations-evidence",
            str(tmp_path / "operations.json"),
            "--property-domain",
            "example.test",
            "--output",
            str(output),
            "--at",
            NOW.isoformat(),
        ]
    )

    assert run(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "3.0"
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["rights_approved"] is True

    assert run(args) == 2
    assert "File exists" in capsys.readouterr().err
