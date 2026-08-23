"""Run a bound COM replay from a clean candidate archive."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


UPSTREAM_REPOSITORY = "https://github.com/z331225718/agent-com.git"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ARCHIVE_SHA256 = "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"
BUILD_TIMEOUT_SECONDS = 300
TOOL_TIMEOUT_SECONDS = 30


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_path(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def load_archived_helper(archive_root: Path):
    path = archive_root / "tools" / "com_direct_semantic_replay.py"
    spec = importlib.util.spec_from_file_location("com_replay_archive_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load archived helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def materialize_archive(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r") as handle:
        for member in handle.getmembers():
            target = (destination / member.name).resolve()
            try:
                target.relative_to(destination)
            except ValueError as error:
                raise RuntimeError("archive contains an escaping member") from error
            if member.issym() or member.islnk():
                raise RuntimeError("archive links are not admitted")
        handle.extractall(destination)


def resolve_executable(path: str, basename: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_file() or resolved.name.lower() != basename.lower():
        raise RuntimeError(f"invalid explicit {basename} executable")
    return resolved


def tool_identity(path: Path, role: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            timeout=TOOL_TIMEOUT_SECONDS,
            check=False,
        )
        output = completed.stdout + completed.stderr
        timed_out = False
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or b"") + (error.stderr or b"")
        completed = None
        timed_out = True
    return {
        "role": role,
        "executable": path.name,
        "file_sha256": digest_path(path),
        "version_output_sha256": digest_bytes(output),
        "version_exit_code": None if completed is None else completed.returncode,
        "path_redacted": True,
        "timeout_seconds": TOOL_TIMEOUT_SECONDS,
        "timed_out": timed_out,
    }


def fixture_bindings(helper: Any) -> dict[str, Any]:
    bindings: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="sipi-com-v2-fixture-") as directory:
        root = Path(directory)
        for scenario in helper.PORTABLE_SCENARIOS:
            scenario_root = root / scenario
            scenario_root.mkdir()
            helper.write_fixture(scenario_root, scenario)
            for path in sorted(scenario_root.rglob("*")):
                if path.is_file():
                    bindings.append(
                        {
                            "scenario": scenario,
                            "name": path.relative_to(scenario_root).as_posix(),
                            "bytes": path.stat().st_size,
                            "sha256": digest_path(path),
                        }
                    )
    canonical = json.dumps(bindings, sort_keys=True, separators=(",", ":")).encode()
    return {
        "generator": "archived tools/com_direct_semantic_replay.py::write_fixture",
        "scenario_count": len(helper.PORTABLE_SCENARIOS),
        "inputs": bindings,
        "corpus_sha256": digest_bytes(canonical),
    }


def source_probe(archive_root: Path) -> dict[str, Any]:
    source_path = archive_root / "crates" / "sipi-agent-com-direct" / "src" / "run_v1.rs"
    source = source_path.read_text(encoding="utf-8")
    s2p_start = source.index("fn load_impulse_v1")
    s4p_start = source.index("fn load_s4p_impulse_v1")
    s2p = source[s2p_start:s4p_start]
    s4p = source[s4p_start:source.index("fn load_s4p_calibration_document_v1")]
    return {
        "source": "crates/sipi-agent-com-direct/src/run_v1.rs",
        "source_sha256": digest_path(source_path),
        "s2p_uses_validated_fd_to_td_leaf": "s21_to_impulse_dc_v1" in s2p,
        "s2p_forbids_matched_kernel": "resolve_matched_kernel_v1" not in s2p,
        "s4p_uses_validated_fd_to_td_leaf": "s21_to_impulse_dc_v1" in s4p,
        "s4p_forbids_matched_kernel": "resolve_matched_kernel_v1" not in s4p,
        "s_parameter_fit": "forbidden",
    }


def run_build(archive_root: Path, archive: Path, cargo: Path, rustc: Path, mode: str) -> dict[str, Any]:
    target = archive_root / "target"
    if target.exists():
        shutil.rmtree(target)
    binary_name = "sipi-com-direct-run" if mode == "com-02" else "sipi-com-direct-public-api"
    manifest = archive_root / "crates" / "sipi-agent-com-direct" / "Cargo.toml"
    env = os.environ.copy()
    env.pop("RUSTC_WRAPPER", None)
    env["RUSTC"] = str(rustc)
    env["CARGO_TARGET_DIR"] = str(target)
    env["RUSTC_WRAPPER"] = ""
    completed = subprocess.run(
        [str(cargo), "build", "--manifest-path", str(manifest), "--locked", "--bin", binary_name],
        cwd=archive_root,
        env=env,
        capture_output=True,
        timeout=BUILD_TIMEOUT_SECONDS,
        check=False,
    )
    binary = target / "debug" / f"{binary_name}.exe"
    if completed.returncode != 0 or not binary.is_file():
        raise RuntimeError(f"clean archive build failed: {completed.returncode}")
    return {
        "command": ["cargo", "build", "--manifest-path", "crates/sipi-agent-com-direct/Cargo.toml", "--locked", "--bin", binary_name],
        "returncode": completed.returncode,
        "timeout_seconds": BUILD_TIMEOUT_SECONDS,
        "timed_out": False,
        "rustc_wrapper_cleared": True,
        "source_mode": "candidate_git_archive_at_immutable_commit",
        "source_commit": "64b783f66d7e986d0975be5ac3946b453b15c4ed",
        "source_tree": "0e11721f2bb5b564002820cc7a5aaab45e30ba3b",
        "archive_sha256": digest_path(archive),
        "stdout_sha256": digest_bytes(completed.stdout),
        "stderr_sha256": digest_bytes(completed.stderr),
        "binary": {
            "path": f"target/debug/{binary_name}.exe",
            "bytes": binary.stat().st_size,
            "sha256": digest_path(binary),
        },
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    archive = args.archive.resolve()
    cargo = resolve_executable(args.cargo, "cargo.exe")
    rustc = resolve_executable(args.rustc, "rustc.exe")
    with TemporaryDirectory(prefix="sipi-com-v2-candidate-") as directory:
        archive_root = Path(directory)
        materialize_archive(archive, archive_root)
        helper, helper_path = load_archived_helper(archive_root)
        runner_name = "run_com_02_direct_semantic_replay.py" if args.mode == "com-02" else "run_com_04_direct_semantic_replay.py"
        build = run_build(archive_root, archive, cargo, rustc, args.mode)
        binary = archive_root / build["binary"]["path"]
        nonce = secrets.token_hex(32)
        run_id = f"{args.mode}-v2-fresh-{args.fresh_run_index}-{nonce}"
        report = helper.redact_for_report(helper.run_report(binary, args.mode, run_id))
        report["schema"] = f"sipi.{args.mode}.direct-semantic-replay.v2"
        report["candidate"] = {
            "status": "bound_clean_git_archive",
            "commit": "64b783f66d7e986d0975be5ac3946b453b15c4ed",
            "tree": "0e11721f2bb5b564002820cc7a5aaab45e30ba3b",
            "archive_sha256": digest_path(archive),
            "archive_bytes": archive.stat().st_size,
            "materialization": "git archive; no working-tree overlay",
            "binary": build["binary"]["path"],
            "binary_sha256": build["binary"]["sha256"],
            "binary_bytes": build["binary"]["bytes"],
        }
        report["execution_binding"] = {
            "run_id": run_id,
            "fresh_run_index": args.fresh_run_index,
            "nonce": nonce,
            "runner": {"path": f"tools/{runner_name}", "sha256": digest_path(archive_root / "tools" / runner_name)},
            "helper": {"path": "tools/com_direct_semantic_replay.py", "sha256": digest_path(helper_path)},
            "v2_wrapper": {"path": "tools/com_direct_semantic_replay_v2.py", "sha256": digest_path(Path(__file__))},
            "fixture": fixture_bindings(helper),
            "toolchain": {
                "cargo": tool_identity(cargo, "cargo"),
                "rustc": tool_identity(rustc, "rustc"),
                "path_redacted": True,
            },
            "build": build,
            "source_probe": source_probe(archive_root),
        }
        report["upstream"] = {
            "repository": UPSTREAM_REPOSITORY,
            "commit": UPSTREAM_COMMIT,
            "tree": UPSTREAM_TREE,
            "declared_license": "MIT",
            "archive_sha256": UPSTREAM_ARCHIVE_SHA256,
            "source_map": f"crates/sipi-agent-com-direct/SOURCE-MAP-{args.mode.upper()}.md",
            "materialization": "git archive at immutable commit metadata-only",
            "runtime_executed": False,
        }
        report["parity"] = {
            "status": "semantic_replay_only",
            "numeric_upstream_parity_claim": False,
            "external_blockers": ["matlab_engine", "proprietary_golden", "plotting_format"],
        }
        return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--mode", choices=("com-02", "com-04"), required=True)
    parser.add_argument("--fresh-run-index", type=int, required=True)
    parser.add_argument("--cargo", required=True)
    parser.add_argument("--rustc", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": report["schema"], "report_sha256": digest_path(args.report), "nonce": report["execution_binding"]["nonce"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
