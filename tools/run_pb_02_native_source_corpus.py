"""Replay the source-owned PyBERT native simulation corpus from archives.

This is deliberately separate from the historical PB-01/PB-02 matrix.  That
matrix binds an older candidate and two SIPI-only configurations; this runner
binds only the successful configurations in the pinned native-core test plus
the additive-noise rejection that is reachable through the CLI.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import secrets
import shutil
from pathlib import Path
from typing import Any

try:  # pragma: no cover - direct execution uses the fallback
    from . import run_pb_01_02_portable_matrix as matrix
except ImportError:  # pragma: no cover
    import run_pb_01_02_portable_matrix as matrix


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.pb-02-pinned-native-source-corpus-replay.v1"
PINNED_UPSTREAM = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
PINNED_UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
SOURCE_TEST_PATH = "native/pybert-core/tests/simulation.rs"
SOURCE_TEST_BLOB = "dd06dc7f612ac32a2fd088611c27530ed25762b6"
FIXTURE = "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json"
NUMERIC_RTOL = 1.0e-9
NUMERIC_ATOL = 1.0e-12
METADATA_EXCLUSIONS = ("$.input_file", "$.backend_metadata.engine.build")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _dfe() -> dict[str, Any]:
    return {
        "gain": 0.1,
        "decisionScaler": 1.0,
        "nAve": 1,
        "deltaT": 1.0e-13,
        "alpha": 0.0,
        "nLockAve": 1,
        "relLockTol": 0.01,
        "lockSustain": 1,
        "ideal": True,
        "bandwidth": 0.0,
        "useAgc": False,
        "agcNAve": 1,
    }


def _ctle() -> dict[str, Any]:
    return {
        "bandwidth": 12.0e9,
        "peakFrequency": 5.0e9,
        "peakMagnitudeDb": 4.0,
        "frequencyStepHz": None,
        "frequencyMaxHz": None,
    }


def _metallic(windowed: bool) -> dict[str, Any]:
    return {
        "kind": "metallic_line",
        "value": {
            "sampleInterval": 1.0e-12,
            "lengthM": 0.5,
            "skinEffectResistanceOhmPerM": 0.5,
            "crossoverAngularFrequencyRadPerS": 1.0e7,
            "dcResistanceOhmPerM": 0.1876,
            "characteristicImpedance": 100.0,
            "propagationVelocityMPerS": 0.67 * 3.0e8,
            "lossTangent": 0.02,
            "sourceImpedance": 100.0,
            "sourceCapacitanceF": 0.2e-12,
            "loadImpedance": 100.0,
            "loadCapacitanceF": 0.4e-12,
            "applyRaisedCosineWindow": windowed,
            "frequencyStepHz": None,
            "frequencyMaxHz": None,
            "impulseLength": None,
        },
    }


def _eye(levels: list[float]) -> dict[str, Any]:
    return {
        "targetBer": 1.0e-12,
        "contourBerLevels": levels,
        "rxRjUi": None,
        "rxDjUi": None,
        "txRjUi": None,
        "txDjUi": None,
        "txDcdUi": None,
        "voltageResolution": 1.0e-3,
        "timePoints": 2,
        "maxDistributionStates": 200,
        "postReceiverOutput": False,
    }


def _mutate(base: dict[str, Any], case_id: str) -> dict[str, Any]:
    value = copy.deepcopy(base)
    if case_id == "linear":
        return value
    if case_id == "additive_noise":
        value["tx"]["additiveNoise"] = {"samplesV": [0.125] * 32, "effectiveSeed": None}
        return value
    if case_id == "ctle_additive_noise":
        value["tx"]["additiveNoise"] = {"samplesV": [0.125] * 32, "effectiveSeed": None}
        value["rx"]["nativeCtleEnabled"] = True
        value["rx"]["ctle"] = _ctle()
        return value
    if case_id == "ctle":
        value["rx"]["nativeCtleEnabled"] = True
        value["rx"]["ctle"] = _ctle()
        return value
    if case_id == "metallic_line":
        value["channel"] = _metallic(False)
    elif case_id == "metallic_line_windowed":
        value["channel"] = _metallic(True)
    elif case_id == "jitter_bathtub":
        value["timebase"]["nbits"] = 254
        value["analysis"]["includeJitter"] = True
        value["analysis"]["includeBathtub"] = True
    elif case_id == "statistical_eye":
        value["analysis"]["statisticalEye"] = _eye([1.0e-12, 1.0e-9])
    elif case_id == "dfe":
        value["rx"]["dfeTaps"] = 1
        value["rx"]["dfe"] = _dfe()
    elif case_id == "dfe_statistical_eye":
        value["rx"]["dfeTaps"] = 1
        value["rx"]["dfe"] = _dfe()
        value["analysis"]["statisticalEye"] = _eye([1.0e-12])
    elif case_id == "isi_viterbi":
        value["channel"]["value"]["impulseResponseVoltsPerSecond"] = [1.0e12, 0.25e12, 0.0, 0.0, 0.0]
        value["rx"]["dfeTaps"] = 1
        value["rx"]["dfe"] = _dfe()
        value["rx"]["viterbiEnabled"] = True
        value["rx"]["viterbi"] = {"stateSymbols": 2, "fec": False, "noiseSigmaV": 0.01, "maxStates": 16}
    elif case_id == "fec_viterbi":
        value["modulation"] = "pam4"
        value["rx"]["dfeTaps"] = 1
        value["rx"]["dfe"] = _dfe()
        value["rx"]["viterbiEnabled"] = True
        value["rx"]["viterbi"] = {"stateSymbols": 2, "fec": True, "noiseSigmaV": None, "maxStates": 16}
    elif case_id == "additive_noise_length_rejected":
        value["tx"]["additiveNoise"] = {"samplesV": [0.0] * 31, "effectiveSeed": None}
    else:
        raise RuntimeError(f"unknown source-owned corpus case: {case_id}")
    return value


SUCCESS_CASES = (
    "linear", "additive_noise", "ctle_additive_noise", "metallic_line", "metallic_line_windowed",
    "ctle", "jitter_bathtub", "statistical_eye", "dfe", "dfe_statistical_eye", "isi_viterbi", "fec_viterbi",
)
REJECTION_CASE = "additive_noise_length_rejected"
CASE_IDS = SUCCESS_CASES + (REJECTION_CASE,)


COMPARE_PROBE = r'''
import copy, hashlib, json, math, sys
import numpy as np

left_dir, right_dir, rtol_text, atol_text = sys.argv[1:]
rtol, atol = float(rtol_text), float(atol_text)

def digest(path):
    data = open(path, "rb").read()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def normalize(value, path="$"):
    if path == "$.input_file":
        if not isinstance(value, str): raise ValueError("input_file must be string")
        return "<input-file>"
    if path == "$.backend_metadata.engine.build":
        if not isinstance(value, dict): raise ValueError("engine build must be object")
        return "<engine-build>"
    if isinstance(value, dict):
        return {key: normalize(value[key], path + "." + key) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize(item, path + "[]") for item in value]
    return value

def compare(left, right, path="$", drifts=None):
    if drifts is None: drifts = []
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            drifts.append(path + ":keyset")
            return drifts
        for key in sorted(left): compare(left[key], right[key], path + "." + key, drifts)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right): drifts.append(path + ":length")
        else:
            for index, (a, b) in enumerate(zip(left, right, strict=True)): compare(a, b, path + f"[{index}]", drifts)
    elif isinstance(left, (int, float)) and not isinstance(left, bool) and isinstance(right, (int, float)) and not isinstance(right, bool):
        if not math.isfinite(float(left)) or not math.isfinite(float(right)) or not math.isclose(float(left), float(right), rel_tol=rtol, abs_tol=atol): drifts.append(path + ":numeric")
    elif left != right: drifts.append(path + ":value")
    return drifts

with open(left_dir + "/meta.json", encoding="utf-8") as stream: left_meta = json.load(stream)
with open(right_dir + "/meta.json", encoding="utf-8") as stream: right_meta = json.load(stream)
meta_drifts = compare(normalize(left_meta), normalize(right_meta))
rows, array_drifts = [], []
with np.load(left_dir + "/arrays.npz", allow_pickle=False) as left, np.load(right_dir + "/arrays.npz", allow_pickle=False) as right:
    if set(left.files) != set(right.files): array_drifts.append("member_set")
    for name in sorted(set(left.files) | set(right.files)):
        if name not in left.files or name not in right.files:
            rows.append({"name": name, "present": False}); continue
        a, b = left[name], right[name]
        row = {"name": name, "present": True, "dtype": str(a.dtype), "shape": list(a.shape), "oracle_dtype": str(b.dtype), "oracle_shape": list(b.shape)}
        if a.dtype != b.dtype or a.shape != b.shape:
            row["passed"] = False; array_drifts.append(name + ":schema"); rows.append(row); continue
        if a.dtype.kind in "fc":
            finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
            delta = float(np.max(np.abs(a-b), initial=0.0))
            scale = max(float(np.max(np.abs(a), initial=0.0)), float(np.max(np.abs(b), initial=0.0)), 1.0)
            passed = finite and bool(np.allclose(a, b, rtol=rtol, atol=atol))
            row.update({"numeric": True, "finite": finite, "max_abs": delta, "scale": scale, "tolerance": atol + rtol * scale, "passed": passed})
        else:
            passed = bool(np.array_equal(a, b))
            row.update({"numeric": False, "passed": passed})
        if not passed: array_drifts.append(name + ":payload")
        rows.append(row)
print(json.dumps({
    "metadata": {"passed": not meta_drifts, "drifts": meta_drifts, "excluded_paths": ["$.input_file", "$.backend_metadata.engine.build"]},
    "arrays": {"passed": not array_drifts, "drifts": array_drifts, "members": rows},
    "artifacts": {"candidate": {"meta": digest(left_dir + "/meta.json"), "arrays": digest(left_dir + "/arrays.npz")}, "oracle": {"meta": digest(right_dir + "/meta.json"), "arrays": digest(right_dir + "/arrays.npz")}}
}, sort_keys=True, separators=(",", ":")))
'''


def _tool(path: str, role: str, args: tuple[str, ...]) -> tuple[Path, dict[str, Any]]:
    candidate = Path(path).expanduser()
    resolved = candidate if candidate.is_file() else shutil.which(path)
    if resolved is None:
        raise RuntimeError(f"{role} executable could not be resolved")
    executable = Path(resolved).resolve(strict=True)
    payload = executable.read_bytes()
    version_args = ("/dump", "/headers", str(executable)) if role == "link" else args
    process = matrix.subprocess.run([str(executable), *version_args], stdout=matrix.subprocess.PIPE, stderr=matrix.subprocess.PIPE, check=False)
    if process.returncode != 0:
        raise RuntimeError(f"{role} version probe failed")
    return executable, {"role": role, "executable": executable.name, "file_sha256": _sha256(payload), "version_sha256": _sha256(process.stdout + b"\0" + process.stderr), "version_exit": 0, "path_redacted": True}


def _git(root: Path, *args: str) -> str:
    return matrix._git(root, *args)


def _identity(root: Path, commit: str) -> dict[str, str]:
    resolved = _git(root, "rev-parse", f"{commit}^{{commit}}")
    return {"commit": resolved, "tree": _git(root, "rev-parse", f"{resolved}^{{tree}}")}


def _tracked_inventory(repo: Path, commit: str, archive_root: Path) -> dict[str, Any]:
    """Hash exactly the archive members owned by the immutable Git tree.

    Python and Rust may create caches below an execution checkout.  Those
    generated files must not weaken the check on any source member, nor make a
    clean archive look dirty merely because a runtime cache appeared.
    """

    listed = matrix.subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "-z", commit],
        stdout=matrix.subprocess.PIPE,
        stderr=matrix.subprocess.PIPE,
        check=True,
    ).stdout
    rows: list[dict[str, Any]] = []
    for raw in listed.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8")
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise RuntimeError("Git archive member path is unsafe")
        payload, _ = matrix.secure_read(archive_root, relative, matrix.MAX_FILE_BYTES)
        rows.append({"path": relative, "bytes": len(payload), "sha256": _sha256(payload)})
    return {"entries": len(rows), "sha256": _sha256(_canonical(rows))}


def _write_json(path: Path, value: Any) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        raise RuntimeError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(payload)
    return {"path": path.name, "bytes": len(payload), "sha256": _sha256(payload)}


def _process(result: dict[str, Any]) -> dict[str, Any]:
    return {"exit_code": result["exit_code"], "stdout": result["stdout_fact"], "stderr": result["stderr_fact"]}


def _case(
    case_id: str, base: dict[str, Any], root: Path, candidate_root: Path, upstream_root: Path,
    binary: Path, cargo: Path, rustc: Path, linker: Path, uv: Path, timeout: int,
) -> dict[str, Any]:
    case_root = matrix._fresh_child(root, case_id)
    value = _mutate(base, case_id)
    payload = _canonical(value)
    input_path = case_root / "input.json"
    input_fact = matrix.exclusive_write(case_root, input_path.name, payload)
    candidate_output, oracle_output = case_root / "candidate", case_root / "oracle"
    env = matrix._execution_env(rustc, cargo, linker)
    env["CARGO_TARGET_DIR"] = str(root / "candidate-target")
    oracle_env = matrix._execution_env(rustc, cargo, linker)
    oracle_env["CARGO_TARGET_DIR"] = str(root / "upstream-target")
    oracle_env["UV_PROJECT_ENVIRONMENT"] = str(root / "upstream-venv")
    candidate = matrix._capture_command([str(binary), "sim-native", str(input_path), "--output-dir", str(candidate_output)], cwd=candidate_root, env=env, capture_root=matrix._fresh_child(case_root, "candidate-capture"), label="candidate", timeout=timeout)
    oracle = matrix._capture_command([str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "pybert", "sim-native", str(input_path), "--output-dir", str(oracle_output)], cwd=upstream_root, env=oracle_env, capture_root=matrix._fresh_child(case_root, "oracle-capture"), label="oracle", timeout=timeout)
    result: dict[str, Any] = {"id": case_id, "input": {"bytes": len(payload), "sha256": _sha256(payload), "file": input_fact}, "candidate_process": _process(candidate), "oracle_process": _process(oracle)}
    if case_id == REJECTION_CASE:
        missing = {"candidate": not (candidate_output / "meta.json").exists() and not (candidate_output / "arrays.npz").exists(), "oracle": not (oracle_output / "meta.json").exists() and not (oracle_output / "arrays.npz").exists()}
        message = "additive noise sample count must equal the native receiver waveform length"
        candidate_text = candidate["stdout"] + candidate["stderr"]
        oracle_text = oracle["stdout"] + oracle["stderr"]
        passed = candidate["exit_code"] != 0 and oracle["exit_code"] != 0 and all(missing.values()) and message.encode() in candidate_text and message.encode() in oracle_text
        result.update({"kind": "expected_rejection", "error_category": "additive_noise_length_mismatch", "no_artifacts": missing, "passed": passed})
        return result
    if candidate["exit_code"] != 0 or oracle["exit_code"] != 0:
        result.update({"kind": "complete_native_artifact", "passed": False, "blockers": ["candidate_or_oracle_process_failed"]})
        return result
    probe = matrix._capture_command([str(uv), "run", "--project", str(upstream_root), "--frozen", "--offline", "--no-editable", "--extra", "native", "python", "-c", COMPARE_PROBE, str(candidate_output), str(oracle_output), repr(NUMERIC_RTOL), repr(NUMERIC_ATOL)], cwd=upstream_root, env=oracle_env, capture_root=matrix._fresh_child(case_root, "compare-capture"), label="compare", timeout=timeout)
    if probe["exit_code"] != 0:
        result.update({"kind": "complete_native_artifact", "passed": False, "blockers": ["comparison_probe_failed"], "comparison_process": _process(probe)})
        return result
    comparison = json.loads(probe["stdout"])
    passed = comparison["metadata"]["passed"] and comparison["arrays"]["passed"]
    result.update({"kind": "complete_native_artifact", "comparison": comparison, "passed": passed})
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo, upstream_repo = args.candidate_repo.resolve(strict=True), args.upstream_repo.resolve(strict=True)
    candidate = _identity(candidate_repo, args.candidate_commit)
    upstream = _identity(upstream_repo, args.upstream_commit)
    if upstream != {"commit": PINNED_UPSTREAM, "tree": PINNED_UPSTREAM_TREE}:
        raise RuntimeError("upstream must resolve to the pinned PyBERT source")
    if _git(upstream_repo, "rev-parse", f"{PINNED_UPSTREAM}:{SOURCE_TEST_PATH}") != SOURCE_TEST_BLOB:
        raise RuntimeError("pinned source simulation test blob drift")
    work = args.work_root.resolve() if args.work_root else Path(matrix.tempfile.mkdtemp(prefix="sipi-pb02-native-corpus-"))
    if work.exists() and any(work.iterdir()):
        raise RuntimeError("work root must be absent or empty")
    work.mkdir(parents=True, exist_ok=True)
    candidate_root, candidate_archive = matrix.materialize_archive(candidate_repo, candidate["commit"], work, "candidate", args.timeout_seconds)
    upstream_root, upstream_archive = matrix.materialize_archive(upstream_repo, upstream["commit"], work, "upstream", args.timeout_seconds)
    candidate_before = _tracked_inventory(candidate_repo, candidate["commit"], candidate_root)
    upstream_before = _tracked_inventory(upstream_repo, upstream["commit"], upstream_root)
    fixture = candidate_root / FIXTURE
    base_bytes = fixture.read_bytes()
    base = json.loads(base_bytes)
    cargo, cargo_identity = _tool(args.cargo, "cargo", ("--version",))
    rustc, rustc_identity = _tool(args.rustc, "rustc", ("-Vv",))
    uv, uv_identity = _tool(args.uv, "uv", ("--version",))
    linker, linker_identity = _tool(args.linker, "link", ("/?",))
    binary, build = matrix._build_candidate(candidate_root, work, cargo, rustc, linker, args.timeout_seconds)
    oracle_runtime = matrix._probe_oracle_runtime(upstream_root, work / "upstream-venv", work, uv, cargo, rustc, linker, args.timeout_seconds)
    cases = [_case(case_id, base, work, candidate_root, upstream_root, binary, cargo, rustc, linker, uv, args.timeout_seconds) for case_id in CASE_IDS]
    if _tracked_inventory(candidate_repo, candidate["commit"], candidate_root) != candidate_before or _tracked_inventory(upstream_repo, upstream["commit"], upstream_root) != upstream_before:
        raise RuntimeError("materialized archive changed during replay")
    success = all(case["passed"] for case in cases)
    report = {
        "schema": SCHEMA,
        "version": 1,
        "run_id": args.run_id,
        "nonce": secrets.token_hex(32),
        "status": "passed" if success else "blocked",
        "scope": {"source_test_path": SOURCE_TEST_PATH, "source_test_blob": SOURCE_TEST_BLOB, "successful_case_ids": list(SUCCESS_CASES), "rejection_case_id": REJECTION_CASE, "numeric_rtol": NUMERIC_RTOL, "numeric_atol": NUMERIC_ATOL, "metadata_exclusions": list(METADATA_EXCLUSIONS)},
        "candidate": {**candidate, "archive_sha256": candidate_archive["archive_sha256"], "fixture": {"path": FIXTURE, "bytes": len(base_bytes), "sha256": _sha256(base_bytes)}},
        "upstream": {**upstream, "archive_sha256": upstream_archive["archive_sha256"]},
        "toolchain": {"cargo": cargo_identity, "rustc": rustc_identity, "uv": uv_identity, "link": linker_identity},
        "build": build,
        "oracle_runtime": oracle_runtime,
        "cases": cases,
    }
    _write_json(args.report, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\Py-bert-agent"))
    parser.add_argument("--upstream-commit", default=PINNED_UPSTREAM)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--cargo", default=os.environ.get("CARGO", r"C:\Users\z3312\.cargo\bin\cargo.exe"))
    parser.add_argument("--rustc", default=os.environ.get("RUSTC", r"C:\Users\z3312\.cargo\bin\rustc.exe"))
    parser.add_argument("--uv", default=os.environ.get("UV", "uv"))
    parser.add_argument("--linker", default=os.environ.get("LINK", r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\link.exe"))
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    report = run(args)
    print(json.dumps({"status": report["status"], "run_id": report["run_id"]}, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
