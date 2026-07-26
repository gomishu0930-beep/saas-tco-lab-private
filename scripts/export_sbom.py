#!/usr/bin/env python3
"""Generate a deterministic CycloneDX SBOM from the committed lockfiles only."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import Any
from urllib.parse import quote, urlsplit


SPEC_VERSION = "1.6"
BOM_VERSION = 1
DEFAULT_UV_LOCK = Path("uv.lock")
DEFAULT_NPM_LOCK = Path("site/package-lock.json")
DEFAULT_OUTPUT = Path("artifacts/release-assurance/sbom.cdx.json")

_HASH_ALGORITHMS = {
    "sha256": ("SHA-256", 32),
    "sha384": ("SHA-384", 48),
    "sha512": ("SHA-512", 64),
}
_PYTHON_NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_NPM_PART_PATTERN = re.compile(r"^[A-Za-z0-9_.~!-][A-Za-z0-9_.~!+-]*$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]*$")


class SbomError(ValueError):
    """Raised when lockfile evidence cannot safely produce an SBOM."""


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SbomError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SbomError(f"{label} must be an array")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SbomError(f"{label} must be a non-empty trimmed string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SbomError(f"{label} contains a control character")
    return value


def _load_bytes(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise SbomError(f"missing {label}: {path}")
        return path.read_bytes()
    except OSError as exc:
        raise SbomError(f"cannot read {label}: {path}: {exc}") from exc


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SbomError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> Any:
    raise SbomError(f"non-finite JSON number is not allowed: {value}")


def _load_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = data.decode("utf-8")
        loaded = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SbomError(f"malformed {label}: {exc}") from exc
    return _require_mapping(loaded, label)


def _load_toml(data: bytes, label: str) -> dict[str, Any]:
    try:
        loaded = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise SbomError(f"malformed {label}: {exc}") from exc
    return _require_mapping(loaded, label)


def _validate_https_url(value: Any, label: str) -> str:
    url = _require_text(value, label)
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        raise SbomError(f"malformed {label}: {url}") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "?" in url
        or "#" in url
        or any(character.isspace() for character in url)
    ):
        raise SbomError(f"insecure or credential-bearing {label}: {url}")
    return url


def _python_name(value: Any, label: str) -> str:
    name = _require_text(value, label)
    if not _PYTHON_NAME_PATTERN.fullmatch(name):
        raise SbomError(f"malformed {label}: {name}")
    return re.sub(r"[-_.]+", "-", name).lower()


def _npm_name(value: Any, label: str) -> str:
    name = _require_text(value, label)
    if name.startswith("@"):
        parts = name.split("/")
        if (
            len(parts) != 2
            or len(parts[0]) == 1
            or not _NPM_PART_PATTERN.fullmatch(parts[0][1:])
            or not _NPM_PART_PATTERN.fullmatch(parts[1])
            or parts[0][1:] in {".", ".."}
            or parts[1] in {".", ".."}
        ):
            raise SbomError(f"malformed {label}: {name}")
    elif "/" in name or name in {".", ".."} or not _NPM_PART_PATTERN.fullmatch(name):
        raise SbomError(f"malformed {label}: {name}")
    return name


def _version(value: Any, label: str) -> str:
    version = _require_text(value, label)
    if not _VERSION_PATTERN.fullmatch(version):
        raise SbomError(f"malformed {label}: {version}")
    return version


def _optional_bool(mapping: dict[str, Any], field: str, label: str) -> bool:
    if field not in mapping:
        return False
    value = mapping[field]
    if type(value) is not bool:
        raise SbomError(f"{label}.{field} must be a boolean")
    return value


def _pypi_purl(name: str, version: str) -> str:
    return f"pkg:pypi/{quote(name, safe='')}@{quote(version, safe='')}"


def _npm_purl(name: str, version: str) -> str:
    if name.startswith("@"):
        namespace, package = name.split("/", 1)
        encoded_name = f"{quote(namespace, safe='')}/{quote(package, safe='')}"
    else:
        encoded_name = quote(name, safe="")
    return f"pkg:npm/{encoded_name}@{quote(version, safe='')}"


def _hash_entry(raw_hash: Any, label: str) -> dict[str, str]:
    text = _require_text(raw_hash, label)
    if ":" not in text:
        raise SbomError(f"malformed {label}: expected algorithm:digest")
    algorithm, digest = text.split(":", 1)
    algorithm = algorithm.lower()
    specification = _HASH_ALGORITHMS.get(algorithm)
    if specification is None:
        raise SbomError(f"unsupported {label} algorithm: {algorithm}")
    cyclone_name, byte_count = specification
    if len(digest) != byte_count * 2 or not re.fullmatch(r"[0-9A-Fa-f]+", digest):
        raise SbomError(f"malformed {label} digest")
    return {"alg": cyclone_name, "content": digest.lower()}


def _integrity_hashes(value: Any, label: str) -> list[dict[str, str]]:
    integrity = _require_text(value, label)
    hashes: set[tuple[str, str]] = set()
    for token in integrity.split():
        if "-" not in token:
            raise SbomError(f"malformed {label}")
        algorithm, encoded = token.split("-", 1)
        specification = _HASH_ALGORITHMS.get(algorithm.lower())
        if specification is None:
            raise SbomError(f"unsupported {label} algorithm: {algorithm}")
        cyclone_name, byte_count = specification
        try:
            digest = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise SbomError(f"malformed {label} base64") from exc
        if len(digest) != byte_count:
            raise SbomError(f"malformed {label} digest length")
        if base64.b64encode(digest).decode("ascii") != encoded:
            raise SbomError(f"non-canonical {label} base64")
        hashes.add((cyclone_name, digest.hex()))
    if not hashes:
        raise SbomError(f"missing {label} hash")
    return [{"alg": algorithm, "content": digest} for algorithm, digest in sorted(hashes)]


def _properties(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in sorted(values.items())]


def _parse_uv_distribution(value: Any, label: str) -> tuple[str, dict[str, str]]:
    distribution = _require_mapping(value, label)
    url = _validate_https_url(distribution.get("url"), f"{label}.url")
    digest = _hash_entry(distribution.get("hash"), f"{label}.hash")
    return url, digest


def _uv_dependency_entries(package: dict[str, Any], label: str) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    if "dependencies" in package:
        for index, dependency in enumerate(_require_list(package["dependencies"], f"{label}.dependencies")):
            dependencies.append(_require_mapping(dependency, f"{label}.dependencies[{index}]"))
    if "dev-dependencies" in package:
        groups = _require_mapping(package["dev-dependencies"], f"{label}.dev-dependencies")
        for group_name in sorted(groups):
            _require_text(group_name, f"{label}.dev-dependencies group")
            group = _require_list(groups[group_name], f"{label}.dev-dependencies.{group_name}")
            for index, dependency in enumerate(group):
                dependencies.append(
                    _require_mapping(dependency, f"{label}.dev-dependencies.{group_name}[{index}]")
                )
    return dependencies


def _uv_components(lock: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    if lock.get("version") != 1 or type(lock.get("revision")) is not int:
        raise SbomError("uv.lock has an unsupported or missing version/revision")
    packages = _require_list(lock.get("package"), "uv.lock.package")
    if not packages:
        raise SbomError("uv.lock.package must not be empty")

    records: list[tuple[dict[str, Any], str, str, str]] = []
    refs: set[str] = set()
    by_name: dict[str, list[tuple[dict[str, Any], str, str, str]]] = {}
    root_count = 0
    for index, raw_package in enumerate(packages):
        label = f"uv.lock.package[{index}]"
        package = _require_mapping(raw_package, label)
        name = _python_name(package.get("name"), f"{label}.name")
        version = _version(package.get("version"), f"{label}.version")
        source = _require_mapping(package.get("source"), f"{label}.source")
        purl = _pypi_purl(name, version)
        if purl in refs:
            raise SbomError(f"duplicate Python component identity: {purl}")
        refs.add(purl)
        if set(source) == {"editable"}:
            if source["editable"] != ".":
                raise SbomError(f"{label}.source editable path must be '.'")
            root_count += 1
        elif set(source) == {"registry"}:
            _validate_https_url(source["registry"], f"{label}.source.registry")
        else:
            raise SbomError(f"{label}.source must be one HTTPS registry or editable '.'")
        record = (package, name, version, purl)
        records.append(record)
        by_name.setdefault(name, []).append(record)
    if root_count != 1:
        raise SbomError("uv.lock must contain exactly one editable root application")

    components: list[dict[str, Any]] = []
    dependency_graph: dict[str, list[str]] = {}
    for package, name, version, purl in records:
        source = package["source"]
        is_root = "editable" in source
        component: dict[str, Any] = {
            "bom-ref": purl,
            "type": "application" if is_root else "library",
            "name": name,
            "version": version,
            "purl": purl,
            "properties": _properties({"saas-preflight:ecosystem": "PyPI"}),
        }
        if not is_root:
            distributions: list[tuple[str, dict[str, str]]] = []
            if "sdist" in package:
                distributions.append(_parse_uv_distribution(package["sdist"], f"uv package {purl}.sdist"))
            if "wheels" in package:
                wheels = _require_list(package["wheels"], f"uv package {purl}.wheels")
                for index, wheel in enumerate(wheels):
                    distributions.append(_parse_uv_distribution(wheel, f"uv package {purl}.wheels[{index}]"))
            if not distributions:
                raise SbomError(f"Python component has no hashed distribution: {purl}")
            distribution_refs = []
            component_hashes: set[tuple[str, str]] = set()
            for url, digest in distributions:
                component_hashes.add((digest["alg"], digest["content"]))
                distribution_refs.append({"type": "distribution", "url": url, "hashes": [digest]})
            component["hashes"] = [
                {"alg": algorithm, "content": digest}
                for algorithm, digest in sorted(component_hashes)
            ]
            component["externalReferences"] = sorted(distribution_refs, key=lambda item: item["url"])

        dependency_refs: set[str] = set()
        for dependency in _uv_dependency_entries(package, f"uv package {purl}"):
            dependency_name = _python_name(dependency.get("name"), f"uv package {purl} dependency.name")
            candidates = by_name.get(dependency_name, [])
            if "version" in dependency:
                dependency_version = _version(
                    dependency["version"], f"uv package {purl} dependency.version"
                )
                candidates = [candidate for candidate in candidates if candidate[2] == dependency_version]
            if len(candidates) != 1:
                raise SbomError(
                    f"dependency cannot be resolved uniquely: {purl} -> {dependency_name}"
                )
            dependency_refs.add(candidates[0][3])
        dependency_graph[purl] = sorted(dependency_refs)
        components.append(component)
    return components, dependency_graph


def _npm_path_name(path: str) -> str:
    if not path or path.startswith("/") or "\\" in path:
        raise SbomError(f"malformed npm lock path: {path}")
    parts = path.split("/")
    index = 0
    last_name = ""
    while index < len(parts):
        if parts[index] != "node_modules":
            raise SbomError(f"malformed npm lock path: {path}")
        index += 1
        if index >= len(parts):
            raise SbomError(f"malformed npm lock path: {path}")
        if parts[index].startswith("@"):
            if index + 1 >= len(parts):
                raise SbomError(f"malformed npm lock path: {path}")
            last_name = f"{parts[index]}/{parts[index + 1]}"
            index += 2
        else:
            last_name = parts[index]
            index += 1
        _npm_name(last_name, f"npm lock path {path}")
    return last_name


def _npm_bom_ref(path: str, purl: str) -> str:
    path_digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return f"urn:saas-preflight:npm-lock:{path_digest}:{purl}"


def _npm_dependency_names(
    package: dict[str, Any], label: str, *, root: bool
) -> list[tuple[str, bool]]:
    fields = ["dependencies", "optionalDependencies"]
    if root:
        fields.append("devDependencies")
    requirements: dict[str, bool] = {}
    for field in fields:
        if field not in package:
            continue
        dependencies = _require_mapping(package[field], f"{label}.{field}")
        for raw_name, raw_constraint in dependencies.items():
            name = _npm_name(raw_name, f"{label}.{field} name")
            _require_text(raw_constraint, f"{label}.{field}.{name}")
            requirements[name] = True

    peer_dependencies = _require_mapping(
        package.get("peerDependencies", {}), f"{label}.peerDependencies"
    )
    peer_metadata = _require_mapping(
        package.get("peerDependenciesMeta", {}), f"{label}.peerDependenciesMeta"
    )
    for raw_name, raw_metadata in peer_metadata.items():
        metadata_name = _npm_name(raw_name, f"{label}.peerDependenciesMeta name")
        metadata = _require_mapping(raw_metadata, f"{label}.peerDependenciesMeta.{metadata_name}")
        _optional_bool(metadata, "optional", f"{label}.peerDependenciesMeta.{metadata_name}")
    for raw_name, raw_constraint in peer_dependencies.items():
        name = _npm_name(raw_name, f"{label}.peerDependencies name")
        _require_text(raw_constraint, f"{label}.peerDependencies.{name}")
        metadata = _require_mapping(peer_metadata.get(raw_name, {}), f"{label}.peerDependenciesMeta.{name}")
        optional = _optional_bool(metadata, "optional", f"{label}.peerDependenciesMeta.{name}")
        requirements[name] = requirements.get(name, False) or not optional
    return sorted(requirements.items())


def _resolve_npm_dependency(path: str, dependency_name: str, paths: set[str]) -> str | None:
    base = path
    while True:
        candidate = f"{base}/node_modules/{dependency_name}" if base else f"node_modules/{dependency_name}"
        if candidate in paths:
            return candidate
        marker = base.rfind("/node_modules/")
        if marker >= 0:
            base = base[:marker]
        elif base:
            base = ""
        else:
            return None


def _npm_components(lock: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    if lock.get("lockfileVersion") != 3:
        raise SbomError("package-lock.json lockfileVersion must be 3")
    if lock.get("requires") is not True:
        raise SbomError("package-lock.json requires must be true")
    packages = _require_mapping(lock.get("packages"), "package-lock.json.packages")
    root = _require_mapping(packages.get(""), "package-lock.json.packages['']")
    root_name = _npm_name(root.get("name"), "npm root name")
    root_version = _version(root.get("version"), "npm root version")
    if lock.get("name") != root_name or lock.get("version") != root_version:
        raise SbomError("package-lock.json root name/version mismatch")

    root_purl = _npm_purl(root_name, root_version)
    components: list[dict[str, Any]] = [
        {
            "bom-ref": root_purl,
            "type": "application",
            "name": root_name,
            "version": root_version,
            "purl": root_purl,
            "properties": _properties({"saas-preflight:ecosystem": "npm"}),
        }
    ]
    refs_by_path: dict[str, str] = {"": root_purl}
    parsed_packages: dict[str, tuple[dict[str, Any], str, str]] = {}
    seen_refs = {root_purl}
    for path, raw_package in packages.items():
        if path == "":
            continue
        _require_text(path, "npm lock package path")
        package = _require_mapping(raw_package, f"npm package {path}")
        name = _npm_path_name(path)
        if "name" in package and _npm_name(package["name"], f"npm package {path}.name") != name:
            raise SbomError(f"npm package name/path mismatch: {path}")
        version = _version(package.get("version"), f"npm package {path}.version")
        for flag in ("dev", "optional", "inBundle", "link"):
            _optional_bool(package, flag, f"npm package {path}")
        if package.get("link") is True:
            raise SbomError(f"npm package link source is not allowed: {path}")
        purl = _npm_purl(name, version)
        bom_ref = _npm_bom_ref(path, purl)
        if bom_ref in seen_refs:
            raise SbomError(f"duplicate npm component identity: {bom_ref}")
        seen_refs.add(bom_ref)
        refs_by_path[path] = bom_ref
        parsed_packages[path] = (package, name, version)

    paths = set(parsed_packages)
    dependency_graph: dict[str, list[str]] = {}
    root_dependencies: set[str] = set()
    for dependency_name, required in _npm_dependency_names(root, "npm root", root=True):
        resolved = _resolve_npm_dependency("", dependency_name, paths)
        if resolved is None:
            if required:
                raise SbomError(f"npm dependency cannot be resolved: root -> {dependency_name}")
            continue
        root_dependencies.add(refs_by_path[resolved])
    dependency_graph[root_purl] = sorted(root_dependencies)

    for path, (package, name, version) in parsed_packages.items():
        purl = _npm_purl(name, version)
        bom_ref = refs_by_path[path]
        in_bundle = _optional_bool(package, "inBundle", f"npm package {path}")
        resolved_value = package.get("resolved")
        integrity_value = package.get("integrity")
        if resolved_value is None:
            if not in_bundle or integrity_value is not None:
                raise SbomError(f"npm package lacks a trusted resolved source: {path}")
            resolved = None
            hashes: list[dict[str, str]] = []
        else:
            resolved = _validate_https_url(resolved_value, f"npm package {path}.resolved")
            hashes = _integrity_hashes(integrity_value, f"npm package {path}.integrity")

        scope = "optional" if _optional_bool(package, "optional", f"npm package {path}") else (
            "excluded" if _optional_bool(package, "dev", f"npm package {path}") else "required"
        )
        component: dict[str, Any] = {
            "bom-ref": bom_ref,
            "type": "library",
            "name": name,
            "version": version,
            "purl": purl,
            "scope": scope,
            "properties": _properties(
                {
                    "saas-preflight:ecosystem": "npm",
                    "saas-preflight:npm:lock-path": path,
                }
            ),
        }
        if hashes:
            component["hashes"] = hashes
            component["externalReferences"] = [
                {"type": "distribution", "url": resolved, "hashes": hashes}
            ]
        license_value = package.get("license")
        if license_value is not None:
            license_name = _require_text(license_value, f"npm package {path}.license")
            component["licenses"] = [{"license": {"name": license_name}}]

        dependency_refs: set[str] = set()
        for dependency_name, required in _npm_dependency_names(
            package, f"npm package {path}", root=False
        ):
            dependency_path = _resolve_npm_dependency(path, dependency_name, paths)
            if dependency_path is None:
                if required:
                    raise SbomError(f"npm dependency cannot be resolved: {path} -> {dependency_name}")
                continue
            dependency_refs.add(refs_by_path[dependency_path])
        dependency_graph[bom_ref] = sorted(dependency_refs)
        components.append(component)
    return components, dependency_graph


def build_sbom(uv_lock_path: Path, npm_lock_path: Path) -> dict[str, Any]:
    """Build one deterministic CycloneDX document from two exact lockfiles."""

    uv_bytes = _load_bytes(uv_lock_path, "uv.lock")
    npm_bytes = _load_bytes(npm_lock_path, "package-lock.json")
    uv_components, uv_dependencies = _uv_components(_load_toml(uv_bytes, "uv.lock"))
    npm_components, npm_dependencies = _npm_components(_load_json(npm_bytes, "package-lock.json"))

    components = sorted(uv_components + npm_components, key=lambda component: component["bom-ref"])
    component_refs = [component["bom-ref"] for component in components]
    if len(component_refs) != len(set(component_refs)):
        raise SbomError("duplicate component identity in generated SBOM")
    graph = uv_dependencies | npm_dependencies
    if set(graph) != set(component_refs):
        raise SbomError("dependency graph does not cover every component")
    for source_ref, dependency_refs in graph.items():
        unresolved = set(dependency_refs) - set(component_refs)
        if unresolved:
            raise SbomError(f"unresolved dependency identity from {source_ref}: {sorted(unresolved)}")

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": BOM_VERSION,
        "metadata": {
            "properties": _properties(
                {
                    "saas-preflight:lockfile:site/package-lock.json:sha256": hashlib.sha256(
                        npm_bytes
                    ).hexdigest(),
                    "saas-preflight:lockfile:uv.lock:sha256": hashlib.sha256(uv_bytes).hexdigest(),
                }
            )
        },
        "components": components,
        "dependencies": [
            {"ref": component_ref, "dependsOn": graph[component_ref]}
            for component_ref in sorted(graph)
        ],
    }


def render_sbom(uv_lock_path: Path, npm_lock_path: Path) -> bytes:
    """Return newline-terminated canonical JSON bytes."""

    document = build_sbom(uv_lock_path, npm_lock_path)
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def export_sbom(
    uv_lock_path: Path,
    npm_lock_path: Path,
    output_path: Path,
    *,
    check: bool = False,
) -> None:
    """Create a new SBOM exclusively, or check an existing artifact without writing."""

    expected = render_sbom(uv_lock_path, npm_lock_path)
    if check:
        actual = _load_bytes(output_path, "SBOM artifact")
        if actual != expected:
            raise SbomError(f"SBOM artifact is stale or non-canonical: {output_path}")
        return

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(expected)
    except FileExistsError as exc:
        raise SbomError(
            f"refusing to overwrite existing SBOM artifact: {output_path}; use --check"
        ) from exc
    except OSError as exc:
        raise SbomError(f"cannot write SBOM artifact: {output_path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv-lock", type=Path, default=DEFAULT_UV_LOCK)
    parser.add_argument("--npm-lock", type=Path, default=DEFAULT_NPM_LOCK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare canonical generated bytes with --output without modifying it",
    )
    args = parser.parse_args(argv)
    try:
        export_sbom(args.uv_lock, args.npm_lock, args.output, check=args.check)
    except SbomError as exc:
        print(f"SBOM error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
