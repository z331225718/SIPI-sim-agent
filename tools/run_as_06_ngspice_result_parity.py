"""Run one fresh AS-06 Rust versus pinned Agent-Spice ngspice replay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path

CANDIDATE_COMMIT = "aea546510d345cd7e280e55897c027be872d759a"
CANDIDATE_TREE = "df99e5bb1c2381bb52fe0037b7b8fbb38b7c6cb9"
CANDIDATE_ARCHIVE_SHA256 = "4da4772366c49330679c85626b63eeccd3234643303d04bcd9b657c0d9eff326"
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
UPSTREAM_ARCHIVE_SHA256 = "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144"
NGSPICE_SHA256 = "86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453"
MODEL_SHA256 = "a23fa36d39328c8a000eb405a66cd293dae6015f3f50df09c4ea887faa104bab"
DECK_SHA256 = "4c9bcfe30462ca61c62d9ecba9c50d73311f5e18b57cc6afe7e58c76f2b56e5a"
RFM_SHA256 = "894b5da3aba954d3d288689458be99d7434db966b4df4675db52165c4db2b55d"
SOURCE_MAP_SHA256 = "9c96655e08fce504ae936b4e0c0cfb93a53ceafee7f0a3a9f848e1add0239304"
DECK = "artifacts/rfm-ngspice-poc/product-run/direct-rfm-example.sp"
RFM = "artifacts/rfm-ngspice-poc/source-fit/source_model.rfm"
MODEL = "src/agent_spice/lib/ngspice/rfm.cm"
SOURCE_MAP = "docs/baselines/as-06-run-rfm-source-map.v4.yaml"
MAX_REPORT = 2 * 1024 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def re_full_hex(value: str) -> bool:
    return HEX64.fullmatch(value) is not None


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(repo: Path, *args: str, binary: bool = False):
    value = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return value.stdout if binary else value.stdout.decode("ascii").strip()


def archive(repo: Path, commit: str, destination: Path) -> dict:
    payload = git(repo, "archive", "--format=tar", commit, binary=True)
    digest = hashlib.sha256(payload).hexdigest()
    tar_path = destination.parent / f"{destination.name}.tar"
    tar_path.write_bytes(payload)
    destination.mkdir()
    with tarfile.open(tar_path, "r:") as bundle:
        for member in bundle.getmembers():
            if member.issym() or member.islnk() or member.name.startswith(("/", "\\")) or ".." in Path(member.name).parts:
                raise RuntimeError("archive contains unsafe member")
        bundle.extractall(destination, filter="data")
    tar_path.unlink()
    return {"commit": commit, "tree": git(repo, "rev-parse", f"{commit}^{{tree}}"), "sha256": digest, "bytes": len(payload)}


def regular(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise RuntimeError(f"not a regular file: {path.name}")


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {result.stderr[-2000:]!r}")
    return result


def load_csv(path: Path) -> tuple[list[str], list[list[float]]]:
    regular(path)
    with path.open("r", encoding="ascii", newline="") as stream:
        rows = list(csv.reader(stream))
    if not rows or rows[0] != ["time", "v(src)", "v(out)"]:
        raise RuntimeError("unexpected waveform schema")
    values = [[float(cell) for cell in row] for row in rows[1:]]
    if any(len(row) != 3 for row in values) or any(not math.isfinite(value) for row in values for value in row):
        raise RuntimeError("unexpected waveform width")
    return rows[0], values


def receipt(path: Path) -> dict:
    regular(path)
    info = path.stat()
    return {"basename": path.name, "bytes": info.st_size, "sha256": sha(path), "nlink": info.st_nlink, "path_redacted": True}


def canonical_f64_digest(header: list[str], rows: list[list[float]]) -> str:
    payload = json.dumps({"header": header, "rows": [[value.hex() for value in row] for row in rows]}, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def rlib_inventory(root: Path) -> dict:
    entries = []
    for path in sorted(root.glob("*.rlib"), key=lambda value: value.name):
        item = receipt(path)
        entries.append({"basename": item["basename"], "bytes": item["bytes"], "sha256": item["sha256"]})
    if not entries:
        raise RuntimeError("compiled dependency inventory is empty")
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("ascii")
    return {"files": len(entries), "bytes": sum(item["bytes"] for item in entries), "sha256": hashlib.sha256(payload).hexdigest(), "path_redacted": True}


def identity(path: Path, role: str) -> dict:
    resolved = path.resolve(strict=True)
    regular(resolved)
    version = subprocess.run([str(resolved), "--version"], capture_output=True, timeout=30)
    return {"role": role, "basename": resolved.name, "sha256": sha(resolved), "version_exit": version.returncode, "version_sha256": hashlib.sha256(version.stdout + version.stderr).hexdigest(), "path_redacted": True}


def build_environment(rustc: Path, target: Path) -> dict[str, str]:
    rejected_prefixes = ("CARGO", "RUST", "RUSTDOC", "PYTHON", "PIP", "UV", "SPICE", "NGSPICE")
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(rejected_prefixes)}
    env["CARGO_TARGET_DIR"] = str(target)
    env["RUSTC"] = str(rustc)
    env.pop("RUSTC_WRAPPER", None)
    env.pop("RUSTC_WORKSPACE_WRAPPER", None)
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--ngspice", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--challenge", required=True)
    args = parser.parse_args()
    if args.output.exists() or len(args.run_id) > 96 or not re_full_hex(args.challenge):
        raise RuntimeError("output must be fresh and run-id bounded")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="sipi-as06-result-") as raw:
        root = Path(raw)
        candidate = root / "candidate"
        upstream = root / "upstream"
        candidate_id = archive(args.candidate_repo.resolve(), CANDIDATE_COMMIT, candidate)
        upstream_id = archive(args.upstream_repo.resolve(), UPSTREAM_COMMIT, upstream)
        if candidate_id != {"commit": CANDIDATE_COMMIT, "tree": CANDIDATE_TREE, "sha256": CANDIDATE_ARCHIVE_SHA256, "bytes": 54640640} or upstream_id != {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE, "sha256": UPSTREAM_ARCHIVE_SHA256, "bytes": 120238080}:
            raise RuntimeError("pinned archive identity drift")
        for relative in (DECK, RFM, MODEL):
            regular(upstream / relative)
        regular(candidate / SOURCE_MAP)
        cargo = args.cargo.resolve(strict=True)
        python = args.python.resolve(strict=True)
        rustc = args.rustc.resolve(strict=True)
        ngspice = args.ngspice.resolve(strict=True)
        toolchain_pre = {"cargo": identity(cargo, "cargo"), "rustc": identity(rustc, "rustc"), "python": identity(python, "python"), "ngspice": identity(ngspice, "ngspice")}
        if toolchain_pre["ngspice"]["sha256"] != NGSPICE_SHA256:
            raise RuntimeError("ngspice-46 expected SHA-256 drift")
        target = root / "target"
        env = build_environment(rustc, target)
        run([str(cargo), "build", "--locked", "--offline", "--manifest-path", str(candidate / "crates/sipi-agent-spice-direct/Cargo.toml"), "--bin", "sipi-agent-spice-run-rfm"], cwd=candidate, env=env)
        rust_bin = target / "debug" / ("sipi-agent-spice-run-rfm.exe" if os.name == "nt" else "sipi-agent-spice-run-rfm")
        regular(rust_bin)
        binary_pre = receipt(rust_bin)
        dependency_pre = rlib_inventory(target / "debug/deps")
        rust_out = root / "rust-out"
        upstream_out = root / "upstream-out"
        model_sha = sha(upstream / MODEL)
        ngspice_sha = sha(ngspice)
        if model_sha != MODEL_SHA256 or sha(upstream / DECK) != DECK_SHA256 or sha(upstream / RFM) != RFM_SHA256 or sha(candidate / SOURCE_MAP) != SOURCE_MAP_SHA256:
            raise RuntimeError("pinned input identity drift")
        run([str(rust_bin), str(upstream / DECK), "--rfm", str(upstream / RFM), "--backend", "ngspice", "--output-root", str(rust_out), "--ngspice", str(ngspice), "--ngspice-sha256", ngspice_sha, "--code-model", str(upstream / MODEL), "--code-model-sha256", model_sha, "--execute"], cwd=candidate, env=env)
        pyenv = dict(env)
        pyenv["PYTHONPATH"] = str(upstream / "src")
        run([str(python), "-m", "agent_spice.cli", "run-rfm", str(upstream / DECK), "--rfm", str(upstream / RFM), "--backend", "ngspice", "--ngspice", str(ngspice), "--code-model", str(upstream / MODEL), "--output-root", str(upstream_out), "--execute"], cwd=upstream, env=pyenv)
        rust_run = rust_out / "direct-rfm-example/rfm_direct"
        upstream_run = upstream_out / "direct-rfm-example/rfm_direct"
        header_a, rows_a = load_csv(rust_run / "waveform.csv")
        header_b, rows_b = load_csv(upstream_run / "waveform.csv")
        if header_a != header_b or len(rows_a) != len(rows_b):
            raise RuntimeError("waveform shape drift")
        differences = [abs(a - b) for left, right in zip(rows_a, rows_b) for a, b in zip(left, right)]
        bit_exact = all(a.hex() == b.hex() for left, right in zip(rows_a, rows_b) for a, b in zip(left, right))
        rust_manifest = json.loads((rust_run / "rfm_run_manifest.json").read_text(encoding="utf-8"))
        upstream_manifest = json.loads((upstream_run / "rfm_run_manifest.json").read_text(encoding="utf-8"))
        logical_keys = ["schema_version", "execution_path", "refit_performed", "reference_mode", "subcircuit_name", "model", "inputs", "artifacts"]
        logical_manifest_equal = all(rust_manifest[key] == upstream_manifest[key] for key in logical_keys)
        runtime_keys = ["path", "normalization", "verification_samples", "reconstruction_rms", "reconstruction_max"]
        runtime_semantics_equal = all(
            rust_manifest["runtime_rfm"][key] == upstream_manifest["runtime_rfm"][key]
            for key in runtime_keys
        )
        toolchain_post = {"cargo": identity(cargo, "cargo"), "rustc": identity(rustc, "rustc"), "python": identity(python, "python"), "ngspice": identity(ngspice, "ngspice")}
        if toolchain_pre != toolchain_post:
            raise RuntimeError("toolchain changed during replay")
        binary_post = receipt(rust_bin)
        dependency_post = rlib_inventory(target / "debug/deps")
        if dependency_pre != dependency_post:
            raise RuntimeError("compiled dependency inventory changed during replay")
        physical = {"rust_waveform": receipt(rust_run / "waveform.csv"), "upstream_waveform": receipt(upstream_run / "waveform.csv"), "rust_manifest": receipt(rust_run / "rfm_run_manifest.json"), "upstream_manifest": receipt(upstream_run / "rfm_run_manifest.json"), "rust_stdout": receipt(rust_run / "stdout.log"), "upstream_stdout": receipt(upstream_run / "stdout.log")}
        report = {"schema": "sipi.as-06-ngspice-result-parity.v2", "status": "passed" if bit_exact and logical_manifest_equal and runtime_semantics_equal and len(rows_a) == 1029 else "blocked", "run_id": args.run_id, "caller_challenge": args.challenge, "fresh_run_nonce": nonce, "runner_sha256": sha(Path(__file__).resolve()), "candidate": candidate_id, "upstream": upstream_id, "toolchain_pre": toolchain_pre, "toolchain_post": toolchain_post, "binary_pre": binary_pre, "binary_post": binary_post, "environment": {"policy": "cargo_rust_python_uv_pip_spice_prefixes_removed", "cargo_target_fresh": True}, "source_map": {"path": SOURCE_MAP, "sha256": sha(candidate / SOURCE_MAP)}, "inputs": {"deck_sha256": sha(upstream / DECK), "rfm_sha256": sha(upstream / RFM), "code_model_sha256": model_sha, "ngspice_sha256": ngspice_sha}, "physical": physical, "canonical": {"rust_f64_sha256": canonical_f64_digest(header_a, rows_a), "upstream_f64_sha256": canonical_f64_digest(header_b, rows_b)}, "result": {"headers": header_a, "waveform_rows": len(rows_a), "float_bit_exact": bit_exact, "max_abs_error": max(differences, default=0.0), "logical_manifest_equal": logical_manifest_equal, "runtime_semantics_equal": runtime_semantics_equal, "rust_reconstruction_rms": rust_manifest["runtime_rfm"]["reconstruction_rms"], "upstream_reconstruction_rms": upstream_manifest["runtime_rfm"]["reconstruction_rms"], "rust_reconstruction_max": rust_manifest["runtime_rfm"]["reconstruction_max"], "upstream_reconstruction_max": upstream_manifest["runtime_rfm"]["reconstruction_max"]}, "claims": {"external_solver_scoped_observation": True, "solver_correctness": False, "release_acceptance": False, "s_parameter_fit": False, "as05_xyce_xdm": False, "environment_injection_resistance": False, "hostile_writer_resistance": False}}
        report["dependency_pre"] = dependency_pre
        report["dependency_post"] = dependency_post
        payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if len(payload) > MAX_REPORT:
            raise RuntimeError("report exceeds budget")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(payload)
        print(json.dumps({"status": report["status"], "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(rows_a), "max_abs_error": max(differences, default=0.0)}, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
