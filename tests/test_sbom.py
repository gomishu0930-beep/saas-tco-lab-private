from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from export_sbom import SbomError, build_sbom, export_sbom, main, render_sbom  # noqa: E402


UV_LOCK = REPOSITORY_ROOT / "uv.lock"
NPM_LOCK = REPOSITORY_ROOT / "site" / "package-lock.json"
SBOM_ARTIFACT = REPOSITORY_ROOT / "artifacts" / "release-assurance" / "sbom.cdx.json"

PYTHON_DIGEST = "11" * 32
NPM_DIGEST_BYTES = b"\x22" * 64
NPM_INTEGRITY = "sha512-" + base64.b64encode(NPM_DIGEST_BYTES).decode("ascii")


def uv_lock_text(*, dependency_first: bool = True) -> str:
    dependency = f'''[[package]]
name = "demo-dependency"
version = "2.0.0"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files.pythonhosted.org/demo-dependency-2.0.0.tar.gz", hash = "sha256:{PYTHON_DIGEST}" }}
'''
    root = '''[[package]]
name = "demo-python-app"
version = "1.0.0"
source = { editable = "." }
dependencies = [{ name = "demo-dependency" }]
'''
    packages = dependency + "\n" + root if dependency_first else root + "\n" + dependency
    return f'''version = 1
revision = 3
requires-python = ">=3.12"

{packages}'''


def npm_lock_document(*, dependency_first: bool = False) -> dict[str, object]:
    root = {
        "name": "demo-web-app",
        "version": "1.0.0",
        "dependencies": {"demo-package": "2.0.0"},
    }
    dependency = {
        "version": "2.0.0",
        "resolved": "https://registry.npmjs.org/demo-package/-/demo-package-2.0.0.tgz",
        "integrity": NPM_INTEGRITY,
        "license": "MIT",
    }
    packages = (
        {"node_modules/demo-package": dependency, "": root}
        if dependency_first
        else {"": root, "node_modules/demo-package": dependency}
    )
    return {
        "name": "demo-web-app",
        "version": "1.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": packages,
    }


