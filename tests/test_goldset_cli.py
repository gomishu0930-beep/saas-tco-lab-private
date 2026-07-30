from __future__ import annotations

import json
from pathlib import Path

from saas_preflight.cli import run

from test_goldset import full_fixture
from test_models import NOW


def test_evaluate_gold_set_cli_emits_hash_only_ready_report(
    tmp_path: Path, capsys
) -> None:
    goldset, candidates, _ = full_fixture()
    goldset_path = tmp_path / "goldset.json"
    candidates_path = tmp_path / "candidates.json"
    goldset_path.write_text(goldset.model_dump_json(indent=2), encoding="utf-8")
    candidates_path.write_text(candidates.model_dump_json(indent=2), encoding="utf-8")

    assert run(
        [
            "evaluate-gold-set",
            "--gold-set",
            str(goldset_path),
            "--candidates",
            str(candidates_path),
            "--at",
            NOW.isoformat(),
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ready_for_release"] is True
    assert payload["gold_vendor_count"] == 3
    assert payload["gold_plan_count"] == 18
    assert payload["quarantines"] == []
    serialized = json.dumps(payload)
    assert "https://" not in serialized
    assert "Plan price is" not in serialized


def test_evaluate_gold_set_cli_rejects_unknown_input_without_echoing_it(
    tmp_path: Path, capsys
) -> None:
    goldset, candidates, _ = full_fixture()
    goldset_path = tmp_path / "goldset.json"
    candidates_path = tmp_path / "candidates.json"
    invalid = json.loads(goldset.model_dump_json())
    invalid["private_tracking_url"] = "https://should-not-echo.invalid/secret"
    goldset_path.write_text(json.dumps(invalid), encoding="utf-8")
    candidates_path.write_text(candidates.model_dump_json(), encoding="utf-8")

    assert run(
        [
            "evaluate-gold-set",
            "--gold-set",
            str(goldset_path),
            "--candidates",
            str(candidates_path),
        ]
    ) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "document validation failed" in captured.err
    assert "should-not-echo" not in captured.err
    assert "private_tracking_url" not in captured.err
