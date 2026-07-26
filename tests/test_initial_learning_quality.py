from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from saas_preflight.cli import run as run_cli
from saas_preflight.growth_system import GoldDomain, LearningGoldCase, LearningGoldSet
from saas_preflight.initial_learning_quality import (
    InitialLearningAttestation,
    InitialLearningAttestationRole,
    InitialLearningDatasetProfile,
    InitialLearningQualityBundle,
    InitialLearningQualityDecision,
    InitialLearningQualityPolicy,
    InitialLearningQualityReason,
    InitialLearningSourceKind,
    InitialLearningTrustStore,
    InitialLearningVerificationKey,
    build_initial_learning_verification_key,
    evaluate_initial_learning_quality,
    hash_initial_learning_artifact,
    initial_learning_authority_sha256,
    initial_learning_input_root_sha256,
    sign_initial_learning_attestation,
)


AT = datetime(2026, 7, 23, 3, 0, tzinfo=timezone.utc)


def _h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _verification_key(
    private_key: Ed25519PrivateKey, issuer: str
) -> InitialLearningVerificationKey:
    return build_initial_learning_verification_key(
        private_key.public_key(), issuer=issuer
    )


def _trust_material() -> tuple[
    InitialLearningTrustStore, dict[InitialLearningAttestationRole, Ed25519PrivateKey]
]:
    private_keys = {
        InitialLearningAttestationRole.SOURCE_STEWARD: Ed25519PrivateKey.generate(),
        InitialLearningAttestationRole.HUMAN_LABELER: Ed25519PrivateKey.generate(),
        InitialLearningAttestationRole.TCO_QA: Ed25519PrivateKey.generate(),
    }
    trust_store = InitialLearningTrustStore(
        source_steward=_verification_key(
            private_keys[InitialLearningAttestationRole.SOURCE_STEWARD], "source-owner"
        ),
        human_labeler=_verification_key(
            private_keys[InitialLearningAttestationRole.HUMAN_LABELER], "human-labeler"
        ),
        tco_qa=_verification_key(
            private_keys[InitialLearningAttestationRole.TCO_QA], "independent-qa"
        ),
    )
    return trust_store, private_keys


def _policy(
    *,
    required: tuple[InitialLearningSourceKind, ...] = (
        InitialLearningSourceKind.FIELD_EVIDENCE,
        InitialLearningSourceKind.KEYWORD_DEMAND,
    ),
) -> InitialLearningQualityPolicy:
    return InitialLearningQualityPolicy(
        policy_id_sha256=_h("initial-learning-policy-v1"),
        created_at=AT - timedelta(days=1),
        expires_at=AT + timedelta(days=30),
        required_source_kinds=required,
        join_required_kinds=(InitialLearningSourceKind.KEYWORD_DEMAND,),
        minimum_cases_per_domain=3,
    )


def _profile(
    kind: InitialLearningSourceKind,
    *,
    rows_accepted: int = 100,
    duplicate_rows: int = 0,
    quarantined_rows: int = 0,
    required_values_missing: int = 0,
    orphan_rows: int = 0,
    join_parent_rows: int = 100,
    join_matched_rows: int = 100,
    schema_drift_detected: bool = False,
    duplicate_headers_detected: bool = False,
    mixed_currency_detected: bool = False,
    ambiguous_timestamps_detected: bool = False,
    unknown_state_rows: int = 0,
    synthetic: bool = False,
) -> InitialLearningDatasetProfile:
    label = kind.value
    return InitialLearningDatasetProfile(
        dataset_id_sha256=_h(f"dataset:{label}"),
        kind=kind,
        raw_export_receipt_sha256=_h(f"raw:{label}"),
        safe_summary_sha256=_h(f"summary:{label}"),
        authority_record_sha256=_h(f"authority:{label}"),
        schema_sha256=_h(f"schema:{label}"),
        mapping_version_sha256=_h(f"mapping:{label}"),
        extraction_spec_sha256=_h(f"extraction:{label}"),
        coverage_manifest_sha256=_h(f"coverage:{label}"),
        expected_grain_sha256=_h(f"grain:{label}"),
        candidate_key_sha256=_h(f"key:{label}"),
        reporting_period_start=AT - timedelta(days=7),
        reporting_period_end=AT - timedelta(hours=1),
        captured_at=AT - timedelta(minutes=30),
        expires_at=AT + timedelta(days=7),
        source_timezone="Asia/Tokyo",
        rows_received=rows_accepted + duplicate_rows + quarantined_rows,
        rows_accepted=rows_accepted,
        duplicate_rows=duplicate_rows,
        quarantined_rows=quarantined_rows,
        required_values_total=500,
        required_values_missing=required_values_missing,
        orphan_rows=orphan_rows,
        join_parent_rows=join_parent_rows,
        join_matched_rows=join_matched_rows,
        schema_drift_detected=schema_drift_detected,
        duplicate_headers_detected=duplicate_headers_detected,
        mixed_currency_detected=mixed_currency_detected,
        ambiguous_timestamps_detected=ambiguous_timestamps_detected,
        unknown_state_rows=unknown_state_rows,
        synthetic=synthetic,
    )


