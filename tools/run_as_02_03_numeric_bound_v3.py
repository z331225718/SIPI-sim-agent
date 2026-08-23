"""Run a pinned upstream-vs-Rust numeric observation for AS-02 or AS-03."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
UPSTREAM_ROOT = Path(r"C:\Users\z3312\code\agent-spice")
FIXTURE = "# Hz S RI R 50\n1e6 0.01 0 0.8 0 0.8 0 0.01 0\n1e7 0.01 0 0.79 0 0.79 0 0.01 0\n1e8 0.01 0 0.7 0 0.7 0 0.01 0\n1e9 0.01 0 0.4 0 0.4 0 0.01 0\n"
FIXTURE_KIND = "fixed_touchstone_line_s2p_v1"
FIXTURE_GENERATED_BY = "tools/run_as_02_03_numeric_bound_v3.py:FIXTURE"
WRAPPER_POLICY = {
    "schema": "sipi.path-free-wrapper-policy.v1",
    "clear_inherited_rustc_wrapper": True,
    "clear_inherited_rustc_workspace_wrapper": True,
    "rustc_wrapper": "unset",
    "rustc_workspace_wrapper": "unset",
}


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def archive(repo: Path, revision: str, destination: Path) -> str:
    payload = subprocess.check_output(["git", "-C", str(repo), "archive", "--format=tar", revision])
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(fileobj=__import__("io").BytesIO(payload), mode="r:") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escape: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(f"unsupported archive member: {member.name}")
        tar.extractall(destination)
    return sha_bytes(payload)


def tool_identity(path: Path, role: str, args: tuple[str, ...]) -> dict[str, Any]:
    result = subprocess.run([str(path), *args], capture_output=True, check=False)
    return {"schema": "sipi.path-free-tool-identity.v1", "role": role, "executable": path.name, "path_redacted": True, "file_sha256": sha(path), "version_sha256": sha_bytes(result.stdout + b"\0" + result.stderr), "exit_code": result.returncode}


def run(command: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    # Keep diagnostics content-addressed but never persist compiler/runtime paths.
    return {
        "returncode": result.returncode,
        "stdout_sha256": sha_bytes(result.stdout.encode()),
        "stderr_sha256": sha_bytes(result.stderr.encode()),
        "stdout_bytes": len(result.stdout.encode()),
        "stderr_bytes": len(result.stderr.encode()),
    }


def execute(row: str, *, run_id: str, report_path: Path, python: Path, cargo: Path, candidate_commit: str, candidate_tree: str, candidate_archive_sha256: str) -> dict[str, Any]:
    if row not in {"AS-02", "AS-03"}:
        raise ValueError("row must be AS-02 or AS-03")
    if len(candidate_commit) != 40 or len(candidate_tree) != 40 or len(candidate_archive_sha256) != 64 or any(c not in "0123456789abcdef" for c in candidate_commit + candidate_tree + candidate_archive_sha256):
        raise ValueError("candidate commit/tree/archive must be lowercase hexadecimal identities")
    fresh_nonce = secrets.token_hex(32)
    run_root = Path(tempfile.mkdtemp(prefix=f"sipi-{row.lower()}-numeric-"))
    stable = Path(tempfile.gettempdir()) / f"sipi-{candidate_commit[:12]}-numeric-candidate"
    if stable.exists():
        shutil.rmtree(stable)
    stable.mkdir(parents=True)
    try:
        candidate_root = stable / "candidate"
        upstream_root = run_root / "upstream"
        actual_tree = subprocess.check_output(["git", "-C", str(ROOT), "show", "-s", "--format=%T", candidate_commit], text=True).strip()
        if actual_tree != candidate_tree:
            raise RuntimeError("candidate commit/tree binding mismatch")
        candidate_archive_sha = archive(ROOT, candidate_commit, candidate_root)
        if candidate_archive_sha != candidate_archive_sha256:
            raise RuntimeError("candidate archive SHA binding mismatch")
        upstream_archive_sha = archive(UPSTREAM_ROOT, UPSTREAM_COMMIT, upstream_root)
        target = stable / "target"
        rustc = cargo.with_name("rustc.exe")
        env = dict(os.environ)
        env.pop("RUSTC_WRAPPER", None)
        env.pop("RUSTC_WORKSPACE_WRAPPER", None)
        env.update({"CARGO_TARGET_DIR": str(target), "CARGO_INCREMENTAL": "0", "SOURCE_DATE_EPOCH": "0", "RUSTC": str(rustc)})
        sep = "\x1f"
        env["CARGO_ENCODED_RUSTFLAGS"] = sep.join((f"--remap-path-prefix={candidate_root}=/sipi-candidate", f"--remap-path-prefix={target}=/sipi-target", "-Cmetadata=as-numeric", "-Clink-arg=/Brepro"))
        binary_name = "sipi-agent-spice-fit-sparam-cascade.exe" if row == "AS-02" else "sipi-agent-spice-fit-yparam.exe"
        build = run([str(cargo), "build", "--manifest-path", str(candidate_root / "crates/sipi-agent-spice-direct/Cargo.toml"), "--release", "--locked", "--bin", binary_name.removesuffix(".exe")], candidate_root, env)
        binary = target / "release" / binary_name
        if build["returncode"] != 0 or not binary.is_file():
            raise RuntimeError("candidate archive build failed")
        input_path = run_root / "line.s2p"
        input_path.write_text(FIXTURE, encoding="ascii", newline="\n")
        if row == "AS-02":
            manifest = run_root / "cascade.json"
            manifest.write_text(json.dumps({"version": 1, "blocks": [{"name": "a", "touchstone": "line.s2p"}, {"name": "b", "touchstone": "line.s2p"}], "cascade": ["a", "b"]}), encoding="utf-8")
            args = ["--rms-target", "1", "--max-order", "1", "--min-order", "1", "--max-order-step", "1", "--cascade-samples", "8"]
            upstream_command = [str(python), "-I", "-c", "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=['agent-spice','fit-sparam-cascade',*sys.argv[2:]];runpy.run_module('agent_spice.cli',run_name='__main__')", str(upstream_root / "src"), str(run_root / "cascade.json"), "--output-root", str(run_root / "upstream-out"), *args]
            candidate_command = [str(binary), str(manifest), "--output-root", str(run_root / "candidate-out"), *args]
            upstream_result = run(upstream_command, run_root, env)
            candidate_result = run(candidate_command, run_root, env)
            upstream_report = run_root / "upstream-out/cascade_report.json"
            candidate_report = run_root / "candidate-out/cascade_report.json"
            if not upstream_report.is_file() or not candidate_report.is_file():
                raise RuntimeError(f"AS-02 report missing upstream={upstream_result} candidate={candidate_result}")
            up = json.loads(upstream_report.read_text(encoding="utf-8")); cand = json.loads(candidate_report.read_text(encoding="utf-8"))
            metrics = {"upstream_cascade_mean_rms": up["cascade_mean_rms_error"], "candidate_cascade_mean_rms": cand["cascade_mean_rms_error"], "upstream_block_rms": [x["full_band_mean_rms_error"] for x in up["blocks"]], "candidate_block_rms": [x["gate"]["full_band_rms"] for x in cand["blocks"]], "upstream_snapshot": {"cascade_order": up.get("cascade_order"), "selected_scales": up.get("selected_scales"), "blocks": [{"name": x.get("name"), "selected_order": x.get("selected_order"), "pole_relocation_iterations": x.get("pole_relocation_iterations"), "scale": x.get("scale"), "full_band_mean_rms_error": x.get("full_band_mean_rms_error"), "priority_band_mean_rms_error": x.get("priority_band_mean_rms_error")} for x in up.get("blocks", [])]}, "candidate_snapshot": {"cascade_order": cand.get("cascade_order"), "selected_scales": cand.get("selected_scales"), "blocks": [{"name": x.get("name"), "selected_order": x.get("selected_order"), "pole_relocation_iterations": x.get("pole_relocation_iterations"), "scale": x.get("scale"), "gate": {"full_band_rms": x.get("gate", {}).get("full_band_rms"), "priority_band_rms": x.get("gate", {}).get("priority_band_rms"), "target_met": x.get("gate", {}).get("target_met")}} for x in cand.get("blocks", [])]}}
        else:
            args = ["--n-poles-real", "1", "--n-poles-cmplx", "0", "--max-order", "1", "--fit-iterations", "2", "--max-y-rms-siemens", "100", "--passivity", "off"]
            upstream_command = [str(python), "-I", "-c", "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=['agent-spice','fit-yparam',*sys.argv[2:]];runpy.run_module('agent_spice.cli',run_name='__main__')", str(upstream_root / "src"), str(input_path), "--output", str(run_root / "upstream.y.sp"), "--report", str(run_root / "upstream.y.json"), *args]
            candidate_command = [str(binary), str(input_path), "--output", str(run_root / "candidate.y.sp"), "--report", str(run_root / "candidate.y.json"), *args]
            upstream_result = run(upstream_command, run_root, env)
            candidate_result = run(candidate_command, run_root, env)
            upstream_report = run_root / "upstream.y.json"
            candidate_report = run_root / "candidate.y.json"
            if not upstream_report.is_file() or not candidate_report.is_file():
                raise RuntimeError(f"AS-03 report missing upstream={upstream_result} candidate={candidate_result}")
            up = json.loads(upstream_report.read_text(encoding="utf-8")); cand = json.loads(candidate_report.read_text(encoding="utf-8"))
            metrics = {"upstream_y_rms_siemens": up["y_rms_siemens"], "candidate_y_rms_siemens": cand["y_rms_siemens"], "upstream_y_mean_rms_siemens": up["y_mean_rms_siemens"], "candidate_y_mean_rms_siemens": cand["y_mean_rms_siemens"], "upstream_snapshot": {key: up.get(key) for key in ("selected_order", "model_order", "pole_relocation_iterations", "target_met", "exact_delivery_gate") if key in up}, "candidate_snapshot": {key: cand.get(key) for key in ("selected_order", "model_order", "pole_relocation_iterations", "target_met", "exact_delivery_gate") if key in cand}}
        report = {"schema": "sipi.agent-spice-as-numeric-bound.v3", "workflow": row, "status": "completed_numeric_mismatch_open", "parity_claim": False, "numeric_parity": False, "run_id": run_id, "fresh_run_nonce": fresh_nonce, "runner": {"repo_relative_path": "tools/run_as_02_03_numeric_bound_v3.py", "sha256": sha(Path(__file__))}, "wrapper_policy": WRAPPER_POLICY, "candidate": {"commit": candidate_commit, "tree": candidate_tree, "archive_sha256": candidate_archive_sha}, "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "archive_sha256": upstream_archive_sha}, "build": {**build, "binary_sha256": sha(binary)}, "toolchain": {"cargo": tool_identity(cargo, "cargo", ("--version",)), "rustc": tool_identity(rustc, "rustc", ("--version",)), "python": tool_identity(python, "python", ("--version",))}, "fixture": {"kind": FIXTURE_KIND, "generated_by_runner_constant": FIXTURE_GENERATED_BY, "sha256": sha(input_path)}, "fixture_sha256": sha(input_path), "execution": {"upstream": upstream_result, "candidate": candidate_result, "upstream_report_sha256": sha(upstream_report), "candidate_report_sha256": sha(candidate_report)}, "metrics": metrics, "non_claims": ["Numeric mismatch remains open.", "No parity or acceptance tolerance is claimed."]}
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return report
    finally:
        shutil.rmtree(stable, ignore_errors=True)
        shutil.rmtree(run_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=["AS-02", "AS-03"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, default=Path.home() / ".cargo/bin/cargo.exe")
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    args = parser.parse_args()
    report = execute(args.row, run_id=args.run_id, report_path=args.report, python=args.python.resolve(), cargo=args.cargo.resolve(), candidate_commit=args.candidate_commit, candidate_tree=args.candidate_tree, candidate_archive_sha256=args.candidate_archive_sha256)
    print(json.dumps({"workflow": args.row, "status": report["status"], "report": args.report.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
