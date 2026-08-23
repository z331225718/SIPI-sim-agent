"""Shared immutable replay helpers for the PB-03..PB-05 Rust leaves.

The helper intentionally treats any missing executable, failed oracle, payload
shape error, or mismatch as blocked.  It never upgrades a wrapper exit code to
numeric parity.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PB03_PARITY_ARRAYS = (
    "ber_auto_correlation.npy",
    "ber_error_indices.npy",
    "ber_observed_bits.npy",
    "ber_reference_bits.npy",
    "channel_impulse_v_per_v.npy",
    "channel_output_v.npy",
    "ctle_output_v.npy",
    "dfe_bits.npy",
    "dfe_clock_times_s.npy",
    "dfe_clocks.npy",
    "dfe_decision_scalers_v.npy",
    "dfe_decisions.npy",
    "dfe_locked.npy",
    "dfe_output_v.npy",
    "dfe_signal_samples_v.npy",
    "dfe_tap_weights_v.npy",
    "dfe_ui_estimates_s.npy",
    "legacy_channel_frequency_hz.npy",
    "legacy_channel_raw_im.npy",
    "legacy_channel_raw_re.npy",
    "legacy_channel_terminated_im.npy",
    "legacy_channel_terminated_re.npy",
    "legacy_channel_trimmed_im.npy",
    "legacy_channel_trimmed_re.npy",
    "legacy_stage_ctle_im.npy",
    "legacy_stage_ctle_out_im.npy",
    "legacy_stage_ctle_out_re.npy",
    "legacy_stage_ctle_re.npy",
    "legacy_stage_dfe_im.npy",
    "legacy_stage_dfe_out_im.npy",
    "legacy_stage_dfe_out_re.npy",
    "legacy_stage_dfe_re.npy",
    "legacy_stage_tx_im.npy",
    "legacy_stage_tx_out_im.npy",
    "legacy_stage_tx_out_re.npy",
    "legacy_stage_tx_re.npy",
    "rx_ffe_impulse_v_per_v.npy",
    "rx_filter_impulse_v_per_v.npy",
    "rx_input_v.npy",
    "rx_output_v.npy",
    "symbols_v.npy",
    "time_s.npy",
    "tx_channel_impulse_v_per_v.npy",
    "tx_waveform_v.npy",
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def git(repo: Path, *args: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def archive_repo(repo: Path, commit: str, destination: Path) -> dict[str, Any]:
    payload = bytes(git(repo, "archive", "--format=tar", commit, raw=True))
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        root = destination.resolve()
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
            archive.extract(member, destination)
    resolved = str(git(repo, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(git(repo, "rev-parse", f"{resolved}^{{tree}}"))
    return {"commit": resolved, "tree": tree, "archive_sha256": sha256(payload)}


def overlay_lane_worktree(repo: Path, destination: Path) -> dict[str, str]:
    """Overlay only the PB direct-port lane and record every file digest."""
    source_root = repo / "crates" / "sipi-pybert-direct"
    if not source_root.is_dir():
        raise RuntimeError("PB direct-port lane is missing from the candidate worktree")
    overlay: dict[str, str] = {}
    for source in sorted(source_root.rglob("*")):
        relative_to_lane = source.relative_to(source_root)
        if not source.is_file() or "target" in relative_to_lane.parts:
            continue
        relative = source.relative_to(repo).as_posix()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = source.read_bytes()
        target.write_bytes(payload)
        overlay[relative] = sha256(payload)
    if not overlay:
        raise RuntimeError("PB direct-port worktree overlay is empty")
    return overlay


def _tool(value: str, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    executable = resolve_executable(value)
    if executable is None:
        raise RuntimeError(f"{role} executable is unavailable")
    version = subprocess.run([str(executable), *version_args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if version.returncode != 0:
        raise RuntimeError(f"{role} version command failed")
    return {
        "role": role,
        "executable": executable.name,
        "path_redacted": True,
        "file_sha256": sha256(executable.read_bytes()),
        "version_exit_code": version.returncode,
        "version_output_sha256": sha256(version.stdout + b"\x00" + version.stderr),
    }


def resolve_executable(value: str) -> Path | None:
    candidates = []
    located = shutil.which(value)
    if located:
        candidates.append(Path(located))
    if value in {"cargo", "rustc", "rustup"}:
        cargo_bin = Path.home() / ".cargo" / "bin"
        candidates.extend((cargo_bin / value, cargo_bin / f"{value}.exe"))
    candidates.append(Path(value))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def toolchain(timeout: int) -> dict[str, Any]:
    cargo = _tool("cargo", "cargo", ("-Vv",))
    rustc = _tool("rustc", "rustc", ("-Vv",))
    uv = _tool("uv", "uv", ("--version",))
    return {"timeout_seconds": timeout, "cargo": cargo, "rustc": rustc, "uv": uv}


def fixture_info(root: Path, relative: str, fallback: Path | None = None) -> dict[str, Any]:
    path = root / relative
    archive_present = path.is_file()
    if not archive_present and fallback is not None:
        path = fallback
    payload = path.read_bytes()
    return {"path": relative, "bytes": len(payload), "sha256": sha256(payload), "archive_present": archive_present}


def npy_summary(payload: bytes) -> dict[str, Any]:
    if payload[:6] != b"\x93NUMPY":
        raise ValueError("NPZ member is not NPY")
    major = payload[6]
    header_offset = 10 if major == 1 else 12
    header_size = int.from_bytes(payload[8:header_offset], "little")
    end = header_offset + header_size
    header = ast.literal_eval(payload[header_offset:end].decode("latin1").strip())
    if not isinstance(header, dict) or header.get("descr") not in ("<f8", "|f8", ">f8"):
        raise ValueError("NPY member is not float64")
    shape = tuple(int(value) for value in header.get("shape", ()))
    count = math.prod(shape)
    raw = payload[end:]
    if len(raw) != count * 8:
        raise ValueError("NPY payload length mismatch")
    if header["descr"] == ">f8":
        raw = b"".join(raw[index : index + 8][::-1] for index in range(0, len(raw), 8))
    return {"count": count, "dtype": header["descr"], "shape": list(shape), "fortran_order": bool(header.get("fortran_order")), "f64_sha256": sha256(raw)}


def npz_summary(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    members: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.endswith(".npy"):
                continue
            members[info.filename] = npy_summary(archive.read(info))
    return {"sha256": sha256(payload), "bytes": len(payload), "logical_members": dict(sorted(members.items())), "logical_sha256": sha256(canonical(dict(sorted(members.items()))))}


def artifact_summary(output: Path) -> dict[str, Any]:
    meta = output / "meta.json"
    arrays = output / "arrays.npz"
    result: dict[str, Any] = {"meta_present": meta.is_file(), "arrays_present": arrays.is_file()}
    if meta.is_file():
        payload = meta.read_bytes()
        result["meta_sha256"] = sha256(payload)
        try:
            value = json.loads(payload.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            result["meta_json_valid"] = False
        else:
            result["meta_json_valid"] = isinstance(value, dict)
            result["meta_schema"] = value.get("schema") if isinstance(value, dict) else None
            result["meta_payload_sha256"] = sha256(canonical(value))
            if isinstance(value, dict):
                result["selection"] = selection_summary(value)
                result["comparison"] = comparison_summary(value)
    if arrays.is_file():
        try:
            result["arrays"] = npz_summary(arrays)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            result["arrays_error"] = type(error).__name__
    return result


def selection_summary(value: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only the stable engine-selection contract, never host paths."""
    candidates: list[Any] = []
    for container in (value.get("diagnostics"), value.get("engine_diagnostics")):
        if isinstance(container, dict):
            candidates.append(container.get("engine_selection"))
    for item in candidates:
        if not isinstance(item, dict):
            continue
        gate = item.get("parity_gate")
        return {
            "requested": item.get("requested"),
            "selected": item.get("selected"),
            "fallback_reason": item.get("fallback_reason"),
            "implementation": item.get("implementation"),
            "rust_only": item.get("rust_only"),
            "parity_gate": {
                "version": gate.get("version"),
                "status": gate.get("status"),
                "reason": gate.get("reason"),
            }
            if isinstance(gate, dict)
            else None,
        }
    return None