def write_fixture_locks(
    directory: Path,
    *,
    uv_text: str | None = None,
    npm_document: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    uv_path = directory / "uv.lock"
    npm_path = directory / "site" / "package-lock.json"
    npm_path.parent.mkdir(parents=True, exist_ok=True)
    uv_path.write_text(uv_text or uv_lock_text(), encoding="utf-8")
    npm_path.write_text(
        json.dumps(npm_document or npm_lock_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return uv_path, npm_path


def component_by_purl(document: dict[str, object], purl: str) -> dict[str, object]:
    components = document["components"]
    assert isinstance(components, list)
    return next(component for component in components if component["purl"] == purl)


def metadata_properties(document: dict[str, object]) -> dict[str, str]:
    metadata = document["metadata"]
    assert isinstance(metadata, dict)
    properties = metadata["properties"]
    assert isinstance(properties, list)
    return {item["name"]: item["value"] for item in properties}


def test_deterministic_canonical_sbom_covers_both_ecosystems(tmp_path: Path) -> None:
    uv_path, npm_path = write_fixture_locks(tmp_path)

    first = render_sbom(uv_path, npm_path)
    second = render_sbom(uv_path, npm_path)
    document = json.loads(first)

    assert first == second
    assert first.endswith(b"\n")
    assert first == (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.6"
    assert document["version"] == 1
    assert len(document["components"]) == 4
    assert len(document["dependencies"]) == 4
    assert {
        (component["name"], component["version"])
        for component in document["components"]
        if component["type"] == "application"
    } == {("demo-python-app", "1.0.0"), ("demo-web-app", "1.0.0")}

    python_component = component_by_purl(document, "pkg:pypi/demo-dependency@2.0.0")
    assert python_component["hashes"] == [{"alg": "SHA-256", "content": PYTHON_DIGEST}]
    assert python_component["externalReferences"][0]["url"].startswith("https://")

    npm_component = component_by_purl(document, "pkg:npm/demo-package@2.0.0")
    assert npm_component["hashes"] == [
        {"alg": "SHA-512", "content": NPM_DIGEST_BYTES.hex()}
    ]
    assert npm_component["licenses"] == [{"license": {"name": "MIT"}}]

    properties = metadata_properties(document)
    assert properties["saas-preflight:lockfile:uv.lock:sha256"] == hashlib.sha256(
        uv_path.read_bytes()
    ).hexdigest()
    assert properties["saas-preflight:lockfile:site/package-lock.json:sha256"] == hashlib.sha256(
        npm_path.read_bytes()
    ).hexdigest()
    assert b"timestamp" not in first
    assert str(tmp_path).encode() not in first


def test_real_lockfiles_produce_complete_unique_graph() -> None:
    document = build_sbom(UV_LOCK, NPM_LOCK)
    components = document["components"]
    dependencies = document["dependencies"]
    refs = [component["bom-ref"] for component in components]

    assert len(components) == 451
    assert len(dependencies) == len(components)
    assert len(refs) == len(set(refs))
    assert {dependency["ref"] for dependency in dependencies} == set(refs)
    assert all(set(dependency["dependsOn"]) <= set(refs) for dependency in dependencies)
    assert sum(component["purl"].startswith("pkg:pypi/") for component in components) == 24
    assert sum(component["purl"].startswith("pkg:npm/") for component in components) == 427


def test_semantic_collections_resist_lockfile_permutation(tmp_path: Path) -> None:
    first_uv, first_npm = write_fixture_locks(tmp_path / "first")
    second_uv, second_npm = write_fixture_locks(
        tmp_path / "second",
        uv_text=uv_lock_text(dependency_first=False),
        npm_document=npm_lock_document(dependency_first=True),
    )
    first = build_sbom(first_uv, first_npm)
    second = build_sbom(second_uv, second_npm)

    assert first["components"] == second["components"]
    assert first["dependencies"] == second["dependencies"]
    assert first["metadata"] != second["metadata"]  # exact raw lockfile evidence intentionally changes


def test_output_is_independent_of_workspace_absolute_path(tmp_path: Path) -> None:
    first_uv, first_npm = write_fixture_locks(tmp_path / "one" / "workspace")
    second_root = tmp_path / "unrelated" / "deep" / "workspace"
    second_root.mkdir(parents=True)
    second_uv = second_root / "renamed-python.lock"
    second_npm = second_root / "renamed-node.lock"
    shutil.copyfile(first_uv, second_uv)
    shutil.copyfile(first_npm, second_npm)

    assert render_sbom(first_uv, first_npm) == render_sbom(second_uv, second_npm)


@pytest.mark.parametrize("missing_name", ["uv", "npm"])
def test_missing_lockfile_fails_closed(tmp_path: Path, missing_name: str) -> None:
    uv_path, npm_path = write_fixture_locks(tmp_path)
    (uv_path if missing_name == "uv" else npm_path).unlink()

    with pytest.raises(SbomError, match="missing"):
        render_sbom(uv_path, npm_path)


def test_duplicate_python_identity_fails_closed(tmp_path: Path) -> None:
    duplicate = uv_lock_text() + f'''\n[[package]]
name = "demo_dependency"
version = "2.0.0"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ url = "https://files.pythonhosted.org/duplicate.tar.gz", hash = "sha256:{PYTHON_DIGEST}" }}
'''
    uv_path, npm_path = write_fixture_locks(tmp_path, uv_text=duplicate)

    with pytest.raises(SbomError, match="duplicate Python component identity"):
        render_sbom(uv_path, npm_path)


def test_duplicate_json_key_fails_closed(tmp_path: Path) -> None:
    uv_path, npm_path = write_fixture_locks(tmp_path)
    npm_path.write_text(
        '{"name":"demo-web-app","name":"attacker","version":"1.0.0",'
        '"lockfileVersion":3,"packages":{}}\n',
        encoding="utf-8",
    )

    with pytest.raises(SbomError, match="duplicate JSON key"):
        render_sbom(uv_path, npm_path)


@pytest.mark.parametrize(
    ("ecosystem", "bad_url"),
    [
        ("uv-registry", "http://pypi.org/simple"),
        ("uv-registry", "https://token@example.invalid/simple"),
        ("uv-distribution", "http://files.pythonhosted.org/demo.tar.gz"),
        ("uv-distribution", "https://user:secret@files.pythonhosted.org/demo.tar.gz"),
        ("npm", "http://registry.npmjs.org/demo-package.tgz"),
        ("npm", "https://token@registry.npmjs.org/demo-package.tgz"),
        ("npm", "https://registry.npmjs.org/demo-package.tgz?token=secret"),
        ("npm", "https://registry.npmjs.org/demo-package.tgz?"),
    ],
)
def test_insecure_or_credential_bearing_source_fails_closed(
    tmp_path: Path, ecosystem: str, bad_url: str
) -> None:
    uv_text = uv_lock_text()
    npm_document = npm_lock_document()
    if ecosystem == "uv-registry":
        uv_text = uv_text.replace("https://pypi.org/simple", bad_url)
    elif ecosystem == "uv-distribution":
        uv_text = uv_text.replace(
            "https://files.pythonhosted.org/demo-dependency-2.0.0.tar.gz", bad_url
        )
    else:
        npm_document["packages"]["node_modules/demo-package"]["resolved"] = bad_url
    uv_path, npm_path = write_fixture_locks(
        tmp_path, uv_text=uv_text, npm_document=npm_document
    )

    with pytest.raises(SbomError, match="insecure or credential-bearing"):
        render_sbom(uv_path, npm_path)


@pytest.mark.parametrize(
    "integrity",
    [
        "sha512-not!base64",
        "sha512-" + base64.b64encode(b"too short").decode("ascii"),
        "md5-" + base64.b64encode(b"x" * 16).decode("ascii"),
        "",
    ],
)
def test_malformed_npm_integrity_fails_closed(tmp_path: Path, integrity: str) -> None:
    npm_document = npm_lock_document()
    npm_document["packages"]["node_modules/demo-package"]["integrity"] = integrity
    uv_path, npm_path = write_fixture_locks(tmp_path, npm_document=npm_document)

    with pytest.raises(SbomError, match="integrity"):
        render_sbom(uv_path, npm_path)


@pytest.mark.parametrize("ecosystem", ["uv", "npm"])
def test_missing_version_fails_closed(tmp_path: Path, ecosystem: str) -> None:
    uv_text = uv_lock_text()
    npm_document = npm_lock_document()
    if ecosystem == "uv":
        uv_text = uv_text.replace('version = "2.0.0"\n', "", 1)
    else:
        del npm_document["packages"]["node_modules/demo-package"]["version"]
    uv_path, npm_path = write_fixture_locks(
        tmp_path, uv_text=uv_text, npm_document=npm_document
    )

    with pytest.raises(SbomError, match="version"):
        render_sbom(uv_path, npm_path)


def test_missing_python_distribution_hash_fails_closed(tmp_path: Path) -> None:
    uv_text = uv_lock_text().replace(f', hash = "sha256:{PYTHON_DIGEST}"', "")
    uv_path, npm_path = write_fixture_locks(tmp_path, uv_text=uv_text)

    with pytest.raises(SbomError, match="hash"):
        render_sbom(uv_path, npm_path)


@pytest.mark.parametrize("ecosystem", ["uv", "npm"])
def test_malformed_version_fails_closed(tmp_path: Path, ecosystem: str) -> None:
    uv_text = uv_lock_text()
    npm_document = npm_lock_document()
    if ecosystem == "uv":
        uv_text = uv_text.replace('version = "2.0.0"', 'version = "../../2.0.0"', 1)
    else:
        npm_document["packages"]["node_modules/demo-package"]["version"] = "2.0.0/path"
    uv_path, npm_path = write_fixture_locks(
        tmp_path, uv_text=uv_text, npm_document=npm_document
    )

    with pytest.raises(SbomError, match="malformed .*version"):
        render_sbom(uv_path, npm_path)


@pytest.mark.parametrize("ecosystem", ["uv", "npm"])
def test_unresolved_dependency_fails_closed(tmp_path: Path, ecosystem: str) -> None:
    uv_text = uv_lock_text()
    npm_document = npm_lock_document()
    if ecosystem == "uv":
        uv_text = uv_text.replace(
            'dependencies = [{ name = "demo-dependency" }]',
            'dependencies = [{ name = "missing-dependency" }]',
        )
    else:
        npm_document["packages"][""]["dependencies"] = {"missing-package": "1.0.0"}
    uv_path, npm_path = write_fixture_locks(
        tmp_path, uv_text=uv_text, npm_document=npm_document
    )

    with pytest.raises(SbomError, match="cannot be resolved"):
        render_sbom(uv_path, npm_path)


def test_non_bundled_npm_package_requires_source_and_integrity(tmp_path: Path) -> None:
    npm_document = npm_lock_document()
    package = npm_document["packages"]["node_modules/demo-package"]
    del package["resolved"]
    del package["integrity"]
    uv_path, npm_path = write_fixture_locks(tmp_path, npm_document=npm_document)

    with pytest.raises(SbomError, match="trusted resolved source"):
        render_sbom(uv_path, npm_path)


def test_optional_missing_peer_is_not_an_installed_dependency(tmp_path: Path) -> None:
    npm_document = npm_lock_document()
    package = npm_document["packages"]["node_modules/demo-package"]
    package["peerDependencies"] = {"optional-peer": "^1.0.0"}
    package["peerDependenciesMeta"] = {"optional-peer": {"optional": True}}
    uv_path, npm_path = write_fixture_locks(tmp_path, npm_document=npm_document)

    document = build_sbom(uv_path, npm_path)
    component = component_by_purl(document, "pkg:npm/demo-package@2.0.0")
    dependency = next(item for item in document["dependencies"] if item["ref"] == component["bom-ref"])
    assert dependency["dependsOn"] == []


def test_missing_required_peer_fails_closed(tmp_path: Path) -> None:
    npm_document = npm_lock_document()
    npm_document["packages"]["node_modules/demo-package"]["peerDependencies"] = {
        "required-peer": "^1.0.0"
    }
    uv_path, npm_path = write_fixture_locks(tmp_path, npm_document=npm_document)

    with pytest.raises(SbomError, match="cannot be resolved"):
        render_sbom(uv_path, npm_path)


def test_malformed_npm_boolean_fails_closed(tmp_path: Path) -> None:
    npm_document = npm_lock_document()
    npm_document["packages"]["node_modules/demo-package"]["dev"] = "true"
    uv_path, npm_path = write_fixture_locks(tmp_path, npm_document=npm_document)

    with pytest.raises(SbomError, match="must be a boolean"):
        render_sbom(uv_path, npm_path)


def test_exclusive_create_and_check_never_overwrite(tmp_path: Path) -> None:
    uv_path, npm_path = write_fixture_locks(tmp_path / "input")
    output = tmp_path / "artifact" / "sbom.cdx.json"

    export_sbom(uv_path, npm_path, output)
    expected = output.read_bytes()
    initial_mtime = output.stat().st_mtime_ns
    with pytest.raises(SbomError, match="refusing to overwrite"):
        export_sbom(uv_path, npm_path, output)

    export_sbom(uv_path, npm_path, output, check=True)
    assert output.read_bytes() == expected
    assert output.stat().st_mtime_ns == initial_mtime

    output.write_bytes(expected + b" ")
    drifted = output.read_bytes()
    with pytest.raises(SbomError, match="stale or non-canonical"):
        export_sbom(uv_path, npm_path, output, check=True)
    assert output.read_bytes() == drifted


def test_cli_check_reports_drift_without_writing(tmp_path: Path) -> None:
    uv_path, npm_path = write_fixture_locks(tmp_path / "input")
    output = tmp_path / "sbom.cdx.json"

    assert main(["--uv-lock", str(uv_path), "--npm-lock", str(npm_path), "--output", str(output)]) == 0
    assert main(
        ["--uv-lock", str(uv_path), "--npm-lock", str(npm_path), "--output", str(output), "--check"]
    ) == 0
    output.write_text("{}\n", encoding="utf-8")
    before = output.read_bytes()
    assert main(
        ["--uv-lock", str(uv_path), "--npm-lock", str(npm_path), "--output", str(output), "--check"]
    ) == 1
    assert output.read_bytes() == before


def test_committed_sbom_is_current_and_canonical() -> None:
    assert SBOM_ARTIFACT.read_bytes() == render_sbom(UV_LOCK, NPM_LOCK)
