"""Fail-closed two-stage gate for the PB-03 eye/contour follow-up."""

from __future__ import annotations

import argparse
import copy
import functools
import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = "docs/baselines/pb-03-eye-contour-gap.v1.yaml"
AUDIT_PATH = "docs/baselines/audits/2026-08-27-pb-03-eye-contour-gap.md"
VERIFIER_PATH = "tools/verify_pb_03_eye_contour_gap.py"
MUTATION_TEST_PATH = "tools/test_verify_pb_03_eye_contour_gap.py"
SCHEMA = "sipi.pb-03.eye-contour-gap.v1"

CANDIDATE_COMMIT = "e18b09917c7c0dbd79a1f1a9fedd22104f6f1c1e"
CANDIDATE_TREE = "505aa18797c4509012185f5ec89771d7138c027c"
CANDIDATE_ARCHIVE = {
    "format": "git-archive-tar",
    "bytes": 53094400,
    "sha256": "db9402a466e84ab006bd53046975a0fa37485cd717517a12a6aa4ca747c47072",
}

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HOST_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/Users/|/home/|\\\\Users\\)")

PRODUCTION_FILES = [
    {
        "path": "crates/sipi-pybert-direct/src/legacy_runtime.rs",
        "blob": "7c29dff4fda9b673fe9477bef6792600630b38fe",
        "bytes": 132018,
        "sha256": "42c4c4398aef9608525ec0a9ce4428a734df018de96f1a11c6980924385596cb",
    },
    {
        "path": "crates/sipi-pybert-direct/src/workflows.rs",
        "blob": "b28853f0643ff317b4e55e841b75152bb1d247fe",
        "bytes": 64900,
        "sha256": "7c7ee604b1073a212a96020dc22b786a05a72ab3e96b5ff534e4965fea30878b",
    },
    {
        "path": "crates/sipi-pybert-direct/tests/pb03_payload.rs",
        "blob": "5e058fe23cf73cc2db59261353dfb38088a8c1bf",
        "bytes": 2812,
        "sha256": "e13fd59211436b448b65aebdb555d813a28368765decc715f2c985c02bc35cea",
    },
    {
        "path": "crates/sipi-pybert-direct/SOURCE-MAP-PB03-PAYLOAD.md",
        "blob": "da309ffbe1b5fb06b0e6bfd716bf0040c6dd701f",
        "bytes": 6188,
        "sha256": "b48b77966dd1b9dc999ffe5a74c3bde964018a583e42788db30b018faa6f8066",
    },
    {
        "path": "crates/sipi-pybert-direct/NOTICE-PYBERT-PB03-PAYLOAD.md",
        "blob": "23f996b4fd2ac68caedf74dcddba711d8f31f0f6",
        "bytes": 1311,
        "sha256": "a146cfa41cb8151bd26b610c04ab67548284b26d75ed9050a4dd39ec46263e2d",
    },
]

EYE_MATRIX_BLOCKERS = [
    "eye_chnl.npy",
    "eye_tx.npy",
    "eye_ctle.npy",
    "eye_dfe.npy",
    "eye_rx.npy",
    "native_eye_chnl.npy",
    "native_eye_tx.npy",
    "native_eye_ctle.npy",
    "native_eye_dfe.npy",
    "native_eye_rx.npy",
]

RESPONSE_HASH_BLOCKERS = [
    "chnl_H.npy",
    "chnl_trimmed_H.npy",
    "ctle_out_H.npy",
    "dfe_out_H.npy",
    "rx_out_H.npy",
    "tx_H.npy",
    "tx_out_H.npy",
]

EXPECTED_GATE_NORMALIZED = {
    "candidate_ancestor": CANDIDATE_COMMIT,
    "commit": "<gate_commit>",
    "tree": "<gate_tree>",
    "files": {
        "verifier": {
            "path": VERIFIER_PATH,
            "blob": "<verifier_blob>",
            "bytes": "<verifier_bytes>",
            "sha256": "<verifier_sha256>",
        },
        "mutation_test": {
            "path": MUTATION_TEST_PATH,
            "blob": "<mutation_test_blob>",
            "bytes": "<mutation_test_bytes>",
            "sha256": "<mutation_test_sha256>",
        },
    },
}