def comparison_summary(value: dict[str, Any]) -> dict[str, Any] | None:
    """Summarize compare semantics without reducing them to process status."""
    diagnostics = value.get("diagnostics")
    comparison = diagnostics.get("comparison") if isinstance(diagnostics, dict) else None
    if not isinstance(comparison, dict):
        return None
    arrays = comparison.get("arrays")
    metrics = comparison.get("metrics")
    metadata = comparison.get("metadata")
    details: dict[str, Any] = {
        "schema": comparison.get("schema"),
        "passed": comparison.get("passed"),
        "status_only_comparison": comparison.get("status_only_comparison"),
        "arrays_passed": arrays.get("passed") if isinstance(arrays, dict) else None,
        "metrics_passed": metrics.get("passed") if isinstance(metrics, dict) else None,
        "metadata_passed": metadata.get("passed") if isinstance(metadata, dict) else None,
        "reason": comparison.get("reason"),
        "reference_required": comparison.get("reference_required"),
        "source": (diagnostics.get("compare_reference") or {}).get("source")
        if isinstance(diagnostics.get("compare_reference"), dict)
        else None,
    }
    return details


def run_command(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    resolved = list(command)
    environment = os.environ.copy()
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.is_dir():
        environment["PATH"] = str(cargo_bin) + os.pathsep + environment.get("PATH", "")
    if resolved and resolved[0] in {"cargo", "rustc", "uv"}:
        executable = resolve_executable(resolved[0])
        if executable is None:
            return {"exit_code": None, "error": f"{resolved[0]} executable unavailable", "stdout_sha256": None, "stderr_sha256": None}
        resolved[0] = str(executable)
    try:
        process = subprocess.run(resolved, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"exit_code": None, "error": type(error).__name__, "stdout_sha256": None, "stderr_sha256": None}
    result: dict[str, Any] = {
        "exit_code": process.returncode,
        "stdout_sha256": sha256(process.stdout),
        "stderr_sha256": sha256(process.stderr),
    }
    try:
        parsed_stderr = json.loads(process.stderr.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed_stderr = None
    if isinstance(parsed_stderr, dict):
        result["stderr_json"] = parsed_stderr
    return result


def _binary(target: Path) -> Path:
    return target / "release" / ("sipi-pybert-direct.exe" if os.name == "nt" else "sipi-pybert-direct")


def payload_digest(summary: dict[str, Any], row: str) -> str | None:
    arrays = summary.get("arrays") if isinstance(summary, dict) else None
    if not isinstance(arrays, dict):
        return None
    members = arrays.get("logical_members")
    if not isinstance(members, dict):
        return None
    if row == "PB-03":
        if not set(PB03_PARITY_ARRAYS).issubset(members):
            return None
        return sha256(canonical({name: members[name] for name in PB03_PARITY_ARRAYS}))
    return arrays.get("logical_sha256")


def compact_artifact(summary: dict[str, Any], row: str) -> dict[str, Any]:
    """Keep reports bounded while retaining every gate input."""
    value = dict(summary)
    arrays = value.get("arrays")
    if not isinstance(arrays, dict):
        return value
    arrays = dict(arrays)
    members = arrays.get("logical_members")
    if isinstance(members, dict):
        arrays["logical_member_count"] = len(members)
        arrays["logical_members"] = {
            name: members[name]
            for name in PB03_PARITY_ARRAYS
            if row == "PB-03" and name in members
        }
    value["arrays"] = arrays
    return value


def run_once(row: str, candidate_repo: Path, upstream_repo: Path, fixture: str, candidate_commit: str, run_id: str, timeout: int) -> dict[str, Any]:
    fixture = PurePosixPath(fixture).as_posix()
    if PureWindowsPath(fixture).is_absolute() or PurePosixPath(fixture).is_absolute() or ".." in PurePosixPath(fixture).parts:
        raise RuntimeError("fixture must be repository-relative")
    with tempfile.TemporaryDirectory(prefix=f"sipi-{row.lower()}-") as work:
        work_root = Path(work)
        candidate_root = work_root / "candidate"
        upstream_root = work_root / "upstream"
        candidate_identity = archive_repo(candidate_repo, candidate_commit, candidate_root)
        candidate_archive_fixture_present = (candidate_root / fixture).is_file()
        candidate_overlay = overlay_lane_worktree(candidate_repo, candidate_root)
        candidate_identity = {**candidate_identity, "working_tree_overlay": candidate_overlay}
        upstream_identity = archive_repo(upstream_repo, UPSTREAM_COMMIT, upstream_root)
        fixture_source = candidate_repo / fixture
        if not fixture_source.is_file():
            raise RuntimeError("fixed fixture is missing from the candidate source tree")
        fixture_bytes = fixture_source.read_bytes()
        for tree in (candidate_root, upstream_root):
            fixture_target = tree / fixture
            fixture_target.parent.mkdir(parents=True, exist_ok=True)
            if fixture_target.is_file() and fixture_target.read_bytes() != fixture_bytes:
                raise RuntimeError("archive fixture differs from the fixed corpus")
            if not fixture_target.is_file():
                fixture_target.write_bytes(fixture_bytes)
        fixture_path = candidate_root / fixture
        # The direct crate is its own workspace, so Cargo places artifacts next
        # to its manifest rather than at the repository root.
        candidate_target = candidate_root / "crates" / "sipi-pybert-direct" / "target"
        candidate_output = work_root / "candidate-output"
        upstream_output = work_root / "upstream-output"
        build = run_command(["cargo", "build", "--manifest-path", str(candidate_root / "crates/sipi-pybert-direct/Cargo.toml"), "--release", "--locked"], candidate_root, timeout)
        binary = _binary(candidate_target)
        if build.get("exit_code") == 0:
            build = {**build, "binary_sha256": sha256(binary.read_bytes()) if binary.is_file() else None}
        command = {"PB-03": "sim-rust", "PB-04": "sim-auto", "PB-05": "sim-compare"}[row]
        if binary.is_file():
            candidate_process = run_command([str(binary), command, str(fixture_path), "--output-dir", str(candidate_output)], candidate_root, timeout)
        else:
            candidate_process = {"exit_code": None, "skipped": True}
        oracle_process = run_command(["uv", "run", "--project", str(upstream_root), "--frozen", "--extra", "native", "pybert", command, str(upstream_root / fixture), "--output-dir", str(upstream_output)], upstream_root, timeout)
        candidate_artifact = artifact_summary(candidate_output)
        oracle_artifact = artifact_summary(upstream_output)
        candidate_payload = payload_digest(candidate_artifact, row)
        oracle_payload = payload_digest(oracle_artifact, row)
        candidate_artifact = compact_artifact(candidate_artifact, row)
        oracle_artifact = compact_artifact(oracle_artifact, row)
        expected_schema = {
            "PB-03": "pybert.native-cli-result.v1",
            "PB-04": "pybert.cli-auto-result.v1",
            "PB-05": "pybert.cli-compare-result.v1",
        }[row]
        candidate_ok = (
            candidate_process.get("exit_code") == 0
            and candidate_artifact.get("meta_schema") == expected_schema
            and candidate_payload is not None
        )
        oracle_ok = (
            oracle_process.get("exit_code") == 0
            and oracle_artifact.get("meta_schema") == expected_schema
            and oracle_payload is not None
        )
        candidate_selection = candidate_artifact.get("selection")
        if candidate_selection is None:
            candidate_selection = selection_summary(candidate_process.get("stderr_json", {}))
        candidate_comparison = candidate_artifact.get("comparison")
        if candidate_comparison is None:
            candidate_comparison = comparison_summary(candidate_process.get("stderr_json", {}))
        candidate_no_reference = (
            row == "PB-05"
            and isinstance(candidate_comparison, dict)
            and candidate_comparison.get("reason") == "not_evaluated"
            and candidate_comparison.get("reference_required") == "external_python_reference_required"
            and candidate_comparison.get("status_only_comparison") is False
        )
        if candidate_no_reference:
            # A missing independent reference is an expected fail-closed outcome,
            # not a process/schema regression.  The row remains blocked because
            # payload parity was intentionally not evaluated.
            candidate_ok = True
        selection = {
            "candidate": candidate_selection,
            "oracle": oracle_artifact.get("selection"),
            "expected": {
                "requested": "auto",
                "selected": "python",
                "parity_gate_status": "blocked",
            }
            if row == "PB-04"
            else None,
        }
        comparison = {
            "candidate": candidate_comparison,
            "oracle": oracle_artifact.get("comparison"),
            "payload_gate": {
                "candidate_artifact_present": candidate_payload is not None,
                "oracle_artifact_present": oracle_payload is not None,
                "logical_arrays_equal": candidate_payload is not None and candidate_payload == oracle_payload,
                "status_only_comparison": False,
            }
            if row == "PB-05"
            else None,
        }
        semantic_ok = True
        if row == "PB-04":
            candidate_selection = selection.get("candidate")
            oracle_selection = oracle_artifact.get("selection")
            semantic_ok = (
                isinstance(candidate_selection, dict)
                and candidate_selection.get("requested") == "auto"
                and candidate_selection.get("selected") == "python"
                and candidate_selection.get("implementation") == "external_python_reference_required"
                and candidate_selection.get("rust_only") is False
                and isinstance(candidate_selection.get("parity_gate"), dict)
                and candidate_selection["parity_gate"].get("status") == "blocked"
                and isinstance(oracle_selection, dict)
                and oracle_selection.get("requested") == "auto"
                and oracle_selection.get("selected") == "python"
                and isinstance(oracle_selection.get("parity_gate"), dict)
                and oracle_selection["parity_gate"].get("status") == "blocked"
            )
        if row == "PB-05":
            candidate_comparison = comparison.get("candidate")
            oracle_comparison = oracle_artifact.get("comparison")
            semantic_ok = (
                isinstance(candidate_comparison, dict)
                and candidate_comparison.get("schema") == "pybert.engine-compare.v1"
                and candidate_comparison.get("status_only_comparison") is False
                and (
                    candidate_comparison.get("reason") == "not_evaluated"
                    or candidate_comparison.get("arrays_passed") is not None
                )
                and isinstance(oracle_comparison, dict)
                and oracle_comparison.get("schema") == "pybert.engine-compare.v1"
                and oracle_comparison.get("status_only_comparison") is not True
                and oracle_comparison.get("arrays_passed") is not None
            )
        blockers: list[str] = []
        if not candidate_ok:
            blockers.append("candidate process or artifact schema/payload gate failed")
        if not oracle_ok:
            blockers.append("oracle process or artifact schema/payload gate failed")
        if candidate_payload is None or oracle_payload is None or candidate_payload != oracle_payload:
            if candidate_no_reference:
                blockers.append("candidate/oracle payload parity not_evaluated: external_python_reference_required")
            else:
                blockers.append("candidate/oracle logical payload gate failed")
        if not semantic_ok:
            blockers.append("workflow semantic gate failed")
        fixture_record = fixture_info(candidate_root, fixture)
        fixture_record["archive_present"] = candidate_archive_fixture_present
        fixture_record["archive_present_before_overlay"] = candidate_archive_fixture_present
        fixture_record["working_tree_overlay_present"] = fixture in candidate_overlay
        if not candidate_archive_fixture_present and fixture not in candidate_overlay:
            blockers.append("fixed fixture is not present in the candidate archive or content-addressed lane overlay")
        return {
            "schema": f"sipi.{row.lower()}-direct-replay.v1",
            "status": "passed" if not blockers else "blocked",
            "source_mode": "git_archive_plus_lane_working_tree_content_addressed",
            "row": row,
            "run_id": run_id,
            "fresh_run_nonce": uuid.uuid4().hex,
            "candidate": candidate_identity,
            "upstream": upstream_identity,
            "fixture": fixture_record,
            "build": build,
            "replay": {
                "candidate_process": candidate_process,
                "oracle_process": oracle_process,
                "candidate_artifact": candidate_artifact,
                "oracle_artifact": oracle_artifact,
                "payload": {"candidate_logical_sha256": candidate_payload, "oracle_logical_sha256": oracle_payload, "equal": candidate_payload is not None and candidate_payload == oracle_payload},
                "selection": selection,
                "comparison": comparison,
                "semantic_gate": semantic_ok,
            },
            "blockers": blockers,
            "claims": {"payload_parity": bool(candidate_ok and oracle_ok and candidate_payload == oracle_payload and semantic_ok), "global_row_closed": False, "release_approval": False},
            "non_claims": ["This is one frozen fixture only.", "Wrapper, selection, comparison, and uncovered branches remain open unless their payload gate passes.", "This evidence is not a license decision or release approval."],
        }


def parse_run_args(row: str, fixture: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--candidate-commit", default=str(git(ROOT, "rev-parse", "HEAD")))
    parser.add_argument("--fixture", default=fixture)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    args = parser.parse_args()
    args.row = row
    return args


def run_main(args: argparse.Namespace) -> int:
    try:
        report = run_once(args.row, args.candidate_repo.resolve(), args.upstream_repo.resolve(), args.fixture, args.candidate_commit, args.run_id, args.timeout_seconds)
        report["toolchain"] = toolchain(args.timeout_seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"status": report["status"], "output": args.output.as_posix()}, sort_keys=True))
    return 0 if report["status"] == "passed" else 1
