#!/usr/bin/env python3
"""Generate the deterministic, credential-free P18 local-verification STOP fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from saas_preflight.repository_acceptance import (
    REQUIRED_REPOSITORY_VERIFICATION_CHECKS,
    RepositoryVerificationFact,
    RepositoryVerificationNetworkMode,
    RepositoryVerificationProvenance,
    build_repository_candidate_manifest,
    build_repository_inventory,
    build_repository_verification_bundle,
    evaluate_repository_acceptance,
    hash_repository_tree,
    hash_repository_verification_command,
)


AT = datetime(2026, 7, 22, 9, 0, tzinfo=timezone.utc)

COMMANDS = (
    "uv run pytest -q <base-suite>",
    "uv run pytest -q tests/test_traction_control.py",
    "uv run pytest -q tests/test_production_consumer.py",
    "uv run python scripts/export_schemas.py --output-dir <temp>",
    "uv run python scripts/generate_p18_pending_fixture.py --output-dir <temp>",
    "uv lock --check",
    "uv run python -m compileall -q src scripts tests",
    "gitleaks detect --source . --no-git --redact --exit-code 1",
    "npm test --prefix site",
    "npm run lint --prefix site",
    "npm audit --prefix site --audit-level=high",
    "uv run python <workflow-verifier>",
    "contract-storage independent audit <fixed-hashes>",
    "tco-qa independent audit <fixed-hashes>",
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_models(repo_root: Path):
    entries = build_repository_inventory(repo_root)
    tree_sha256 = hash_repository_tree(entries)
    facts = tuple(
        RepositoryVerificationFact(
            check=check,
            subject_tree_sha256=tree_sha256,
            command_argv=tuple(command.split()),
            working_directory="repository-root",
            environment_sha256=_sha256("p18-sanitized-environment-v1"),
            network_mode=RepositoryVerificationNetworkMode.DISABLED,
            interpreter_sha256=_sha256("p18-synthetic-interpreter"),
            import_closure_sha256=_sha256("p18-synthetic-import-closure"),
            command_sha256=hash_repository_verification_command(
                command_argv=tuple(command.split()),
                working_directory="repository-root",
                environment_sha256=_sha256("p18-sanitized-environment-v1"),
                network_mode=RepositoryVerificationNetworkMode.DISABLED,
                interpreter_sha256=_sha256("p18-synthetic-interpreter"),
                import_closure_sha256=_sha256(
                    "p18-synthetic-import-closure"
                ),
            ),
            tool_name=f"synthetic-p18-check-{index}",
            tool_version="0.0.0-synthetic",
            provenance=RepositoryVerificationProvenance.SYNTHETIC_CONTRACT,
            executed_at=AT - timedelta(hours=2),
            not_after=AT + timedelta(days=2),
            assertions_executed=1,
            failures=0,
            skipped=0,
            exit_code=0,
            output_sha256=_sha256(f"synthetic-output-{index}"),
        )
        for index, (check, command) in enumerate(
            zip(REQUIRED_REPOSITORY_VERIFICATION_CHECKS, COMMANDS, strict=True),
            1,
        )
    )
    verification = build_repository_verification_bundle(tree_sha256, facts)
    manifest = build_repository_candidate_manifest(
        repo_root,
        verification,
        candidate_id="p11-p18-local-candidate-pending",
        assembled_at=AT,
        expires_at=AT + timedelta(days=1),
    )
    report = evaluate_repository_acceptance(manifest, repo_root, at=AT)
    return verification, manifest, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/local-acceptance/p18-current-stop"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    names = (
        "verification-evidence.synthetic.json",
        "candidate-manifest.pending.json",
        "expected-stop-report.json",
    )
    for name, model in zip(names, build_models(args.repo_root), strict=True):
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
