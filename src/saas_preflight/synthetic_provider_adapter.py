"""Credential-free subprocess fixture for the P13 provider protocol.

This is deliberately a local file-state simulator.  It has no network imports,
provider URL, account discovery or production credential support.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saas_preflight.control_cycle import Ed25519VerificationKey, SigningRole
from saas_preflight.production_consumer import (
    ProductionSignatureScope,
    ProviderDispatchToken,
    ProviderOutcome,
    ProviderResultReceipt,
    _file_sha256,
    _build_signed_model,
    _canonical_json_bytes,
    _canonical_sha256,
    _require_utc,
    _verify_signed,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--provider-key", type=Path, required=True)
    parser.add_argument("--dispatcher-key", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--postcondition-schema", type=Path, required=True)
    return parser


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    lock = path.with_suffix(path.suffix + ".lock")
    lock.touch(mode=0o600, exist_ok=True)
    with lock.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_pinned_bytes(path: Path) -> bytes:
    if path.parent == Path("/dev/fd") and path.name.isdigit():
        descriptor = int(path.name)
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        offset = 0
        while chunk := os.pread(descriptor, 1_048_576, offset):
            chunks.append(chunk)
            offset += len(chunk)
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if (
            identity(before) != identity(after)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
        ):
            raise ValueError("pinned adapter input changed")
        return b"".join(chunks)
    return path.read_bytes()


def _private_key(path: Path) -> Ed25519PrivateKey:
    metadata = (
        os.fstat(int(path.name))
        if path.parent == Path("/dev/fd") and path.name.isdigit()
        else path.stat()
    )
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
        raise ValueError("unsafe adapter signing key")
    raw = _read_pinned_bytes(path)
    if len(raw) != 32:
        raise ValueError("invalid adapter signing key")
    return Ed25519PrivateKey.from_private_bytes(raw)


def _read_object(path: Path) -> dict:
    value = json.loads(_read_pinned_bytes(path).decode("utf-8"))
    if type(value) is not dict:
        raise ValueError("fixture object must be a JSON object")
    return value


def _write_state(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, _canonical_json_bytes(value))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _verify_input(args: argparse.Namespace) -> tuple[ProviderDispatchToken, datetime, dict]:
    frame = json.loads(sys.stdin.buffer.read(262_145).decode("utf-8"))
    if type(frame) is not dict or set(frame) != {"token", "at"}:
        raise ValueError("invalid adapter input frame")
    token = ProviderDispatchToken.model_validate_json(
        _canonical_json_bytes(frame["token"])
    )
    at = datetime.fromisoformat(str(frame["at"]).replace("Z", "+00:00"))
    _require_utc(at, "synthetic adapter time")
    dispatcher = Ed25519VerificationKey.model_validate_json(
        _read_pinned_bytes(args.dispatcher_key)
    )
    allowlist = _read_object(args.allowlist)
    schema = _read_object(args.postcondition_schema)
    entries = allowlist.get("entries")
    expected_entry = {
        "operation": token.operation.value,
        "adapter_id": token.adapter_id,
        "store_id_sha256": token.store_id_sha256,
        "target_sha256": token.target_sha256,
        "expected_pre_state_sha256": token.expected_pre_state_sha256,
        "expected_post_state_sha256": token.expected_post_state_sha256,
        "adapter_executable_sha256": token.adapter_executable_sha256,
        "probe_executable_sha256": token.probe_executable_sha256,
        "python_executable_sha256": token.python_executable_sha256,
        "adapter_dependency_closure_sha256":
            token.adapter_dependency_closure_sha256,
        "postcondition_schema_sha256": token.postcondition_schema_sha256,
    }
    if (
        not _verify_signed(token, dispatcher)
        or dispatcher.role is not SigningRole.EXECUTOR
        or not token.issued_at <= at < token.expires_at
        or set(allowlist) != {"schema_version", "entries"}
        or allowlist.get("schema_version") != "1.0"
        or token.provider_allowlist_sha256 != _canonical_sha256(allowlist)
        or type(entries) is not list
        or any(type(entry) is not dict for entry in entries)
        or len({_canonical_sha256(entry) for entry in entries}) != len(entries)
        or expected_entry not in entries
        or hashlib.sha256(
            _read_pinned_bytes(args.postcondition_schema)
        ).hexdigest() != token.postcondition_schema_sha256
        or schema.get("schema_version") != "1.0"
        or _file_sha256(sys.executable) != token.python_executable_sha256
    ):
        raise ValueError("dispatch or provider allowlist verification failed")
    return token, at, allowlist


def _execute(args: argparse.Namespace, token: ProviderDispatchToken, at: datetime) -> dict:
    private = _private_key(args.provider_key)
    with _locked(args.state):
        state = _read_object(args.state)
        if set(state) != {"schema_version", "targets", "operations", "call_count"}:
            raise ValueError("synthetic provider state schema mismatch")
        stored = state["operations"].get(token.idempotency_key_sha256)
        if stored is not None:
            return ProviderResultReceipt.model_validate_json(
                _canonical_json_bytes(stored)
            ).model_dump(mode="json")
        observed_pre = state["targets"].get(token.target_sha256, "0" * 64)
        success = observed_pre == token.expected_pre_state_sha256
        observed_post = (
            token.expected_post_state_sha256 if success else observed_pre
        )
        if success:
            state["targets"][token.target_sha256] = observed_post
        state["call_count"] += 1
        audit = _canonical_sha256(
            {
                "fixture": "synthetic-provider-v1",
                "idempotency_key_sha256": token.idempotency_key_sha256,
                "fencing_token": token.fencing_token,
                "call_count": state["call_count"],
            }
        )
        receipt = _build_signed_model(
            ProviderResultReceipt,
            {
                "issuer": "synthetic-provider-adapter",
                "signer_role": SigningRole.PROVIDER_ADAPTER,
                "scope": ProductionSignatureScope.PROVIDER_RESULT,
                "dispatch_payload_sha256": token.payload_sha256,
                "store_id_sha256": token.store_id_sha256,
                "epoch": token.epoch,
                "fencing_token": token.fencing_token,
                "operation": token.operation,
                "adapter_id": token.adapter_id,
                "target_sha256": token.target_sha256,
                "idempotency_key_sha256": token.idempotency_key_sha256,
                "outcome": ProviderOutcome.SUCCEEDED if success else ProviderOutcome.FAILED,
                "observed_pre_state_sha256": observed_pre,
                "observed_post_state_sha256": observed_post,
                "provider_audit_receipt_sha256": audit,
                "started_at": at,
                "completed_at": at,
            },
            private,
            issuer="synthetic-provider-adapter",
            role=SigningRole.PROVIDER_ADAPTER,
        )
        state["operations"][token.idempotency_key_sha256] = receipt.model_dump(mode="json")
        _write_state(args.state, state)
        return receipt.model_dump(mode="json")


def main() -> int:
    args = _parser().parse_args()
    try:
        token, at, _ = _verify_input(args)
        result = _execute(args, token, at)
        sys.stdout.buffer.write(_canonical_json_bytes(result))
        return 0
    except Exception as exc:
        sys.stderr.write(type(exc).__name__ + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