EXPECTED_MANIFEST_NORMALIZED = {
    "schema": SCHEMA,
    "version": 1,
    "row": "PB-03",
    "status": "scoped_contour_cardinality_bound_eye_response_blocked",
    "scope": {
        "evidence_mode": "candidate_archive_and_production_source_binding",
        "clean_external_replay": False,
        "whole_payload_parity": False,
        "description": "Source-bound contour-cardinality follow-up; no external replay or whole-payload parity claim.",
    },
    "source": {
        "candidate": {
            "commit": CANDIDATE_COMMIT,
            "tree": CANDIDATE_TREE,
            "archive": CANDIDATE_ARCHIVE,
        }
    },
    "production_files": PRODUCTION_FILES,
    "payload": {
        "candidate_field_count": 142,
        "ordered_contour_ber_levels": [1.0e-5, 1.0e-4, 1.0e-3],
        "third_contour": {
            "members": ["eye_contour_2_x_ui.npy", "eye_contour_2_y_v.npy"],
            "x_count": 0,
            "y_count": 0,
            "empty": True,
        },
        "blocked": {
            "eye_matrices": EYE_MATRIX_BLOCKERS,
            "response_hash_drift": RESPONSE_HASH_BLOCKERS,
        },
    },
    "claims": {
        "candidate_source_bound": True,
        "candidate_field_count": True,
        "ordered_contour_levels": True,
        "third_contour_empty": True,
        "eye_matrix_parity": False,
        "response_hash_parity": False,
        "whole_payload_parity": False,
        "execution_provenance": False,
        "product_capability": False,
        "release_approval": False,
    },
    "non_claims": [
        "The ten eye/native-eye matrices remain blocked because no typed two-dimensional source exists.",
        "The seven response magnitudes remain pre-serialization telemetry hash drift.",
        "The source-bound 142-field observation is not an external replay or whole-payload parity result.",
        "This record is not execution provenance, product acceptance, or release approval.",
    ],
    "bindings": {
        "audit": {
            "path": AUDIT_PATH,
            "sha256": "<audit_sha256>",
        }
    },
    "git_gate": EXPECTED_GATE_NORMALIZED,
}

EXPECTED_AUDIT_NORMALIZED = """# PB-03 eye/contour source-bound audit

This record binds the reviewed Rust production candidate and its five PB-03
production files. It is not an external replay, execution provenance,
whole-payload parity, product acceptance, or release approval.

The candidate publishes 142 fields. Its ordered contour BER levels are
`[1e-5, 1e-4, 1e-3]`; the third contour coordinate arrays are present and
empty. Ten eye/native-eye matrices remain blocked because the typed Rust output
has no two-dimensional eye source. Seven response magnitudes remain blocked as
pre-serialization telemetry hash drift.

candidate_commit: e18b09917c7c0dbd79a1f1a9fedd22104f6f1c1e
candidate_tree: 505aa18797c4509012185f5ec89771d7138c027c
candidate_archive_sha256: db9402a466e84ab006bd53046975a0fa37485cd717517a12a6aa4ca747c47072
gate_commit: <bound>
gate_tree: <bound>
verifier_sha256: <bound>
mutation_test_sha256: <bound>
"""