def _gold_set(*, synthetic: bool = False) -> LearningGoldSet:
    cases = tuple(
        sorted(
            (
                LearningGoldCase(
                    case_id_sha256=_h(f"case:{domain.value}:{index}"),
                    domain=domain,
                    input_artifact_sha256=_h(f"input:{domain.value}:{index}"),
                    expected_artifact_sha256=_h(f"expected:{domain.value}:{index}"),
                    human_label_receipt_sha256=_h(f"receipt:{domain.value}:{index}"),
                    synthetic=synthetic,
                    labeled_at=AT - timedelta(hours=3),
                    expires_at=AT + timedelta(days=30),
                )
                for domain in GoldDomain
                for index in range(3)
            ),
            key=lambda item: item.case_id_sha256,
        )
    )
    return LearningGoldSet(
        goldset_id_sha256=_h("owned-learning-gold-v1"),
        created_at=AT - timedelta(hours=2),
        expires_at=AT + timedelta(days=30),
        cases=cases,
    )


def _attestation(
    private_key: Ed25519PrivateKey,
    verification_key: InitialLearningVerificationKey,
    *,
    role: InitialLearningAttestationRole,
    subject_sha256: str,
    policy_sha256: str,
) -> InitialLearningAttestation:
    return sign_initial_learning_attestation(
        private_key,
        verification_key,
        role=role,
        subject_sha256=subject_sha256,
        policy_sha256=policy_sha256,
        issued_at=AT - timedelta(minutes=15),
        expires_at=AT + timedelta(days=7),
    )


def _bundle(
    policy: InitialLearningQualityPolicy,
    trust_store: InitialLearningTrustStore,
    private_keys: dict[InitialLearningAttestationRole, Ed25519PrivateKey],
    *,
    datasets: tuple[InitialLearningDatasetProfile, ...] | None = None,
    gold_set: LearningGoldSet | None = None,
) -> InitialLearningQualityBundle:
    selected_datasets = datasets if datasets is not None else tuple(
        sorted(
            (
                _profile(InitialLearningSourceKind.FIELD_EVIDENCE),
                _profile(InitialLearningSourceKind.KEYWORD_DEMAND),
            ),
            key=lambda item: (item.kind.value, item.dataset_id_sha256),
        )
    )
    selected_gold_set = gold_set or _gold_set()
    policy_sha256 = hash_initial_learning_artifact(policy)
    attestations = [
        _attestation(
            private_keys[InitialLearningAttestationRole.SOURCE_STEWARD],
            trust_store.source_steward,
            role=InitialLearningAttestationRole.SOURCE_STEWARD,
            subject_sha256=hash_initial_learning_artifact(dataset),
            policy_sha256=policy_sha256,
        )
        for dataset in selected_datasets
    ]
    attestations.append(
        _attestation(
            private_keys[InitialLearningAttestationRole.HUMAN_LABELER],
            trust_store.human_labeler,
            role=InitialLearningAttestationRole.HUMAN_LABELER,
            subject_sha256=hash_initial_learning_artifact(selected_gold_set),
            policy_sha256=policy_sha256,
        )
    )
    ordered_attestations = tuple(
        sorted(
            attestations,
            key=lambda item: (
                item.role.value,
                item.subject_sha256,
                item.payload_sha256,
            ),
        )
    )
    bundle_id_sha256 = _h("initial-learning-bundle-v1")
    input_root_sha256 = initial_learning_input_root_sha256(
        bundle_id_sha256=bundle_id_sha256,
        policy_sha256=policy_sha256,
        datasets=selected_datasets,
        learning_gold_set=selected_gold_set,
        source_and_label_attestations=ordered_attestations,
    )
    qa_attestation = _attestation(
        private_keys[InitialLearningAttestationRole.TCO_QA],
        trust_store.tco_qa,
        role=InitialLearningAttestationRole.TCO_QA,
        subject_sha256=input_root_sha256,
        policy_sha256=policy_sha256,
    )
    return InitialLearningQualityBundle(
        bundle_id_sha256=bundle_id_sha256,
        policy_sha256=policy_sha256,
        datasets=selected_datasets,
        learning_gold_set=selected_gold_set,
        source_and_label_attestations=ordered_attestations,
        input_root_sha256=input_root_sha256,
        qa_attestation=qa_attestation,
    )


