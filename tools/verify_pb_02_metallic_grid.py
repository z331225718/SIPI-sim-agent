"""Fail-closed verifier for the additive PB-02 metallic-grid checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/pb-02-metallic-grid.v1.yaml"
SOURCE_MAP = ROOT / "docs/baselines/pb-02-metallic-grid-source-map.v1.yaml"
EXPECTED_SCHEMA = "sipi.pb-02-metallic-grid.v1"
EXPECTED_COMMIT = "7c27d24d0080f274405863724627ffad8bb90bec"
EXPECTED_TREE = "8de8205c66989ebfc28df334bd6bcbe33067a85e"
EXPECTED_ARCHIVE = "6d526e98429c23380a9987830331cf2d3421e05b54f3bdbacac95ee7a834f074"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
UPSTREAM_ARCHIVE = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PATH_LEAK = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp)/|\\(?:Users|Temp)\\)")
ARCHIVE_FORMAT = "tar"
ARCHIVE_COMMAND = "git -c core.autocrlf=false archive --format=tar <commit>"
DEFAULT_UPSTREAM = ROOT.parent / "Py-bert-agent"
EXPECTED_SOURCE_MAP_PATH = "docs/baselines/pb-02-metallic-grid-source-map.v1.yaml"
EXPECTED_AUDIT_PATH = "docs/baselines/audits/2026-08-24-pb-02-metallic-grid.v1.md"
EXPECTED_UPSTREAM_FILES = [
    {
        "path": "src/pybert/pybert.py",
        "blob_sha1": "1af665c4595fff1ff5fb30341fe063bd10e5cd89",
        "sha256": "a2fdd33db845db09155e323a26465688d759e77ed2bcc4a23cb7a5298d5457dd",
        "role": "_get_f uses NumPy arange stop-exclusive grid",
    },
    {
        "path": "src/pybert/utility/channel.py",
        "blob_sha1": "5526c1c4d46a98e63e5600c5f5bb90cb96db4f96",
        "sha256": "0c49010fc0b69eea0982eef6296d250fa558077ce4dcdc1d914ef37360301181",
        "role": "metallic-line gamma checkpoint",
    },
]
EXPECTED_LANE_FILES = [
    {
        "source_path": "native/pybert-core/src/input.rs",
        "target_path": "crates/sipi-pybert-direct/src/input.rs",
        "target_blob_sha1": "c7820beb25c051b8d3c43652c83d906cff185728",
        "target_sha256": "25a0af0d0442f9d96e1488518404254ea058468b48b8294e13afcc878a3f1947",
        "role": "metallic_grid_input",
        "classification": "adapted",
    },
    {
        "source_path": "native/pybert-core/src/simulation.rs",
        "target_path": "crates/sipi-pybert-direct/src/simulation.rs",
        "target_blob_sha1": "21dc15d3e330c1f9a246a91494a88fa53a35281a",
        "target_sha256": "74475c5832413ffdb4bf48b0b06a1532e6b1dd85de30f690cf013a74deea5e39",
        "role": "metallic_grid_implementation",
        "classification": "adapted",
    },
    {
        "source_path": "native/pybert-core/tests/native_branch_matrix.rs",
        "target_path": "crates/sipi-pybert-direct/tests/native_branch_matrix.rs",
        "target_blob_sha1": "34739b906671d5664bf5ff56c0041a9e649ea5b6",
        "target_sha256": "aeba651902ba002c71661d7ceec9507be7bfa2db3ec7fce3804d86e7e366fef5",
        "role": "metallic_grid_external_checkpoint",
        "classification": "additive_test",
    },
]
EXPECTED_HARNESS_PATHS = {"tools/verify_pb_02_metallic_grid.py", "tools/test_verify_pb_02_metallic_grid.py"}
EXPECTED_SOURCE_FILES = ["src/pybert/pybert.py", "src/pybert/utility/channel.py"]
EXPECTED_INPUT_PARAMETERS = {
    "sample_interval_s": 1.0e-12,
    "length_m": 0.05,
    "skin_effect_resistance_ohm_per_m": 1.452,
    "crossover_angular_frequency_rad_per_s": 10000000.0,
    "dc_resistance_ohm_per_m": 0.1876,
    "characteristic_impedance_ohm": 100.0,
    "propagation_velocity_m_per_s": 201000000.0,
    "loss_tangent": 0.02,
    "source_impedance_ohm": 50.0,
    "source_capacitance_f": 5.0e-13,
    "load_impedance_ohm": 100.0,
    "load_capacitance_f": 5.0e-13,
    "apply_raised_cosine_window": True,
    "frequency_step_hz": 3000000000.0,
    "frequency_max_hz": 10000000000.0,
    "impulse_length_s": 1.0e-9,
}
EXPECTED_RAW_PARAMETERS = {
    "length_m": 0.05,
    "skin_effect_resistance_ohm_per_m": 1.452,
    "crossover_angular_frequency_rad_per_s": 10000000.0,
    "dc_resistance_ohm_per_m": 0.1876,
    "characteristic_impedance_ohm": 100.0,
    "propagation_velocity_m_per_s": 201000000.0,
    "loss_tangent": 0.02,
    "step_hz": 3000000000.0,
    "requested_max_hz": 10000000000.0,
}
EXPECTED_CLAIMS = {
    "source_binding": True,
    "numeric_checkpoint": True,
    "clean_archive_replay": False,
    "global_payload_parity": False,
    "global_row_closed": False,
    "promotion": False,
    "external_reference_required": True,
}
EXPECTED_NON_CLAIMS = [
    "This is a scoped metallic-grid/source/numeric checkpoint, not PB-02 global parity evidence.",
    "No two-fresh replay or aggregate is claimed by this successor.",
    "PB-03, PB-04, and PB-05 remain outside this successor.",
]


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def check_repo_path(blockers: list[str], value: Any, expected: str, label: str) -> None:
    valid = (
        isinstance(value, str)
        and value == expected
        and not Path(value).is_absolute()
        and not PATH_LEAK.search(value)
        and "\\" not in value
        and ".." not in PurePosixPath(value).parts
    )
    check(blockers, valid, f"{label} path drift")


def git_blob(root: Path, commit: str, path: str) -> tuple[str | None, str | None]:
    try:
        blob = subprocess.run(["git", "-C", str(root), "rev-parse", f"{commit}:{path}"], check=True, capture_output=True, text=True).stdout.strip()
        payload = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path}"], check=True, capture_output=True).stdout
        return blob, sha256(payload)
    except (OSError, subprocess.CalledProcessError):
        return None, None


def git_tree(root: Path, commit: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", f"{commit}^{{tree}}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def git_archive_sha256(root: Path, commit: str) -> str | None:
    try:
        archive = subprocess.run(
            ["git", "-C", str(root), "-c", "core.autocrlf=false", "archive", "--format=tar", commit],
            check=True,
            capture_output=True,
        ).stdout
        return sha256(archive)
    except (OSError, subprocess.CalledProcessError):
        return None


def verify_archive(
    blockers: list[str],
    binding: dict[str, Any],
    root: Path,
    commit: str,
    tree: str,
    expected_archive: str,
    label: str,
) -> None:
    archive = binding.get("archive") or {}
    check(blockers, archive.get("format") == ARCHIVE_FORMAT, f"{label} archive format drift")
    check(blockers, archive.get("command") == ARCHIVE_COMMAND, f"{label} archive command drift")
    check(blockers, git_tree(root, commit) == tree, f"{label} tree bytes drift")
    actual_archive = git_archive_sha256(root, commit)
    check(blockers, actual_archive == expected_archive, f"{label} archive bytes drift")


def verify_source_map(document: dict[str, Any], blockers: list[str], upstream: Path) -> None:
    check(
        blockers,
        set(document) == {"schema", "status", "candidate", "upstream", "lane_files", "harness_files"},
        "source-map key set drift",
    )
    check(blockers, document.get("schema") == "sipi.pb-02-metallic-grid-source-map.v1", "source-map schema drift")
    check(blockers, document.get("status") == "scoped_source_binding_open", "source-map status drift")
    candidate = document.get("candidate") or {}
    check(blockers, candidate.get("commit") == EXPECTED_COMMIT, "source-map candidate commit drift")
    check(blockers, candidate.get("tree") == EXPECTED_TREE, "source-map candidate tree drift")
    check(blockers, candidate.get("archive_sha256") == EXPECTED_ARCHIVE, "source-map candidate archive drift")
    verify_archive(blockers, candidate, ROOT, EXPECTED_COMMIT, EXPECTED_TREE, EXPECTED_ARCHIVE, "source-map candidate")
    upstream_binding = document.get("upstream") or {}
    check(blockers, upstream_binding.get("commit") == UPSTREAM_COMMIT, "source-map upstream commit drift")
    check(blockers, upstream_binding.get("tree") == UPSTREAM_TREE, "source-map upstream tree drift")
    check(blockers, upstream_binding.get("archive_sha256") == UPSTREAM_ARCHIVE, "source-map upstream archive drift")
    check(blockers, upstream_binding.get("repository") == "pybert", "source-map upstream repository drift")
    verify_archive(blockers, upstream_binding, upstream, UPSTREAM_COMMIT, UPSTREAM_TREE, UPSTREAM_ARCHIVE, "source-map upstream")
    check(blockers, upstream_binding.get("files") == EXPECTED_UPSTREAM_FILES, "source-map upstream tuple drift")
    for item in upstream_binding.get("files", []):
        check_repo_path(blockers, item.get("path"), item.get("path", ""), f"upstream source {item.get('path')}")
        blob, digest = git_blob(upstream, UPSTREAM_COMMIT, item.get("path", ""))
        check(blockers, blob == item.get("blob_sha1"), f"upstream blob drift: {item.get('path')}")
        check(blockers, digest == item.get("sha256"), f"upstream sha256 drift: {item.get('path')}")
    for item in document.get("lane_files", []):
        blob, digest = git_blob(ROOT, EXPECTED_COMMIT, item.get("target_path", ""))
        check(blockers, blob == item.get("target_blob_sha1"), f"candidate blob drift: {item.get('target_path')}")
        check(blockers, digest == item.get("target_sha256"), f"candidate sha256 drift: {item.get('target_path')}")
        check_repo_path(blockers, item.get("source_path"), item.get("source_path", ""), f"lane source {item.get('source_path')}")
        check_repo_path(blockers, item.get("target_path"), item.get("target_path", ""), f"lane target {item.get('target_path')}")
        check(blockers, item.get("classification") not in {"verbatim", "global"}, "source-map forbidden classification")
    check(blockers, document.get("lane_files") == EXPECTED_LANE_FILES, "source-map lane tuple drift")
    check(blockers, {item.get("path") for item in document.get("harness_files", [])} == EXPECTED_HARNESS_PATHS, "source-map harness set drift")
    for item in document.get("harness_files", []):
        path = Path(item.get("path", ""))
        check_repo_path(blockers, item.get("path"), item.get("path", ""), "source-map harness")
        try:
            check(blockers, sha256((ROOT / path).read_bytes()) == item.get("sha256"), f"harness sha256 drift: {path}")
        except OSError:
            blockers.append(f"harness missing: {path}")


def verify(document: dict[str, Any], root: Path = ROOT, upstream: Path | None = None) -> dict[str, Any]:
    if upstream is None:
        upstream = DEFAULT_UPSTREAM
    blockers: list[str] = []
    check(
        blockers,
        set(document)
        == {
            "schema",
            "status",
            "row",
            "workflow",
            "candidate",
            "upstream",
            "source_map",
            "audit",
            "checkpoint",
            "claims",
            "non_claims",
        },
        "manifest key set drift",
    )
    check(blockers, document.get("schema") == EXPECTED_SCHEMA, "manifest schema drift")
    check(blockers, document.get("status") == "scoped_numeric_checkpoint_open", "manifest status drift")
    check(blockers, document.get("row") == "PB-02" and document.get("workflow") == "sim-native", "scope drift")
    candidate = document.get("candidate") or {}
    check(blockers, candidate.get("commit") == EXPECTED_COMMIT, "candidate commit drift")
    check(blockers, candidate.get("tree") == EXPECTED_TREE, "candidate tree drift")
    check(blockers, candidate.get("archive_sha256") == EXPECTED_ARCHIVE, "candidate archive drift")
    verify_archive(blockers, candidate, root, EXPECTED_COMMIT, EXPECTED_TREE, EXPECTED_ARCHIVE, "candidate")
    source = document.get("upstream") or {}
    check(blockers, source.get("commit") == UPSTREAM_COMMIT, "upstream commit drift")
    check(blockers, source.get("tree") == UPSTREAM_TREE, "upstream tree drift")
    check(blockers, source.get("archive_sha256") == UPSTREAM_ARCHIVE, "upstream archive drift")
    verify_archive(blockers, source, upstream, UPSTREAM_COMMIT, UPSTREAM_TREE, UPSTREAM_ARCHIVE, "upstream")
    source_binding = document.get("source_map") or {}
    check_repo_path(blockers, source_binding.get("path"), EXPECTED_SOURCE_MAP_PATH, "source-map")
    source_map_path = root / source_binding.get("path", "")
    try:
        source_map_bytes = source_map_path.read_bytes()
        source_map = yaml.safe_load(source_map_bytes)
        check(blockers, sha256(source_map_bytes) == source_binding.get("sha256"), "source-map hash drift")
        if isinstance(source_map, dict):
            verify_source_map(source_map, blockers, upstream)
    except (OSError, yaml.YAMLError) as error:
        blockers.append(f"source-map load failure: {error}")
    checkpoint = document.get("checkpoint") or {}
    check(
        blockers,
        set(checkpoint) == {"oracle", "source_files", "grid_cases", "input_parameters", "metallic_raw_re"},
        "checkpoint key set drift",
    )
    check(blockers, checkpoint.get("oracle") == "pinned_external_python", "checkpoint oracle drift")
    check(blockers, checkpoint.get("source_files") == EXPECTED_SOURCE_FILES, "checkpoint source file drift")
    for path in checkpoint.get("source_files", []):
        check_repo_path(blockers, path, path, f"checkpoint source {path}")
    check(blockers, checkpoint.get("input_parameters") == EXPECTED_INPUT_PARAMETERS, "checkpoint input parameter drift")
    ordinary = ((checkpoint.get("grid_cases") or {}).get("ordinary") or {})
    near = ((checkpoint.get("grid_cases") or {}).get("near_integral_stop") or {})
    check(blockers, set(checkpoint.get("grid_cases") or {}) == {"ordinary", "near_integral_stop"}, "grid case key set drift")
    check(
        blockers,
        ordinary
        == {
            "length_m": 0.05,
            "step_hz": 3.0e9,
            "requested_max_hz": 1.0e10,
            "impulse_length_s": 1.0e-9,
            "expected_grid_hz": [0.0, 3.0e9, 6.0e9, 9.0e9, 12.0e9],
        },
        "ordinary grid control drift",
    )
    check(
        blockers,
        near
        == {
            "length_m": 0.05,
            "step_hz": 3.0e9,
            "requested_max_hz": 3000000000.0000005,
            "impulse_length_s": 1.0e-9,
            "expected_grid_hz": [0.0, 3.0e9],
        },
        "near-integral grid control drift",
    )
    check(blockers, ordinary.get("expected_grid_hz") == [0.0, 3.0e9, 6.0e9, 9.0e9, 12.0e9], "ordinary grid checkpoint drift")
    check(blockers, near.get("expected_grid_hz") == [0.0, 3.0e9], "near-integral grid checkpoint drift")
    raw = checkpoint.get("metallic_raw_re") or {}
    check(blockers, set(raw) == {"parameters", "values", "tolerance"}, "raw checkpoint key set drift")
    check(blockers, raw.get("parameters") == EXPECTED_RAW_PARAMETERS, "raw checkpoint parameter drift")
    check(blockers, raw.get("values") == [0.9999999999998559, -0.21346019040916128, -0.7836205535132831, 0.6107703954011926, 0.3676296985687409], "metallic raw checkpoint drift")
    check(blockers, raw.get("tolerance") == 1.0e-12, "checkpoint tolerance drift")
    claims = document.get("claims") or {}
    check(blockers, claims == EXPECTED_CLAIMS, "claims key/value drift")
    check(blockers, document.get("non_claims") == EXPECTED_NON_CLAIMS, "non-claims drift")
    audit = document.get("audit") or {}
    check_repo_path(blockers, audit.get("path"), EXPECTED_AUDIT_PATH, "audit")
    audit_path = root / audit.get("path", "")
    try:
        audit_bytes = audit_path.read_bytes()
        check(blockers, sha256(audit_bytes) == audit.get("sha256"), "audit hash drift")
        check(blockers, PATH_LEAK.search(audit_bytes.decode("utf-8", errors="replace")) is None, "audit absolute path leak")
    except OSError as error:
        blockers.append(f"audit load failure: {error}")
    check(blockers, PATH_LEAK.search(json.dumps(document, ensure_ascii=True)) is None, "absolute path leak")
    try:
        check(blockers, PATH_LEAK.search(source_map_bytes.decode("utf-8", errors="replace")) is None, "source-map absolute path leak")
    except UnboundLocalError:
        pass
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--upstream", type=Path, default=None)
    args = parser.parse_args()
    result = verify(yaml.safe_load(args.evidence.read_text(encoding="utf-8")), ROOT, args.upstream)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