class EyeContourGateError(ValueError):
    """A malformed, drifted, or incompletely bound PB-03 record."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_string(value: Any) -> bool:
    return type(value) is str and bool(value)


def _strict_int(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _exact_typed(actual: Any, expected: Any, path: str) -> None:
    if type(actual) is not type(expected):
        raise EyeContourGateError(f"{path} type drift")
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise EyeContourGateError(f"{path} keys drift")
        for key, expected_value in expected.items():
            _exact_typed(actual[key], expected_value, f"{path}.{key}")
        return
    if isinstance(expected, list):
        if len(actual) != len(expected):
            raise EyeContourGateError(f"{path} length drift")
        for index, (actual_value, expected_value) in enumerate(zip(actual, expected, strict=True)):
            _exact_typed(actual_value, expected_value, f"{path}[{index}]")
        return
    if actual != expected:
        raise EyeContourGateError(f"{path} value drift")


def _safe_repo_file(root: Path, relative: Any, label: str) -> Path:
    if not _strict_string(relative) or "\\" in relative:
        raise EyeContourGateError(f"{label} unsafe path")
    posix = PurePosixPath(relative)
    windows = PureWindowsPath(relative)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise EyeContourGateError(f"{label} unsafe path")
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise EyeContourGateError(f"{label} unsafe path")
    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
        if root.is_symlink() or getattr(root_metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise OSError("root link/reparse")
        candidate = root.joinpath(*posix.parts)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
        current = resolved_root
        for part in posix.parts:
            current /= part
            metadata = current.lstat()
            if current.is_symlink() or getattr(metadata, "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
            ):
                raise OSError("component link/reparse")
        metadata = candidate.stat()
        if not candidate.is_file() or metadata.st_nlink != 1:
            raise OSError("regular-file/nlink gate")
    except (OSError, ValueError) as error:
        raise EyeContourGateError(f"{label} containment/symlink/reparse/nlink gate") from error
    return candidate


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise EyeContourGateError("manifest parse failed") from error
    if not isinstance(value, dict):
        raise EyeContourGateError("manifest root type drift")
    return value


def _git(repo: Path, *arguments: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _git_exists(repo: Path, object_name: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", object_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def _git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


@functools.lru_cache(maxsize=8)
def _git_archive_receipt(repo_text: str, commit: str) -> dict[str, Any]:
    repo = Path(repo_text)
    payload = _git(repo, "archive", "--format=tar", commit, raw=True)
    if not isinstance(payload, bytes):
        raise EyeContourGateError("candidate archive payload type drift")
    return {"format": "git-archive-tar", "bytes": len(payload), "sha256": _sha256(payload)}


def _normalize_gate(gate: Any) -> dict[str, Any]:
    if type(gate) is not dict or set(gate) != {"candidate_ancestor", "commit", "tree", "files"}:
        raise EyeContourGateError("manifest.git_gate keys drift")
    if gate["candidate_ancestor"] != CANDIDATE_COMMIT:
        raise EyeContourGateError("manifest.git_gate candidate drift")
    for label in ("commit", "tree"):
        if type(gate[label]) is not str or HEX40.fullmatch(gate[label]) is None:
            raise EyeContourGateError(f"manifest.git_gate.{label} type/format drift")
    files = gate["files"]
    if type(files) is not dict or set(files) != {"verifier", "mutation_test"}:
        raise EyeContourGateError("manifest.git_gate.files keys drift")
    expected_paths = {"verifier": VERIFIER_PATH, "mutation_test": MUTATION_TEST_PATH}
    for label, expected_path in expected_paths.items():
        item = files[label]
        if type(item) is not dict or set(item) != {"path", "blob", "bytes", "sha256"}:
            raise EyeContourGateError(f"manifest.git_gate.files.{label} keys drift")
        if item["path"] != expected_path:
            raise EyeContourGateError(f"manifest.git_gate.files.{label} path drift")
        if type(item["blob"]) is not str or HEX40.fullmatch(item["blob"]) is None:
            raise EyeContourGateError(f"manifest.git_gate.files.{label} blob drift")
        if not _strict_int(item["bytes"], 1):
            raise EyeContourGateError(f"manifest.git_gate.files.{label} bytes type drift")
        if type(item["sha256"]) is not str or HEX64.fullmatch(item["sha256"]) is None:
            raise EyeContourGateError(f"manifest.git_gate.files.{label} sha256 drift")
    normalized = copy.deepcopy(gate)
    normalized["commit"] = "<gate_commit>"
    normalized["tree"] = "<gate_tree>"
    for label in ("verifier", "mutation_test"):
        normalized["files"][label]["blob"] = f"<{label}_blob>"
        normalized["files"][label]["bytes"] = f"<{label}_bytes>"
        normalized["files"][label]["sha256"] = f"<{label}_sha256>"
    _exact_typed(normalized, EXPECTED_GATE_NORMALIZED, "manifest.git_gate")
    return normalized


def _normalize_manifest(document: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(document)
    try:
        audit_sha256 = normalized["bindings"]["audit"]["sha256"]
        gate = normalized["git_gate"]
    except (KeyError, TypeError) as error:
        raise EyeContourGateError("manifest dynamic anchors missing") from error
    if type(audit_sha256) is not str or HEX64.fullmatch(audit_sha256) is None:
        raise EyeContourGateError("manifest.bindings.audit.sha256 type/format drift")
    normalized["bindings"]["audit"]["sha256"] = "<audit_sha256>"
    normalized["git_gate"] = _normalize_gate(gate)
    _exact_typed(normalized, EXPECTED_MANIFEST_NORMALIZED, "manifest")
    return document


def bound_audit(gate: dict[str, Any]) -> str:
    text = EXPECTED_AUDIT_NORMALIZED
    replacements = {
        "gate_commit: <bound>": f"gate_commit: {gate['commit']}",
        "gate_tree: <bound>": f"gate_tree: {gate['tree']}",
        "verifier_sha256: <bound>": f"verifier_sha256: {gate['files']['verifier']['sha256']}",
        "mutation_test_sha256: <bound>": f"mutation_test_sha256: {gate['files']['mutation_test']['sha256']}",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text


def future_manifest(gate: dict[str, Any], audit_sha256: str) -> dict[str, Any]:
    if type(audit_sha256) is not str or HEX64.fullmatch(audit_sha256) is None:
        raise EyeContourGateError("future audit sha256 type/format drift")
    document = copy.deepcopy(EXPECTED_MANIFEST_NORMALIZED)
    document["bindings"]["audit"]["sha256"] = audit_sha256
    document["git_gate"] = copy.deepcopy(gate)
    return document


def _gate_changed_paths(repo: Path, gate_commit: str) -> list[str]:
    output = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", f"{gate_commit}^", gate_commit)
    if not isinstance(output, str):
        raise EyeContourGateError("gate diff type drift")
    return [line for line in output.splitlines() if line]


def _verify_gate_commit(repo: Path, gate: dict[str, Any], require_record_descendant: bool) -> dict[str, Any]:
    gate_commit = gate["commit"]
    gate_tree = gate["tree"]
    try:
        if _git(repo, "rev-parse", gate_commit) != gate_commit:
            raise EyeContourGateError("git gate commit unavailable")
        if _git(repo, "rev-parse", f"{gate_commit}^{{tree}}") != gate_tree:
            raise EyeContourGateError("git gate tree drift")
        if _git(repo, "rev-parse", f"{gate_commit}^") != CANDIDATE_COMMIT:
            raise EyeContourGateError("git gate is not the direct candidate child")
        changed_paths = _gate_changed_paths(repo, gate_commit)
        if len(changed_paths) != 2 or sorted(changed_paths) != sorted(
            [VERIFIER_PATH, MUTATION_TEST_PATH]
        ):
            raise EyeContourGateError("git gate changed paths drift")
        for label, path in (("verifier", VERIFIER_PATH), ("mutation_test", MUTATION_TEST_PATH)):
            if _git_exists(repo, f"{gate_commit}^:{path}"):
                raise EyeContourGateError(f"git gate did not first introduce {path}")
            item = gate["files"][label]
            payload = _git(repo, "show", f"{gate_commit}:{path}", raw=True)
            if not isinstance(payload, bytes):
                raise EyeContourGateError(f"git gate {label} payload type drift")
            if (
                _git(repo, "rev-parse", f"{gate_commit}:{path}") != item["blob"]
                or len(payload) != item["bytes"]
                or _sha256(payload) != item["sha256"]
            ):
                raise EyeContourGateError(f"git gate {label} identity drift")
            current = _safe_repo_file(repo, path, f"current {label}")
            if current.read_bytes() != payload:
                raise EyeContourGateError(f"current {label} differs from git gate")
            if require_record_descendant and _git(repo, "show", f"HEAD:{path}", raw=True) != payload:
                raise EyeContourGateError(f"record {label} differs from git gate")
        for path in (MANIFEST_PATH, AUDIT_PATH):
            if _git_exists(repo, f"{gate_commit}:{path}"):
                raise EyeContourGateError(f"formal artifact existed at git gate: {path}")
        head = _git(repo, "rev-parse", "HEAD")
        if not isinstance(head, str):
            raise EyeContourGateError("record HEAD type drift")
        if require_record_descendant:
            if head == gate_commit or not _git_is_ancestor(repo, gate_commit, head):
                raise EyeContourGateError("record is not a strict git gate descendant")
        elif head != gate_commit:
            raise EyeContourGateError("clean gate checkout HEAD drift")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EyeContourGateError("git gate verification failed") from error
    return gate


def _verify_candidate(repo: Path, document: dict[str, Any]) -> None:
    try:
        if _git(repo, "rev-parse", CANDIDATE_COMMIT) != CANDIDATE_COMMIT:
            raise EyeContourGateError("candidate commit unavailable")
        if _git(repo, "rev-parse", f"{CANDIDATE_COMMIT}^{{tree}}") != CANDIDATE_TREE:
            raise EyeContourGateError("candidate tree drift")
        receipt = _git_archive_receipt(str(repo.resolve(strict=True)), CANDIDATE_COMMIT)
        _exact_typed(receipt, CANDIDATE_ARCHIVE, "candidate archive")
        _exact_typed(document["production_files"], PRODUCTION_FILES, "manifest.production_files")
        for item in PRODUCTION_FILES:
            path = item["path"]
            payload = _git(repo, "show", f"{CANDIDATE_COMMIT}:{path}", raw=True)
            if not isinstance(payload, bytes):
                raise EyeContourGateError(f"candidate production payload type drift: {path}")
            if (
                _git(repo, "rev-parse", f"{CANDIDATE_COMMIT}:{path}") != item["blob"]
                or len(payload) != item["bytes"]
                or _sha256(payload) != item["sha256"]
            ):
                raise EyeContourGateError(f"candidate production identity drift: {path}")
            current = _safe_repo_file(repo, path, f"production {path}")
            if current.read_bytes() != payload:
                raise EyeContourGateError(f"production worktree drift: {path}")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EyeContourGateError("candidate Git verification failed") from error


def _verify_audit(repo: Path, document: dict[str, Any], gate: dict[str, Any]) -> None:
    binding = document["bindings"]["audit"]
    audit = _safe_repo_file(repo, binding["path"], "audit")
    payload = audit.read_bytes()
    if _sha256(payload) != binding["sha256"]:
        raise EyeContourGateError("audit sha256 drift")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise EyeContourGateError("audit encoding drift") from error
    if text != bound_audit(gate):
        raise EyeContourGateError("audit coordinated content drift")
    if HOST_PATH.search(text):
        raise EyeContourGateError("audit contains a host path")


def _verify_record_artifacts(repo: Path) -> None:
    for path, label in ((MANIFEST_PATH, "manifest"), (AUDIT_PATH, "audit")):
        current = _safe_repo_file(repo, path, label)
        try:
            committed = _git(repo, "show", f"HEAD:{path}", raw=True)
        except subprocess.CalledProcessError as error:
            raise EyeContourGateError(f"{label} is not committed in record HEAD") from error
        if not isinstance(committed, bytes) or committed != current.read_bytes():
            raise EyeContourGateError(f"{label} differs from record HEAD")


def verify_gate_checkout_without_formal_artifacts(repo: Path) -> dict[str, Any]:
    manifest = repo / MANIFEST_PATH
    audit = repo / AUDIT_PATH
    if manifest.exists() or audit.exists():
        raise EyeContourGateError("formal artifacts are partially present")
    try:
        head = _git(repo, "rev-parse", "HEAD")
        tree = _git(repo, "rev-parse", "HEAD^{tree}")
        if not isinstance(head, str) or not isinstance(tree, str):
            raise EyeContourGateError("clean gate identity type drift")
        files: dict[str, Any] = {}
        for label, path in (("verifier", VERIFIER_PATH), ("mutation_test", MUTATION_TEST_PATH)):
            current = _safe_repo_file(repo, path, f"clean gate {label}")
            payload = _git(repo, "show", f"{head}:{path}", raw=True)
            if not isinstance(payload, bytes) or current.read_bytes() != payload:
                raise EyeContourGateError(f"clean gate {label} worktree drift")
            files[label] = {
                "path": path,
                "blob": _git(repo, "rev-parse", f"{head}:{path}"),
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
        gate = {
            "candidate_ancestor": CANDIDATE_COMMIT,
            "commit": head,
            "tree": tree,
            "files": files,
        }
        _normalize_gate(gate)
        _verify_gate_commit(repo, gate, require_record_descendant=False)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise EyeContourGateError("clean gate checkout verification failed") from error
    return {
        "valid": True,
        "status": "skipped_formal_artifacts_absent",
        "gate_commit": head,
        "gate_tree": tree,
    }


def verify(repo: Path = ROOT) -> dict[str, Any]:
    manifest_exists = (repo / MANIFEST_PATH).exists()
    audit_exists = (repo / AUDIT_PATH).exists()
    if not manifest_exists and not audit_exists:
        return verify_gate_checkout_without_formal_artifacts(repo)
    if manifest_exists != audit_exists:
        raise EyeContourGateError("formal artifacts are partially present")

    manifest_path = _safe_repo_file(repo, MANIFEST_PATH, "manifest")
    _safe_repo_file(repo, AUDIT_PATH, "audit")
    document = _load_yaml(manifest_path)
    _normalize_manifest(document)
    gate = document["git_gate"]
    _verify_gate_commit(repo, gate, require_record_descendant=True)
    _verify_record_artifacts(repo)
    _verify_candidate(repo, document)
    _verify_audit(repo, document, gate)
    if HOST_PATH.search(json.dumps(document, sort_keys=True)):
        raise EyeContourGateError("manifest contains a host path")
    return {
        "valid": True,
        "status": document["status"],
        "candidate_field_count": document["payload"]["candidate_field_count"],
        "ordered_contour_ber_levels": document["payload"]["ordered_contour_ber_levels"],
        "blocked_eye_matrices": len(document["payload"]["blocked"]["eye_matrices"]),
        "blocked_response_hashes": len(document["payload"]["blocked"]["response_hash_drift"]),
        "whole_payload_parity": document["claims"]["whole_payload_parity"],
        "gate_commit": gate["commit"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()
    try:
        print(json.dumps(verify(arguments.root), sort_keys=True))
        return 0
    except (EyeContourGateError, OSError, json.JSONDecodeError) as error:
        print(
            json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