def test_verified_real_complete_inputs_are_ready_only_for_human_review() -> None:
    policy = _policy()
    trust_store, private_keys = _trust_material()
    bundle = _bundle(policy, trust_store, private_keys)

    report = evaluate_initial_learning_quality(
        bundle,
        policy,
        trust_store,
        expected_authority_sha256=initial_learning_authority_sha256(
            policy, trust_store
        ),
        at=AT,
    )

    assert report.decision is InitialLearningQualityDecision.READY_FOR_HUMAN_REVIEW
    assert report.reasons == ()
    assert report.authority == "none"
    assert all(check.passed for check in report.checks)


def test_synthetic_human_gold_is_rejected_even_when_signed() -> None:
    policy = _policy()
    trust_store, private_keys = _trust_material()
    bundle = _bundle(
        policy,
        trust_store,
        private_keys,
        gold_set=_gold_set(synthetic=True),
    )

    report = evaluate_initial_learning_quality(
        bundle,
        policy,
        trust_store,
        expected_authority_sha256=initial_learning_authority_sha256(
            policy, trust_store
        ),
        at=AT,
    )

    assert report.decision is InitialLearningQualityDecision.STOP
    assert report.reasons == (InitialLearningQualityReason.GOLDSET_SYNTHETIC,)


def test_dirty_owned_data_is_rejected_before_learning() -> None:
    policy = _policy()
    trust_store, private_keys = _trust_material()
    dirty_keyword = _profile(
        InitialLearningSourceKind.KEYWORD_DEMAND,
        rows_accepted=94,
        duplicate_rows=3,
        quarantined_rows=3,
        required_values_missing=1,
        orphan_rows=1,
        join_matched_rows=98,
        schema_drift_detected=True,
        duplicate_headers_detected=True,
        mixed_currency_detected=True,
        ambiguous_timestamps_detected=True,
        unknown_state_rows=1,
    )
    datasets = tuple(
        sorted(
            (
                _profile(InitialLearningSourceKind.FIELD_EVIDENCE),
                dirty_keyword,
            ),
            key=lambda item: (item.kind.value, item.dataset_id_sha256),
        )
    )
    bundle = _bundle(policy, trust_store, private_keys, datasets=datasets)

    report = evaluate_initial_learning_quality(
        bundle,
        policy,
        trust_store,
        expected_authority_sha256=initial_learning_authority_sha256(
            policy, trust_store
        ),
        at=AT,
    )

    assert report.decision is InitialLearningQualityDecision.STOP
    assert set(report.reasons) >= {
        InitialLearningQualityReason.DUPLICATE_RATE_EXCEEDED,
        InitialLearningQualityReason.QUARANTINE_RATE_EXCEEDED,
        InitialLearningQualityReason.MISSING_RATE_EXCEEDED,
        InitialLearningQualityReason.ORPHAN_ROWS_PRESENT,
        InitialLearningQualityReason.JOIN_COVERAGE_INSUFFICIENT,
        InitialLearningQualityReason.SCHEMA_DRIFT,
        InitialLearningQualityReason.SOURCE_CONTRACT_INVALID,
    }


