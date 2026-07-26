from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from saas_preflight.launch_semantics import (
    LaunchSemanticGate,
    LaunchSemanticInputError,
    LaunchSemanticReason,
    build_launch_semantic_authority_pins,
    evaluate_launch_semantics,
    hash_launch_semantic_packet,
)

from launch_semantic_support import build_semantic_context


@pytest.fixture(scope="module")
def context():
    return build_semantic_context()


def test_exact_typed_packet_reaches_non_authoritative_semantic_pass(context) -> None:
    report = evaluate_launch_semantics(
        context["packet"],
        context["pins"],
        at=context["at"],
        expected_authority_pins_sha256=context["pins"].pins_sha256,
    )
    assert report.passed is True
    assert tuple(item.gate for item in report.gates) == tuple(LaunchSemanticGate)
    assert all(item.passed and not item.reasons for item in report.gates)
    assert report.authority_effect == "none"
    assert report.authorizes_external_mutation is False


def test_packet_external_authority_root_rejects_complete_substitution(context) -> None:
    with pytest.raises(LaunchSemanticInputError, match="consumer root"):
        evaluate_launch_semantics(
            context["packet"],
            context["pins"],
            at=context["at"],
            expected_authority_pins_sha256="f" * 64,
        )


def test_packet_hash_covers_every_typed_section(context) -> None:
    packet = context["packet"]
    changed_scope = packet.scope.model_copy(
        update={"environment_identity_sha256": "e" * 64}
    )
    values = packet.model_dump(exclude={"packet_sha256"})
    values["scope"] = changed_scope
    with pytest.raises(ValidationError, match="packet hash mismatch"):
        type(packet)(**values, packet_sha256=packet.packet_sha256)


def test_underlying_expiry_cannot_be_extended_by_a_fresh_envelope(context) -> None:
    report = evaluate_launch_semantics(
        context["packet"],
        context["pins"],
        at=context["at"] + timedelta(minutes=5),
        expected_authority_pins_sha256=context["pins"].pins_sha256,
    )
    assert report.passed is False
    p15 = next(
        item
        for item in report.gates
        if item.gate is LaunchSemanticGate.PRODUCTION_INTEGRATION_READINESS
    )
    assert p15.passed is False
    assert LaunchSemanticReason.PRODUCTION_READINESS_INVALID in p15.reasons


def test_consumer_pins_are_exactly_rebuilt_from_packet(context) -> None:
    assert build_launch_semantic_authority_pins(context["packet"]) == context["pins"]
    assert hash_launch_semantic_packet(context["packet"]) == context["packet"].packet_sha256
