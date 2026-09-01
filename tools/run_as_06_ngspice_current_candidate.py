"""Run two immutable AS-06 ngspice replays against an explicit candidate commit.

This is deliberately separate from the historical formal runner.  The
candidate identity is supplied by the caller and is archived before build or
execution, so an uncommitted worktree cannot become the replay input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
import tempfile
from pathlib import Path

import run_as_06_ngspice_result_parity as base


HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_REPORT = 2 * 1024 * 1024


def _hex(value: str) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _identity(path: Path, role: str) -> dict:
    value = base.identity(path, role)
    if value["version_exit"] != 0 or not _hex(value["sha256"]) or not _hex(value["version_sha256"]):
        raise RuntimeError(f"{role} identity is not executable or hashed")
    return value


def _write_report(path: Path, report: dict) -> str:
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_REPORT:
        raise RuntimeError("report exceeds budget")
    with path.open("xb") as stream:
        stream.write(payload)
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--ngspice", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--challenge", required=True)
    args = parser.parse_args()
    if args.output.exists() or not _hex(args.challenge) or len(args.run_id) > 96:
        raise RuntimeError("output must be fresh and challenge/run-id bounded")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sipi-as06-current-") as raw:
        root = Path(raw)
        candidate = root / "candidate"
        upstream = root / "upstream"
        candidate_id = base.archive(args.candidate_repo.resolve(), args.candidate_commit, candidate)
        upstream_id = base.archive(args.upstream_repo.resolve(), base.UPSTREAM_COMMIT, upstream)
        if upstream_id != {
            "commit": base.UPSTREAM_COMMIT,
            "tree": base.UPSTREAM_TREE,
            "sha256": base.UPSTREAM_ARCHIVE_SHA256,
            "bytes": 120238080,
        }:
            raise RuntimeError("pinned upstream archive identity drift")

        source_map = candidate / base.SOURCE_MAP
        base.regular(source_map)
        source_map_sha = base.sha(source_map)
        if source_map_sha != base.SOURCE_MAP_SHA256:
            raise RuntimeError("candidate source-map identity drift")
        for relative in (base.DECK, base.RFM, base.MODEL):
            base.regular(upstream / relative)

        cargo = args.cargo.resolve(strict=True)
        python = args.python.resolve(strict=True)
        rustc = args.rustc.resolve(strict=True)
        ngspice = args.ngspice.resolve(strict=True)
        toolchain_pre = {
            "cargo": _identity(cargo, "cargo"),
            "rustc": _identity(rustc, "rustc"),
            "python": _identity(python, "python"),
            "ngspice": _identity(ngspice, "ngspice"),
        }
        if toolchain_pre["ngspice"]["sha256"] != base.NGSPICE_SHA256:
            raise RuntimeError("ngspice identity drift")
        inputs = {
            "deck_sha256": base.sha(upstream / base.DECK),
            "rfm_sha256": base.sha(upstream / base.RFM),
            "code_model_sha256": base.sha(upstream / base.MODEL),
            "ngspice_sha256": base.sha(ngspice),
        }
        expected_inputs = {
            "deck_sha256": base.DECK_SHA256,
            "rfm_sha256": base.RFM_SHA256,
            "code_model_sha256": base.MODEL_SHA256,
            "ngspice_sha256": base.NGSPICE_SHA256,
        }
        if inputs != expected_inputs:
            raise RuntimeError("pinned replay input identity drift")

        target = root / "target"
        env = base.build_environment(rustc, target)
        base.run(
            [
                str(cargo),
                "build",
                "--locked",
                "--offline",
                "--manifest-path",
                str(candidate / "crates/sipi-agent-spice-direct/Cargo.toml"),
                "--bin",
                "sipi-agent-spice-run-rfm",
            ],
            cwd=candidate,
            env=env,
        )
        rust_bin = target / "debug" / (
            "sipi-agent-spice-run-rfm.exe" if sys.platform == "win32" else "sipi-agent-spice-run-rfm"
        )
        base.regular(rust_bin)
        binary_pre = base.receipt(rust_bin)
        dependency_pre = base.rlib_inventory(target / "debug/deps")
        rust_out = root / "rust-out"
        upstream_out = root / "upstream-out"
        base.run(
            [
                str(rust_bin),
                str(upstream / base.DECK),
                "--rfm",
                str(upstream / base.RFM),
                "--backend",
                "ngspice",
                "--output-root",
                str(rust_out),
                "--ngspice",
                str(ngspice),
                "--ngspice-sha256",
                inputs["ngspice_sha256"],
                "--code-model",
                str(upstream / base.MODEL),
                "--code-model-sha256",
                inputs["code_model_sha256"],
                "--execute",
            ],
            cwd=candidate,
            env=env,
        )
        python_env = dict(env)
        python_env["PYTHONPATH"] = str(upstream / "src")
        base.run(
            [
                str(python),
                "-m",
                "agent_spice.cli",
                "run-rfm",
                str(upstream / base.DECK),
                "--rfm",
                str(upstream / base.RFM),
                "--backend",
                "ngspice",
                "--ngspice",
                str(ngspice),
                "--code-model",
                str(upstream / base.MODEL),
                "--output-root",
                str(upstream_out),
                "--execute",
            ],
            cwd=upstream,
            env=python_env,
        )

        rust_run = rust_out / "direct-rfm-example" / "rfm_direct"
        upstream_run = upstream_out / "direct-rfm-example" / "rfm_direct"
        header_a, rows_a = base.load_csv(rust_run / "waveform.csv")
        header_b, rows_b = base.load_csv(upstream_run / "waveform.csv")
        differences = [
            abs(a - b) for left, right in zip(rows_a, rows_b) for a, b in zip(left, right)
        ]
        bit_exact = (
            header_a == header_b
            and len(rows_a) == len(rows_b)
            and all(
                a.hex() == b.hex()
                for left, right in zip(rows_a, rows_b)
                for a, b in zip(left, right)
            )
        )
        rust_manifest = json.loads((rust_run / "rfm_run_manifest.json").read_text(encoding="utf-8"))
        upstream_manifest = json.loads(
            (upstream_run / "rfm_run_manifest.json").read_text(encoding="utf-8")
        )
        logical_keys = [
            "schema_version",
            "execution_path",
            "refit_performed",
            "reference_mode",
            "subcircuit_name",
            "model",
            "inputs",
            "artifacts",
        ]
        logical_manifest_equal = all(
            rust_manifest[key] == upstream_manifest[key] for key in logical_keys
        )
        runtime_keys = [
            "path",
            "normalization",
            "verification_samples",
            "reconstruction_rms",
            "reconstruction_max",
        ]
        runtime_semantics_equal = all(
            rust_manifest["runtime_rfm"][key] == upstream_manifest["runtime_rfm"][key]
            for key in runtime_keys
        )
        toolchain_post = {
            "cargo": _identity(cargo, "cargo"),
            "rustc": _identity(rustc, "rustc"),
            "python": _identity(python, "python"),
            "ngspice": _identity(ngspice, "ngspice"),
        }
        binary_post = base.receipt(rust_bin)
        dependency_post = base.rlib_inventory(target / "debug/deps")
        if toolchain_pre != toolchain_post or dependency_pre != dependency_post:
            raise RuntimeError("toolchain or dependency inventory changed during replay")

        claims = {
            "external_solver_scoped_observation": True,
            "solver_correctness": False,
            "release_acceptance": False,
            "s_parameter_fit": False,
            "as05_xyce_xdm": False,
            "environment_injection_resistance": False,
            "hostile_writer_resistance": False,
        }
        result = {
            "headers": header_a,
            "waveform_rows": len(rows_a),
            "float_bit_exact": bit_exact,
            "max_abs_error": max(differences, default=0.0),
            "logical_manifest_equal": logical_manifest_equal,
            "runtime_semantics_equal": runtime_semantics_equal,
            "rust_reconstruction_rms": rust_manifest["runtime_rfm"]["reconstruction_rms"],
            "upstream_reconstruction_rms": upstream_manifest["runtime_rfm"]["reconstruction_rms"],
            "rust_reconstruction_max": rust_manifest["runtime_rfm"]["reconstruction_max"],
            "upstream_reconstruction_max": upstream_manifest["runtime_rfm"]["reconstruction_max"],
        }
        report = {
            "schema": "sipi.as-06-ngspice-current-candidate.v1",
            "status": "passed"
            if bit_exact and logical_manifest_equal and runtime_semantics_equal and len(rows_a) == 1029
            else "blocked",
            "run_id": args.run_id,
            "caller_challenge": args.challenge,
            "fresh_run_nonce": secrets.token_hex(32),
            "runner_sha256": base.sha(Path(__file__).resolve()),
            "candidate": candidate_id,
            "upstream": upstream_id,
            "toolchain_pre": toolchain_pre,
            "toolchain_post": toolchain_post,
            "binary_pre": binary_pre,
            "binary_post": binary_post,
            "dependency_pre": dependency_pre,
            "dependency_post": dependency_post,
            "environment": {
                "policy": "cargo_rust_python_uv_pip_spice_prefixes_removed",
                "cargo_target_fresh": True,
            },
            "source_map": {"path": base.SOURCE_MAP, "sha256": source_map_sha},
            "inputs": inputs,
            "physical": {
                "rust_waveform": base.receipt(rust_run / "waveform.csv"),
                "upstream_waveform": base.receipt(upstream_run / "waveform.csv"),
                "rust_manifest": base.receipt(rust_run / "rfm_run_manifest.json"),
                "upstream_manifest": base.receipt(upstream_run / "rfm_run_manifest.json"),
                "rust_stdout": base.receipt(rust_run / "stdout.log"),
                "upstream_stdout": base.receipt(upstream_run / "stdout.log"),
            },
            "canonical": {
                "rust_f64_sha256": base.canonical_f64_digest(header_a, rows_a),
                "upstream_f64_sha256": base.canonical_f64_digest(header_b, rows_b),
            },
            "result": result,
            "claims": claims,
        }
        report_sha = _write_report(args.output, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "sha256": report_sha,
                    "candidate": candidate_id["commit"],
                    "rows": len(rows_a),
                    "max_abs_error": result["max_abs_error"],
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
