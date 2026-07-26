#!/usr/bin/env python3
"""Generate the deterministic, credential-free P17 empty-ledger STOP fixture."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from saas_preflight.control_cycle import SigningRole, create_verification_key
from saas_preflight.settlement_amendment import (
    SettlementAmendmentPolicy,
    SettlementAmendmentTrustStore,
    hash_settlement_policy,
    hash_settlement_trust_store,
)
from saas_preflight.traction_control import (
    TractionAuthorityPins,
    TractionEvaluationBundle,
    TractionPolicy,
    TractionTrustStore,
    evaluate_traction,
    hash_traction_artifact,
    hash_traction_policy,
    hash_traction_trust_store,
    sign_traction_plan,
)


START = datetime(2026, 8, 1, tzinfo=ZoneInfo("Asia/Tokyo")).astimezone(
    timezone.utc
)
AT = START


def digest(index: int) -> str:
    return f"{index:064x}"


def private_key(index: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([index]) * 32)


def verification_key(index: int, issuer: str, role: SigningRole):
    return create_verification_key(
        private_key(index).public_key(), issuer=issuer, role=role
    )


def build_models():
    traction_trust = TractionTrustStore(
        plan_human=verification_key(
            31, "fixture-traction-human", SigningRole.HUMAN_APPROVER
        ),
        observation_tco_qa=verification_key(
            32, "fixture-traction-tco", SigningRole.TCO_QA
        ),
        clock_auditor=verification_key(
            35, "fixture-traction-clock", SigningRole.TIME_AUDITOR
        ),
    )
    settlement_trust = SettlementAmendmentTrustStore(
        amendment_producer=verification_key(
            33, "fixture-settlement-producer", SigningRole.COHORT_PRODUCER
        ),
        completeness_verifier=verification_key(
            34, "fixture-settlement-tco", SigningRole.TCO_QA
        ),
    )
    p12_policy_sha256 = digest(101)
    p12_trust_sha256 = digest(102)
    settlement_policy = SettlementAmendmentPolicy(
        trust_store_sha256=hash_settlement_trust_store(settlement_trust),
        p12_policy_sha256=p12_policy_sha256,
        p12_trust_store_sha256=p12_trust_sha256,
        completeness_rule_sha256=digest(103),
        maximum_amendment_ttl_seconds=604800,
        maximum_completeness_ttl_seconds=604800,
    )
    traction_policy = TractionPolicy(
        trust_store_sha256=hash_traction_trust_store(traction_trust),
        ledger_store_id_sha256=digest(104),
        p12_policy_sha256=p12_policy_sha256,
        p12_trust_store_sha256=p12_trust_sha256,
        settlement_policy_sha256=hash_settlement_policy(settlement_policy),
        settlement_trust_store_sha256=hash_settlement_trust_store(
            settlement_trust
        ),
        identity_hmac_key_id_sha256=digest(105),
        maximum_plan_ttl_seconds=34560000,
        maximum_observation_ttl_seconds=604800,
    )
    expires = START + timedelta(days=240)
    plan = sign_traction_plan(
        policy=traction_policy,
        trust_store=traction_trust,
        signing_key=private_key(31),
        issuer="fixture-traction-human",
        property_record_sha256=digest(106),
        property_domain_sha256=digest(107),
        measured_release_sha256=digest(108),
        measured_artifact_sha256=digest(109),
        measured_schema_sha256=digest(110),
        partner_ids=("partner-a", "partner-b", "partner-c"),
        rights_evidence_sha256=digest(111),
        rights_expires_at=expires + timedelta(days=1),
        affiliate_evidence_sha256=digest(112),
        affiliate_expires_at=expires + timedelta(days=1),
        experiment_started_at=START,
        issued_at=START - timedelta(days=1),
        expires_at=expires,
    )
    pins = TractionAuthorityPins(
        expected_policy_sha256=hash_traction_policy(traction_policy),
        expected_trust_store_sha256=hash_traction_trust_store(traction_trust),
        expected_plan_sha256=hash_traction_artifact(plan),
        expected_ledger_store_id_sha256=traction_policy.ledger_store_id_sha256,
        expected_property_record_sha256=plan.property_record_sha256,
        expected_property_domain_sha256=plan.property_domain_sha256,
        expected_release_sha256=plan.measured_release_sha256,
        expected_artifact_sha256=plan.measured_artifact_sha256,
        expected_schema_sha256=plan.measured_schema_sha256,
        expected_partner_set_sha256=plan.partner_set_sha256,
        expected_p12_policy_sha256=plan.p12_policy_sha256,
        expected_p12_trust_store_sha256=plan.p12_trust_store_sha256,
        expected_settlement_policy_sha256=plan.settlement_policy_sha256,
        expected_settlement_trust_store_sha256=plan.settlement_trust_store_sha256,
    )
    bundle = TractionEvaluationBundle()
    report = evaluate_traction(
        bundle.observations,
        plan=plan,
        policy=traction_policy,
        trust_store=traction_trust,
        authority_pins=pins,
        settlement_evidence=bundle.settlement_evidence,
        settlement_policy=settlement_policy,
        settlement_trust_store=settlement_trust,
        at=AT,
    )
    return (
        traction_trust,
        traction_policy,
        plan,
        pins,
        settlement_trust,
        settlement_policy,
        bundle,
        report,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("examples/p17/blocked"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    names = (
        "trust-store.json",
        "policy.json",
        "plan.json",
        "authority-pins.json",
        "settlement-trust-store.json",
        "settlement-policy.json",
        "evidence-bundle.json",
        "expected-stop-report.json",
    )
    for name, model in zip(names, build_models(), strict=True):
        (args.output_dir / name).write_text(
            json.dumps(
                model.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
