"""Run PB-03 candidate sim-rust against the pinned Python backend corpus.

The candidate and the Python oracle are materialized independently from their
immutable repositories. Corpus inputs are content-addressed test inputs, not
source overlays. No ``sim-rust`` command is used for the oracle side.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from pb_03_replay_common import (
    DEFAULT_UPSTREAM,
    ROOT,
    UPSTREAM_COMMIT,
    UPSTREAM_TREE,
    _binary,
    archive_repo,
    build_summary,
    canonical,
    resolve_toolchain,
    run_command,
    sha256,
)


CORPUS_PATH = ROOT / "docs/baselines/pb-03-python-oracle-corpus-d3154093.v1.json"
ORACLE_HELPER = ROOT / "tools/pb_03_python_oracle.py"
SCALAR_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*):.*$", re.MULTILINE)


def digest_file(path: Path) -> str:
    return sha256(path.read_bytes())


def materialize_harness_snapshot(payload: bytes, root: Path, name: str) -> Path:
    snapshot = root / "harness" / name
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(payload)
    if digest_file(snapshot) != sha256(payload):
        raise RuntimeError("harness snapshot digest changed during materialization")
    return snapshot


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def replace_or_append(text: str, overrides: dict[str, Any]) -> str:
    result = text
    for key, value in overrides.items():
        encoded = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value).lower() if isinstance(value, bool) else str(value)
        pattern = re.compile(rf"(?m)^(?P<indent>\s*){re.escape(key)}:.*$")
        replacement = rf"\g<indent>{key}: {encoded}"
        result, count = pattern.subn(replacement, result, count=1)
        if count == 0:
            if not result.endswith("\n"):
                result += "\n"
            result += f"{key}: {encoded}\n"
    return result


def write_case(root: Path, base: bytes, case: dict[str, Any], files: dict[str, str]) -> Path:
    case_root = root / "pb03-oracle-corpus" / str(case["id"])
    case_root.mkdir(parents=True, exist_ok=True)
    config = case_root / "config.yaml"
    config.write_text(replace_or_append(base.decode("utf-8"), case.get("overrides", {})), encoding="utf-8")
    for name, content in files.items():
        (case_root / name).write_text(content, encoding="utf-8", newline="\n")
    return config


def array_summary(array: np.ndarray) -> dict[str, Any]:
    value = np.asarray(array, dtype=np.float64)
    return {
        "dtype": "float64",
        "shape": list(value.shape),
        "count": int(value.size),
        "f64_sha256": sha256(np.ascontiguousarray(value).tobytes()),
    }


def read_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {name: np.asarray(archive[name], dtype=np.float64) for name in archive.files}


def compare_payload(candidate_path: Path, oracle_path: Path, fields: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    try:
        candidate = read_npz(candidate_path)
        oracle = read_npz(oracle_path)
    except (OSError, ValueError, TypeError) as error:
        # Keep the immutable report portable.  The process hashes and the
        # per-side exit codes retain evidence without leaking a temp root.
        return [], [f"NPZ load failed: {type(error).__name__}"]
    comparisons: list[dict[str, Any]] = []
    for name in fields:
        left = candidate.get(name)
        right = oracle.get(name)
        if left is None or right is None:
            blockers.append(f"missing oracle payload field: {name}")
            continue
        if left.shape != right.shape:
            comparisons.append({"name": name, "candidate": array_summary(left), "oracle": array_summary(right), "passed": False, "reason": "shape_mismatch"})
            blockers.append(f"payload shape mismatch: {name}")
            continue
        delta = np.abs(left - right)
        max_abs = float(np.max(delta)) if delta.size else 0.0
        scale = float(np.max(np.abs(right))) if right.size else 0.0
        tolerance = 1.0e-6 + 1.0e-6 * scale
        passed = bool(np.all(np.isfinite(left)) and np.all(np.isfinite(right)) and max_abs <= tolerance)
        comparisons.append({
            "name": name,
            "candidate": array_summary(left),
            "oracle": array_summary(right),
            "max_abs": max_abs,
            "scale": scale,
            "tolerance": tolerance,
            "passed": passed,
        })
        if not passed:
            blockers.append(f"payload mismatch: {name}")
    return comparisons, blockers


def metadata_summary(path: Path) -> dict[str, Any]:
    try:
        value = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"schema": None}
    if not isinstance(value, dict):
        return {"schema": None}
    diagnostics = value.get("diagnostics")
    selected_diagnostics = {}
    if isinstance(diagnostics, dict):
        for key in ("backend", "engine_selection", "comparison"):
            if key in diagnostics:
                selected_diagnostics[key] = diagnostics[key]
    return {
        "schema": value.get("schema"),
        "backend": value.get("backend"),
        "source_command": value.get("source_command"),
        "array_names": sorted(value.get("source_fields", {}).keys()) if isinstance(value.get("source_fields"), dict) else None,
        "diagnostics": selected_diagnostics,
        "metrics": value.get("metrics") if isinstance(value.get("metrics"), dict) else None,
    }


def run_matrix(
    *,
    candidate_repo: Path,
    upstream_repo: Path,
    output: Path,
    run_id: str,
    candidate_commit: str,
    candidate_tree: str,
    candidate_archive_sha256: str,
    timeout: int,
) -> dict[str, Any]:
    corpus_payload = CORPUS_PATH.read_bytes()
    oracle_helper_payload = ORACLE_HELPER.read_bytes()
    oracle_helper_sha256 = sha256(oracle_helper_payload)
    toolchain_report, tool_paths = resolve_toolchain(timeout)
    corpus = json.loads(corpus_payload.decode("utf-8"))
    base_fixture = str(corpus["base_fixture"])
    cases = corpus["cases"]
    files = corpus.get("files", {})
    if not isinstance(cases, list) or not isinstance(files, dict):
        raise ValueError("invalid PB-03 oracle corpus")
    with tempfile.TemporaryDirectory(prefix="sipi-pb03-python-oracle-") as temporary:
        work = Path(temporary)
        candidate_root = work / "candidate"
        upstream_root = work / "upstream"
        candidate_identity = archive_repo(candidate_repo, candidate_commit, candidate_root)
        if candidate_identity.get("tree") != candidate_tree or candidate_identity.get("archive_sha256") != candidate_archive_sha256:
            raise RuntimeError("candidate archive identity does not match the requested prep commit")
        upstream_identity = archive_repo(upstream_repo, UPSTREAM_COMMIT, upstream_root)
        oracle_helper = materialize_harness_snapshot(oracle_helper_payload, work, ORACLE_HELPER.name)
        candidate_base = candidate_root / base_fixture
        if not candidate_base.is_file():
            raise RuntimeError("base fixture is absent from candidate archive")
        base = candidate_base.read_bytes()
        build_result = run_command(
            ["cargo", "build", "--manifest-path", str(candidate_root / "crates/sipi-pybert-direct/Cargo.toml"), "--release", "--locked"],
            candidate_root,
            timeout,
            tool_paths,
        )
        binary = _binary(candidate_root / "crates" / "sipi-pybert-direct" / "target")
        build = build_summary(build_result, binary)
        corpus_cases: list[dict[str, Any]] = []
        for case in cases:
            case_id = str(case["id"])
            candidate_config = write_case(candidate_root, base, case, files)
            upstream_config = write_case(upstream_root, base, case, files)
            candidate_output = work / "candidate-output" / case_id
            oracle_output = work / "oracle-output" / case_id
            if binary.is_file():
                candidate_process = run_command(
                    [str(binary), "sim-rust", str(candidate_config), "--output-dir", str(candidate_output)],
                    candidate_root,
                    timeout,
                    tool_paths,
                )
            else:
                candidate_process = {"exit_code": None, "skipped": True}
            oracle_process = run_command(
                ["uv", "run", "--project", str(upstream_root), "--frozen", "python", str(oracle_helper), str(upstream_config), "--output-dir", str(oracle_output)],
                upstream_config.parent,
                timeout,
                tool_paths,
            )
            candidate_meta = metadata_summary(candidate_output)
            oracle_meta = metadata_summary(oracle_output)
            expected_fields = [str(item) for item in case.get("expected_fields", [])]
            comparisons, payload_blockers = compare_payload(candidate_output / "arrays.npz", oracle_output / "arrays.npz", expected_fields)
            blockers = list(payload_blockers)
            if candidate_process.get("exit_code") != 0:
                blockers.append("candidate sim-rust process failed")
            if oracle_process.get("exit_code") != 0:
                blockers.append("independent Python oracle process failed")
            if candidate_meta.get("schema") != "pybert.native-cli-result.v1":
                blockers.append("candidate artifact schema mismatch")
            if oracle_meta.get("schema") != "pybert.python-oracle-result.v1":
                blockers.append("Python oracle artifact schema mismatch")
            corpus_cases.append({
                "id": case_id,
                "expected_fields": expected_fields,
                "candidate_process": candidate_process,
                "oracle_process": oracle_process,
                "candidate": candidate_meta,
                "oracle": oracle_meta,
                "payload": {
                    "fields": comparisons,
                    "equal": not payload_blockers,
                    "compared_field_count": len(comparisons),
                },
                "status": "passed" if not blockers else "blocked",
                "blockers": blockers,
            })
        result = {
            "schema": "sipi.pb-03-python-oracle-matrix-replay.v1",
            "version": 1,
            "row": "PB-03",
            "status": "passed" if all(case["status"] == "passed" for case in corpus_cases) else "blocked",
            "source_mode": "git_archive_at_candidate_prep_commit_plus_content_addressed_input_corpus_and_harness_snapshot",
            "run_id": run_id,
            "fresh_run_nonce": uuid.uuid4().hex,
            "candidate": candidate_identity,
            "upstream": upstream_identity,
            "fixture": {"path": base_fixture, "archive_present": True, "sha256": sha256(base), "source": "candidate_archive", "archive_source_sha256": sha256(base)},
            "corpus": {"path": relative(CORPUS_PATH), "sha256": sha256(corpus_payload), "case_count": len(corpus_cases), "file_names": sorted(files)},
            "harness": {
                "runner": {"path": relative(Path(__file__)), "sha256": digest_file(Path(__file__))},
                "python_oracle": {"path": relative(ORACLE_HELPER), "sha256": oracle_helper_sha256, "snapshot": "candidate_prep_archive_harness_snapshot"},
            },
            "build": build,
            "toolchain": toolchain_report,
            "cases": corpus_cases,
            "claims": {
                "independent_python_payload_oracle": True,
                "portable_cases_only": True,
                "global_branch_parity": False,
                "promotion": False,
            },
            "external_blockers": [
                {"branch": "legacy.external.ami_ibis_ts4_getwave", "reason": "host-owned DLL/model/service remains outside the portable corpus"},
                {"branch": "legacy.config.exact_pybert_data_class_pickle", "reason": "the oracle executes the class but the Rust artifact contract remains data-only"},
            ],
            "non_claims": [
                "The Python process is independent of the Rust candidate and is not sim-rust.",
                "Case payload parity does not close untested PyBERT branches or external model branches.",
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_matrix(
        candidate_repo=args.candidate_repo.resolve(),
        upstream_repo=args.upstream_repo.resolve(),
        output=args.output.resolve(),
        run_id=args.run_id,
        candidate_commit=args.candidate_commit,
        candidate_tree=args.candidate_tree,
        candidate_archive_sha256=args.candidate_archive_sha256,
        timeout=args.timeout,
    )
    print(json.dumps({"status": result["status"], "run_id": result["run_id"], "case_count": len(result["cases"])}, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
