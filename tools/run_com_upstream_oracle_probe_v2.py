"""Probe the pinned Agent-COM runtime without claiming full COM parity.

The pure Python leaves are executed from a clean upstream archive and retain
their numeric payload.  The public ``run_com`` entrypoint is attempted with
the shipped workbook and synthetic THRU fixture under a bounded timeout.  A
timeout is an explicit blocker, never a parity result.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import secrets
import subprocess
import sys
import tarfile
import tempfile
import shutil
import platform
from pathlib import Path
from typing import Any


UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ARCHIVE_SHA256 = "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"
CONFIG = "matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx"
THRU = "fixtures/synthetic/thru_10db_at_26p56ghz.s4p"
ENTRYPOINT_TIMEOUT_SECONDS = 15
TOOL_TIMEOUT_SECONDS = 15
BOUND_TOOLS = (
    "tools/run_com_upstream_oracle_probe_v2.py",
    "tools/aggregate_com_upstream_oracle_probe_v2.py",
    "tools/verify_com_upstream_oracle_probe_v2.py",
    "tools/test_verify_com_upstream_oracle_probe_v2.py",
    "docs/baselines/audits/2026-08-23-com-upstream-runtime-oracle-v2.md",
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def tool_identity(path: Path, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(path), *version_args], capture_output=True, timeout=TOOL_TIMEOUT_SECONDS, check=False
        )
        output = completed.stdout + completed.stderr
        exit_code = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or b"") + (error.stderr or b"")
        exit_code = None
        timed_out = True
    return {
        "role": role,
        "executable": path.name,
        "file_sha256": file_sha256(path),
        "version_output_sha256": sha256(output),
        "version_exit_code": exit_code,
        "path_redacted": True,
        "timeout_seconds": TOOL_TIMEOUT_SECONDS,
        "timed_out": timed_out,
    }


def toolchain_identity() -> dict[str, Any]:
    python = Path(sys.executable).resolve()
    uv_name = shutil.which("uv")
    uv = Path(uv_name).resolve() if uv_name else None
    result: dict[str, Any] = {
        "python": tool_identity(python, "python", ("--version",)),
        "python_runtime": {
            "implementation": platform.python_implementation(),
            "version_output_sha256": sha256(platform.python_version().encode()),
            "path_redacted": True,
        },
        "uv": None if uv is None else tool_identity(uv, "uv", ("--version",)),
        "uv_available": uv is not None,
        "numpy_version": __import__("numpy").__version__,
        "scipy_version": __import__("scipy").__version__,
        "path_redacted": True,
    }
    return result


def package_identity(root: Path) -> dict[str, Any]:
    files = []
    package_root = root / "src" / "agent_com"
    for path in sorted(package_root.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": file_sha256(path)})
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"package": "agent_com", "file_count": len(files), "tree_sha256": sha256(canonical), "numpy_version": __import__("numpy").__version__, "scipy_version": __import__("scipy").__version__}


def fixture_identity(root: Path) -> dict[str, Any]:
    entries = []
    for relative in (CONFIG, THRU):
        path = root / relative
        payload = path.read_bytes()
        entries.append({"path": relative, "bytes": len(payload), "sha256": sha256(payload)})
    return {"paths_relative_to_archive": True, "inputs": entries, "corpus_sha256": sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())}


def binding_hashes() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    return {"files": {relative: {"path": relative, "sha256": file_sha256(root / relative)} for relative in BOUND_TOOLS}, "path_redacted": True}


def materialize(upstream: Path, destination: Path) -> str:
    archive = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(upstream), "archive", "--format=tar", UPSTREAM_COMMIT],
        capture_output=True,
        check=True,
    ).stdout
    digest = sha256(archive)
    if digest != UPSTREAM_ARCHIVE_SHA256:
        raise RuntimeError("pinned upstream archive digest drift")
    destination.mkdir()
    root = destination.resolve()
    with tarfile.open(fileobj=__import__("io").BytesIO(archive), mode="r:") as handle:
        for member in handle.getmembers():
            if member.issym() or member.islnk():
                raise RuntimeError("upstream archive links are not admitted")
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("upstream archive path escapes destination")
        handle.extractall(destination)
    return digest


def portable_payload(root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(root / "src"))
    calibration = importlib.import_module("agent_com.calibration")
    mmse_mod = importlib.import_module("agent_com.equalization.mmse")
    rxffe_mod = importlib.import_module("agent_com.equalization.rx_ffe")
    import numpy as np

    h = np.asarray([[1.0, 0.1], [0.2, 1.0], [0.1, 0.3]], dtype=np.float64)
    mmse = mmse_mod.constrained_mmse(
        h, np.eye(2, dtype=np.float64) * 0.01, decision_index=0,
        dfe_tap_count=1, sigma_x2=1.0, levels=4, r_lm=50.0,
        rx_min=np.asarray([-2.0, -2.0]), rx_max=np.asarray([2.0, 2.0]),
        dfe_min=np.asarray([-0.5]), dfe_max=np.asarray([0.5]), rx_cursor_offset=0,
    )
    waveform = np.zeros(32, dtype=np.float64)
    waveform[[8, 12, 16, 20, 24, 28]] = [0.01, 0.1, 1.0, 0.05, 0.02, 0.01]
    rxffe = rxffe_mod.force_rx_ffe(
        waveform, cursor_index=16, precursor_count=1, postcursor_count=2,
        samples_per_ui=4, unity_cursor=True, return_filtered=True,
    )
    calibration_result = calibration.calibrate_receiver_noise(
        lambda sigma: np.asarray([3.0 - sigma, 2.5 - sigma], dtype=np.float64),
        pass_threshold_db=2.0, initial_step_v=2.0,
    )
    return {
        "mmse": {
            "fom_db": float(mmse.fom_db), "sigma_e": float(mmse.sigma_e),
            "condition_number": float(mmse.condition_number),
            "rx_ffe": np.asarray(mmse.rx_ffe).tolist(), "dfe": np.asarray(mmse.dfe).tolist(),
        },
        "rx_ffe_search": {
            "taps": np.asarray(rxffe.taps).tolist(),
            "filtered_waveform_sha256": sha256(np.asarray(rxffe.filtered, dtype=np.float64).tobytes()),
        },
        "calibration": {
            "sigma_bn_v": float(calibration_result.sigma_bn_v),
            "iteration_count": len(calibration_result.iterations),
            "minimum_com_db": [float(item.minimum_com_db) for item in calibration_result.iterations],
        },
    }


def entrypoint_probe(root: Path, timeout: int) -> dict[str, Any]:
    if timeout != ENTRYPOINT_TIMEOUT_SECONDS:
        raise RuntimeError("entrypoint timeout gate drift")
    code = (
        "from pathlib import Path; "
        "from agent_com import load_config,run_com,ChannelSet,RunOptions,BehaviorProfile; "
        "r=Path.cwd(); c=load_config(r/'" + CONFIG + "'); "
        "run_com(config=c, channels=ChannelSet(r/'" + THRU + "'), "
        "options=RunOptions(BehaviorProfile.r480(), diagnostics=False))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code], cwd=root, env=env,
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "status": "blocked",
            "reason": "entrypoint_timeout",
            "timeout_seconds": timeout,
            "stdout_sha256": sha256(error.stdout or b""),
            "stderr_sha256": sha256(error.stderr or b""),
            "dependency": "numpy+scipy available; no MATLAB engine requested",
            "entrypoint": "agent_com.api.run_com",
        }
    return {
        "status": "passed" if completed.returncode == 0 else "blocked",
        "returncode": completed.returncode,
        "timeout_seconds": timeout,
        "stdout_sha256": sha256(completed.stdout),
        "stderr_sha256": sha256(completed.stderr),
        "entrypoint": "agent_com.api.run_com",
        "dependency": "numpy+scipy available; no MATLAB engine requested",
        "reason": None if completed.returncode == 0 else "entrypoint_nonzero",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-com-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("com-02", "com-04"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="sipi-com-upstream-v2-") as directory:
        root = Path(directory) / "upstream"
        archive_sha256 = materialize(args.agent_com_root.resolve(), root)
        report = {
            "schema": "sipi.com-upstream-runtime-oracle.v2",
            "mode": args.mode,
            "run_id": args.run_id,
            "fresh_run_nonce": secrets.token_hex(32),
            "upstream": {
                "commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE,
                "archive_sha256": archive_sha256, "declared_license": "MIT",
                "materialization": "git archive at immutable commit",
                "observation_scope": "upstream_only",
                "runtime_executed": True,
            },
            "execution_binding": {
                "toolchain": toolchain_identity(),
                "package": package_identity(root),
                "fixtures": fixture_identity(root),
                "scripts": binding_hashes(),
                "entrypoint_timeout_seconds": ENTRYPOINT_TIMEOUT_SECONDS,
            },
            "portable_leaf": {
                "status": "numeric_payload_observed",
                "payload": portable_payload(root),
            },
            "entrypoint": entrypoint_probe(root, args.timeout),
            "parity": {
                "portable_leaf_numeric_payload": True,
                "full_run_numeric_parity": False,
                "candidate_rust_parity_claim": False,
                "observation_scope": "upstream_only",
                "release_or_promotion": False,
            },
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": report["schema"], "run_id": args.run_id, "entrypoint": report["entrypoint"]["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
