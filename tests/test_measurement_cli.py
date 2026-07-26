from __future__ import annotations

import json
from pathlib import Path

import pytest

from saas_preflight.cli import run
from saas_preflight.readiness_builder import (
    CohortEvidence,
    DemandEvidence,
    OperationsEvidence,
)

from test_measurement import _cohort_batch, _demand_batch, _operations_batch


@pytest.mark.parametrize(
    ("command", "batch", "evidence_type", "kind"),
    [
        ("aggregate-demand", _demand_batch(), DemandEvidence, "demand"),
        ("aggregate-cohort", _cohort_batch(), CohortEvidence, "cohort"),
        (
            "aggregate-operations",
            _operations_batch(),
            OperationsEvidence,
            "operations",
        ),
    ],
)
def test_measurement_cli_writes_typed_evidence_once(
    command: str,
    batch,
    evidence_type,
    kind: str,
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / f"{kind}-summary.json"
    output = tmp_path / f"{kind}-evidence.json"
    source.write_text(batch.model_dump_json(indent=2), encoding="utf-8")

    args = [command, str(source), "--output", str(output)]
    assert run(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "aggregated"
    assert payload["type"] == kind
    evidence = evidence_type.model_validate_json(output.read_text(encoding="utf-8"))
    assert evidence.evidence_version.startswith("sha256:")

    assert run(args) == 2
    assert "File exists" in capsys.readouterr().err
