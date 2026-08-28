"""Run a bound COM replay from a clean candidate archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tarfile
import time
import types
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory, TemporaryFile
from typing import Any


UPSTREAM_REPOSITORY = "https://github.com/z331225718/agent-com.git"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
UPSTREAM_ARCHIVE_SHA256 = "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"
CANDIDATE_COMMIT = "af518684936f8656eda61288abe2647f7d909ea4"
CANDIDATE_TREE = "e49c50407557806c4addae103acbfd576b01527e"
CANDIDATE_ARCHIVE_SHA256 = "3098bb432d8c00c4c65c058cf0f325172112de6c24fb5e55127688d8e147d990"
CANDIDATE_ARCHIVE_BYTES = 54_650_880
BUILD_TIMEOUT_SECONDS = 300
TOOL_TIMEOUT_SECONDS = 30
MAX_HARNESS_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_ARCHIVE_MEMBER_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 256 * 1024 * 1024
MAX_TOOL_OUTPUT_BYTES = 4 * 1024 * 1024


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bounded_regular_bytes(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise RuntimeError(f"symlink is not admitted: {path.name}")
    path = path.resolve(strict=True)
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or path.is_symlink() or before.st_size > limit:
        raise RuntimeError(f"unadmitted bounded regular file: {path.name}")
    with path.open("rb") as handle:
        payload = handle.read(limit + 1)
    after = path.stat(follow_symlinks=False)
    if len(payload) > limit or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        raise RuntimeError(f"file identity drift: {path.name}")
    return payload


def harness_bytes(name: str) -> tuple[Path, bytes]:
    root = Path(__file__).resolve().parent
    path = (root / name).resolve(strict=True)
    if path.parent != root:
        raise RuntimeError("harness path escaped tools directory")
    return path, bounded_regular_bytes(path, MAX_HARNESS_BYTES)


def digest_path(path: Path) -> str:
    return digest_bytes(bounded_regular_bytes(path, MAX_ARCHIVE_TOTAL_BYTES))


def load_harness_helper():
    path, source = harness_bytes("com_direct_semantic_replay.py")
    module = types.ModuleType("com_replay_prep_v2")
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module, path, digest_bytes(source)


def materialize_archive(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r") as handle:
        members = handle.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise RuntimeError("archive member budget exceeded")
        total = 0
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or "\\" in member.name or not member.name:
                raise RuntimeError("archive contains a non-canonical member name")
            if not (member.isdir() or member.isreg()):
                raise RuntimeError("archive admits only regular files and directories")
            if member.size > MAX_ARCHIVE_MEMBER_BYTES:
                raise RuntimeError("archive member budget exceeded")
            total += member.size
            if total > MAX_ARCHIVE_TOTAL_BYTES:
                raise RuntimeError("archive total budget exceeded")
            target = destination.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                target.mkdir(exist_ok=True)
                continue
            source = handle.extractfile(member)
            if source is None:
                raise RuntimeError("archive regular member has no payload")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def admit_candidate_archive(archive: Path) -> bytes:
    payload = bounded_regular_bytes(archive, CANDIDATE_ARCHIVE_BYTES)
    if len(payload) != CANDIDATE_ARCHIVE_BYTES or digest_bytes(payload) != CANDIDATE_ARCHIVE_SHA256:
        raise RuntimeError("candidate archive identity mismatch")
    return payload


def run_bounded(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int):
    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                raise RuntimeError("subprocess timeout")
            if stdout.tell() > MAX_TOOL_OUTPUT_BYTES or stderr.tell() > MAX_TOOL_OUTPUT_BYTES:
                process.kill()
                process.wait()
                raise RuntimeError("subprocess output budget exceeded")
            time.sleep(0.01)
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(MAX_TOOL_OUTPUT_BYTES + 1)
        err = stderr.read(MAX_TOOL_OUTPUT_BYTES + 1)
        if len(out) > MAX_TOOL_OUTPUT_BYTES or len(err) > MAX_TOOL_OUTPUT_BYTES:
            raise RuntimeError("subprocess output budget exceeded")
        return subprocess.CompletedProcess(command, process.returncode, out, err)


def exactly_one_test_passed(output: str) -> bool:
    lines = output.splitlines()
    running = [line for line in lines if re.fullmatch(r"running \d+ tests?", line)]
    summaries = [line for line in lines if re.fullmatch(r"test result:.*", line)]
    if len(running) != 1 or len(summaries) != 1 or running[0] != "running 1 test":
        return False
    return bool(
        re.fullmatch(
            r"test result: ok\. 1 passed; 0 failed; \d+ ignored; \d+ measured; \d+ filtered out; finished in [0-9.]+s",
            summaries[0],
        )
    )


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
        "generator": "prep-bound tools/com_direct_semantic_replay.py::write_fixture",
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
    completed = run_bounded(
        [str(cargo), "build", "--manifest-path", str(manifest), "--locked", "--bin", binary_name],
        cwd=archive_root,
        env=env,
        timeout=BUILD_TIMEOUT_SECONDS,
    )
    binary = target / "debug" / f"{binary_name}.exe"
    if completed.returncode != 0 or not binary.is_file():
        raise RuntimeError(f"clean archive build failed: {completed.returncode}")
    exact_test = "package_vtf_v1::tests::workbook_snp_port_order_is_applied_before_mixed_mode"
    port_order_test = run_bounded(
        [
            str(cargo),
            "test",
            "--manifest-path",
            str(manifest),
            "--lib",
            exact_test,
            "--",
            "--exact",
        ],
        cwd=archive_root,
        env=env,
        timeout=BUILD_TIMEOUT_SECONDS,
    )
    test_output = (port_order_test.stdout + port_order_test.stderr).decode("utf-8", "replace")
    if port_order_test.returncode != 0 or not exactly_one_test_passed(test_output):
        raise RuntimeError("trusted-workbook snpPortsOrder execution observation failed")
    return {
        "command": ["cargo", "build", "--manifest-path", "crates/sipi-agent-com-direct/Cargo.toml", "--locked", "--bin", binary_name],
        "returncode": completed.returncode,
        "timeout_seconds": BUILD_TIMEOUT_SECONDS,
        "timed_out": False,
        "rustc_wrapper_cleared": True,
        "source_mode": "candidate_git_archive_at_immutable_commit",
        "source_commit": CANDIDATE_COMMIT,
        "source_tree": CANDIDATE_TREE,
        "archive_sha256": digest_path(archive),
        "stdout_sha256": digest_bytes(completed.stdout),
        "stderr_sha256": digest_bytes(completed.stderr),
        "binary": {
            "path": f"target/debug/{binary_name}.exe",
            "bytes": binary.stat().st_size,
            "sha256": digest_path(binary),
        },
        "candidate_execution_observations": {
            "trusted_workbook_snp_port_order": {
                "kind": "focused_rust_test",
                "test": exact_test,
                "returncode": port_order_test.returncode,
                "stdout_sha256": digest_bytes(port_order_test.stdout),
                "stderr_sha256": digest_bytes(port_order_test.stderr),
                "serialized_result_field": None,
            }
        },
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    archive = args.archive.resolve()
    admit_candidate_archive(archive)
    cargo = resolve_executable(args.cargo, "cargo.exe")
    rustc = resolve_executable(args.rustc, "rustc.exe")
    with TemporaryDirectory(prefix="sipi-com-v2-candidate-") as directory:
        archive_root = Path(directory)
        materialize_archive(archive, archive_root)
        helper, helper_path, helper_sha256 = load_harness_helper()
        runner_name = "run_com_02_direct_semantic_replay.py" if args.mode == "com-02" else "run_com_04_direct_semantic_replay.py"
        _, runner_source = harness_bytes(runner_name)
        _, wrapper_source = harness_bytes(Path(__file__).name)
        runner_sha256 = digest_bytes(runner_source)
        wrapper_sha256 = digest_bytes(wrapper_source)
        build = run_build(archive_root, archive, cargo, rustc, args.mode)
        binary = archive_root / build["binary"]["path"]
        nonce = secrets.token_hex(32)
        run_id = f"{args.mode}-v2-fresh-{args.fresh_run_index}-{nonce}"
        report = helper.redact_for_report(helper.run_report(binary, args.mode, run_id))
        report["schema"] = f"sipi.{args.mode}.direct-semantic-replay.v2"
        report["candidate"] = {
            "status": "bound_clean_git_archive",
            "commit": CANDIDATE_COMMIT,
            "tree": CANDIDATE_TREE,
            "archive_sha256": digest_path(archive),
            "archive_bytes": CANDIDATE_ARCHIVE_BYTES,
            "materialization": "git archive; no working-tree overlay",
            "binary": build["binary"]["path"],
            "binary_sha256": build["binary"]["sha256"],
            "binary_bytes": build["binary"]["bytes"],
        }
        report["prep_source_inventory"] = {
            "run_id": run_id,
            "fresh_run_index": args.fresh_run_index,
            "nonce": nonce,
            "runner": {"path": f"tools/{runner_name}", "sha256": runner_sha256, "runtime_executed": False},
            "helper": {"path": "tools/com_direct_semantic_replay.py", "sha256": helper_sha256, "runtime_executed": "true-from-snapshot"},
            "v2_wrapper": {"path": "tools/com_direct_semantic_replay_v2.py", "sha256": wrapper_sha256, "runtime_executed": "self_unproven"},
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
    print(json.dumps({"schema": report["schema"], "report_sha256": digest_path(args.report), "nonce": report["prep_source_inventory"]["nonce"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