def test_stale_capture_lag_and_attestations_are_rejected() -> None:
    policy = InitialLearningQualityPolicy.model_validate(
        {
            **_policy().model_dump(),
            "maximum_capture_age_seconds": 60,
            "maximum_reporting_lag_seconds": 60,
            "maximum_attestation_age_seconds": 60,
        }
    )
    trust_store, private_keys = _trust_material()
    bundle = _bundle(policy, trust_store, private_keys)

    report = evaluate_initial_learning_quality(
        bundle,
        policy,
        trust_store,
        expected_authority_sha256=initial_learning_authority_sha256(
            policy, trust_store
        ),
        at=AT,
    )

    assert report.decision is InitialLearningQualityDecision.STOP
    assert set(report.reasons) >= {
        InitialLearningQualityReason.SOURCE_CAPTURE_STALE,
        InitialLearningQualityReason.SOURCE_REPORTING_LAG_EXCEEDED,
        InitialLearningQualityReason.SOURCE_ATTESTATION_INVALID,
        InitialLearningQualityReason.HUMAN_LABEL_ATTESTATION_INVALID,
        InitialLearningQualityReason.QA_ATTESTATION_INVALID,
    }


def test_missing_required_source_and_wrong_authority_root_stop() -> None:
    policy = _policy(
        required=(
            InitialLearningSourceKind.AFFILIATE,
            InitialLearningSourceKind.FIELD_EVIDENCE,
            InitialLearningSourceKind.KEYWORD_DEMAND,
        )
    )
    trust_store, private_keys = _trust_material()
    bundle = _bundle(policy, trust_store, private_keys)

    report = evaluate_initial_learning_quality(
        bundle,
        policy,
        trust_store,
        expected_authority_sha256=_h("wrong-authority"),
        at=AT,
    )

    assert report.decision is InitialLearningQualityDecision.STOP
    assert set(report.reasons) >= {
        InitialLearningQualityReason.AUTHORITY_ROOT_MISMATCH,
        InitialLearningQualityReason.REQUIRED_SOURCE_MISSING,
    }


def test_dataset_profile_rejects_non_reconciling_row_counts() -> None:
    with pytest.raises(ValidationError, match="row accounting must be exact"):
        InitialLearningDatasetProfile(
            **_profile(InitialLearningSourceKind.FIELD_EVIDENCE).model_dump(
                exclude={"rows_received"}
            ),
            rows_received=101,
        )


def test_public_key_id_and_private_signer_must_match() -> None:
    key = Ed25519PrivateKey.generate()
    correct = _verification_key(key, "source-owner")
    with pytest.raises(ValidationError, match="key ID must hash"):
        InitialLearningVerificationKey(
            **correct.model_dump(exclude={"key_id_sha256"}),
            key_id_sha256=_h("wrong-key-id"),
        )
    with pytest.raises(ValueError, match="signer does not match"):
        sign_initial_learning_attestation(
            Ed25519PrivateKey.generate(),
            correct,
            role=InitialLearningAttestationRole.SOURCE_STEWARD,
            subject_sha256=_h("subject"),
            policy_sha256=_h("policy"),
            issued_at=AT,
            expires_at=AT + timedelta(hours=1),
        )


def test_cli_emits_authority_free_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = _policy()
    trust_store, private_keys = _trust_material()
    bundle = _bundle(policy, trust_store, private_keys)
    policy_path = tmp_path / "policy.json"
    trust_path = tmp_path / "trust.json"
    bundle_path = tmp_path / "bundle.json"
    policy_path.write_text(policy.model_dump_json(), encoding="utf-8")
    trust_path.write_text(trust_store.model_dump_json(), encoding="utf-8")
    bundle_path.write_text(bundle.model_dump_json(), encoding="utf-8")

    result = run_cli(
        [
            "evaluate-initial-learning-quality",
            str(bundle_path),
            "--policy",
            str(policy_path),
            "--trust-store",
            str(trust_path),
            "--expected-authority-sha256",
            initial_learning_authority_sha256(policy, trust_store),
            "--at",
            AT.isoformat(),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["decision"] == "ready_for_human_review"
    assert output["authority"] == "none"
