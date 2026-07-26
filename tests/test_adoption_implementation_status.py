from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "CURRENT_ADOPTION_REGISTRY.json"
STATUS = ROOT / "docs" / "CURRENT_ADOPTION_IMPLEMENTATION_STATUS.json"


def test_every_registry_item_has_completed_codex_work_and_evidence() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    registry_ids = [item["id"] for item in registry["items"]]
    status_ids = [item["id"] for item in status["items"]]

    assert len(registry_ids) == 37
    assert len(registry_ids) == len(set(registry_ids))
    assert status_ids == registry_ids
    assert set(status["allowed_states"]) == {
        "implemented_verified",
        "prepared_waiting_human",
        "implemented_waiting_trigger",
        "deferred_gate_prepared",
    }

    for item in status["items"]:
        assert item["state"] in status["allowed_states"], item["id"]
        assert item["codex_work_complete"] is True, item["id"]
        assert item["evidence"], item["id"]
        for evidence in item["evidence"]:
            path = Path(evidence)
            if path.is_absolute():
                # Personal Codex skills are validated separately and are not CI inputs.
                continue
            assert (ROOT / path).exists(), f"{item['id']}: {evidence}"
        if item["state"] == "implemented_verified":
            assert item["remaining_human"] is None, item["id"]
        else:
            assert item["remaining_human"], item["id"]
