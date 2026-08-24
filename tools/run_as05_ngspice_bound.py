"""Clean-archive AS-05 ngspice scoped-observation preparation runner."""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
FIXTURE_GENERATOR = "tools/run_as05_ngspice_bound.py::fixtures_v1"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_VERSION_BYTES = 64 * 1024
COMMAND_TIMEOUT_SECONDS = 600
VERSION_TIMEOUT_SECONDS = 10
FIXTURES = (
    ("uppercase_tran", "uppercase_tran_v1", "AS05 uppercase tran\nV1 IN 0 1\nR1 IN OUT 1K\nC1 OUT 0 1N\n.TRAN 1E-17 1E-17\n.PRINT TRAN V(OUT)\n.MEASURE TRAN M_RMS FIND V(OUT) AT=0\n.END\n"),
    ("measure_only", "measure_only_v1", "AS05 measure only\nV1 IN 0 1\nR1 IN OUT 1K\nC1 OUT 0 1N\n.TRAN 1E-17 1E-17\n.MEASURE TRAN M_ONLY FIND V(OUT) AT=0\n.END\n"),
)
IDENTITY_FIELDS = ("role", "basename", "path_redacted", "file_sha256", "file_bytes", "version_exit_code", "version_output_sha256", "version_output_bytes", "timeout_seconds", "max_output_bytes")
CONSUMED_INPUT_KEYS = {"path", "bytes", "sha256"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report_sha(path: Path) -> str:
    return sha(read_bounded(path, MAX_REPORT_BYTES))


def read_bounded(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > limit:
        raise RuntimeError(f"file exceeds bounded budget: {path.name}")
    chunks: list[bytes] = []
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise RuntimeError(f"file exceeds bounded budget: {path.name}")
            chunks.append(chunk)
    return b"".join(chunks)


def run_command(command: list[str], *, cwd: Path | None, timeout: int, output_limit: int, env: dict[str, str] | None = None) -> tuple[int, bytes, bytes]:
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    lock = threading.Lock()
    overflow = threading.Event()

    def drain(name: str, stream: Any) -> None:
        nonlocal total
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            with lock:
                total += len(chunk)
                if total > output_limit:
                    overflow.set()
                    if process.poll() is None:
                        process.kill()
                    return
                output[name].extend(chunk)

    threads = [threading.Thread(target=drain, args=(name, getattr(process, name)), daemon=True) for name in ("stdout", "stderr")]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        code = 124
    else:
        code = process.returncode
    if overflow.is_set() and process.poll() is None:
        process.kill()
        process.wait()
    for thread in threads:
        thread.join(timeout=5)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    if overflow.is_set():
        return 125, bytes(output["stdout"]), bytes(output["stderr"])
    return code, bytes(output["stdout"]), bytes(output["stderr"])


def safe_absolute(path: Path) -> bool:
    """Reject Windows drive-relative and UNC spellings before Path normalization."""
    raw = str(path).replace("\\", "/")
    return path.is_absolute() and not re.match(r"^(?:[A-Za-z]:[^/]|//)", raw)


@lru_cache(maxsize=1)
def git_executable() -> Path:
    path = shutil.which("git")
    if not path:
        raise RuntimeError("git executable is unavailable")
    return Path(path).resolve()


def git(repo: Path, *args: str, output_limit: int = MAX_ARCHIVE_BYTES, executable: Path | None = None) -> bytes:
    code, stdout, stderr = run_command([str(executable or git_executable()), "-C", str(repo), *args], cwd=None, timeout=60, output_limit=output_limit)
    if code != 0:
        raise RuntimeError(f"git failed: {stderr.decode(errors='replace')[:512]}")
    return stdout


def materialize_archive(repo: Path, revision: str, destination: Path, executable: Path | None = None) -> str:
    payload = git(repo, "archive", "--format=tar", revision, executable=executable)
    destination.mkdir()
    root = destination.resolve()
    with tarfile.open(fileobj=__import__("io").BytesIO(payload), mode="r:") as tar:
        members = tar.getmembers()
        for member in members:
            raw_name = member.name.replace("\\", "/")
            name = Path(raw_name)
            if (name.is_absolute() or raw_name.startswith("/") or raw_name.startswith("//")
                    or re.match(r"^[A-Za-z]:", raw_name) or ".." in name.parts
                    or member.issym() or member.islnk()):
                raise RuntimeError("unsafe git archive member")
            target = (root / name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("git archive member escapes candidate root")
            if not (member.isdir() or member.isfile()):
                raise RuntimeError("unsupported git archive member type")
        tar.extractall(root)
    for path in root.rglob("*"):
        if path.is_symlink() or (path.is_file() and path.stat().st_size > MAX_FILE_BYTES):
            raise RuntimeError("unsafe or overbudget archive materialization")
    return sha(payload)


def tool_identity(path: Path, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    data = read_bounded(path)
    code, stdout, stderr = run_command([str(path), *version_args], cwd=None, timeout=VERSION_TIMEOUT_SECONDS, output_limit=MAX_VERSION_BYTES)
    return {
        "role": role,
        "basename": path.name,
        "path_redacted": True,
        "file_sha256": sha(data),
        "file_bytes": len(data),
        "version_exit_code": code,
        "version_output_sha256": sha(stdout + b"\0" + stderr),
        "version_output_bytes": len(stdout) + len(stderr),
        "timeout_seconds": VERSION_TIMEOUT_SECONDS,
        "max_output_bytes": MAX_VERSION_BYTES,
    }


def identity_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(left.get(field) == right.get(field) for field in IDENTITY_FIELDS)


def toolchain_identities(git_path: Path, cargo: Path, rustc: Path, python: Path) -> dict[str, dict[str, Any]]:
    return {role: tool_identity(path, role, version_args) for role, path, version_args in (("git", git_path, ("--version",)), ("cargo", cargo, ("--version",)), ("rustc", rustc, ("--version",)), ("python", python, ("--version",)))}


def runner_custody(runtime_path: Path, archive_path: Path, expected_sha256: str) -> bool:
    if (runtime_path.is_symlink() or not runtime_path.is_file()
            or archive_path.is_symlink() or not archive_path.is_file()):
        return False
    return sha(read_bounded(runtime_path)) == expected_sha256 == sha(read_bounded(archive_path))


def fixture_records(root: Path) -> list[dict[str, Any]]:
    fixture_root = root / "fixtures"
    fixture_root.mkdir()
    records = []
    for fixture_id, kind, text in FIXTURES:
        data = text.encode("ascii")
        path = fixture_root / f"{fixture_id}.sp"
        path.write_bytes(data)
        records.append({"id": fixture_id, "kind": kind, "generated_by_runner": FIXTURE_GENERATOR, "path": f"fixtures/{fixture_id}.sp", "bytes": len(data), "sha256": sha(data)})
    return records


def physical(path: Path, relative: str, root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if path.is_symlink() or (resolved_path != resolved_root and resolved_root not in resolved_path.parents):
        raise RuntimeError("external artifact is symlinked or escapes case root")
    data = read_bounded(path)
    return {"path": relative, "bytes": len(data), "sha256": sha(data)}


def run_case(candidate_root: Path, run_root: Path, fixture: dict[str, Any], solver: Path, solver_sha256: str, binary: Path, binary_snapshot: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    output_root = run_root / "out"
    deck = run_root / fixture["path"]
    if not deck.is_file() or deck.is_symlink():
        raise RuntimeError(f"fixture input is not a regular file: {fixture['id']}")
    input_before = physical(deck, fixture["path"], run_root)
    if input_before != {key: fixture[key] for key in ("path", "bytes", "sha256")}:
        raise RuntimeError(f"fixture input changed before execution: {fixture['id']}")
    if not binary.is_file() or binary.is_symlink() or physical(binary, "binary", candidate_root) != binary_snapshot:
        raise RuntimeError("candidate binary is not the attested regular file")
    code, stdout, stderr = run_command([str(binary), str(deck), "--backend", "ngspice", "--output-root", str(output_root), "--execute", "--ngspice", str(solver), "--ngspice-sha256", solver_sha256], cwd=candidate_root, timeout=180, output_limit=MAX_VERSION_BYTES, env=env)
    case_root = output_root / fixture["id"] / f"{fixture['id']}__base"
    summary_path = case_root / "run_summary.json"
    report_path = output_root / fixture["id"] / "run_report.json"
    if not summary_path.is_file() or not report_path.is_file():
        raise RuntimeError(f"Rust AS-05 output contract missing for {fixture['id']}")
    input_after = physical(deck, fixture["path"], run_root)
    if input_after != input_before:
        raise RuntimeError(f"fixture input changed during execution: {fixture['id']}")
    summary_data = read_bounded(summary_path, MAX_REPORT_BYTES)
    report_data = read_bounded(report_path, MAX_REPORT_BYTES)
    summary = json.loads(summary_data.decode("utf-8"))
    run_report = json.loads(report_data.decode("utf-8"))
    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, list):
        raise RuntimeError(f"Rust AS-05 artifact contract missing for {fixture['id']}")
    artifact_records = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise RuntimeError(f"Rust AS-05 artifact contract is not an object for {fixture['id']}")
        relative_path = artifact.get("path")
        if not isinstance(relative_path, str) or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise RuntimeError("Rust AS-05 artifact path escaped case root")
        physical_record = physical(case_root / relative_path, relative_path, case_root)
        if artifact.get("bytes") != physical_record["bytes"] or artifact.get("sha256") != physical_record["sha256"]:
            raise RuntimeError(f"Rust AS-05 summary artifact snapshot disagrees with physical artifact for {fixture['id']}")
        artifact_records.append(physical_record)
    expected_artifacts = {"case", "stdout.log", "stderr.log"}
    if fixture["id"] == "uppercase_tran":
        expected_artifacts.add("waveform.csv")
    if {item["path"] for item in artifact_records} != expected_artifacts:
        raise RuntimeError(f"Rust AS-05 artifact slots do not match fixed contract for {fixture['id']}")
    waveform = summary.get("waveform")
    waveform_path = case_root / "waveform.csv"
    waveform_record: dict[str, Any] = {"present": waveform_path.is_file(), "path": None, "bytes": 0, "sha256": None}
    if waveform_path.is_file():
        waveform_record.update(physical(waveform_path, "waveform.csv", case_root))
    if physical(binary, "binary", candidate_root) != binary_snapshot:
        raise RuntimeError("candidate binary changed during execution")
    return {
        "id": fixture["id"],
        "kind": fixture["kind"],
        "consumed_input": input_after,
        "returncode": code,
        "cli": {"stdout_bytes": len(stdout), "stdout_sha256": sha(stdout), "stderr_bytes": len(stderr), "stderr_sha256": sha(stderr)},
        "summary": {"path": f"{fixture['id']}/run_summary.json", "bytes": len(summary_data), "sha256": sha(summary_data), "ok": summary.get("ok"), "backend": summary.get("backend"), "external_runtime_sha256": (summary.get("external_runtime") or {}).get("sha256"), "output_contract": summary.get("output_contract"), "measurements": summary.get("measurements"), "waveform_rows": (waveform or {}).get("rows") if isinstance(waveform, dict) else 0, "artifacts": artifact_records},
        "run_report": {"path": f"{fixture['id']}/run_report.json", "bytes": len(report_data), "sha256": sha(report_data), "status": run_report.get("status"), "backend": run_report.get("backend"), "execute": run_report.get("execute")},
        "waveform": waveform_record,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-tree", required=True)
    parser.add_argument("--candidate-archive-sha256", required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--upstream-archive-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--ngspice", type=Path, required=True)
    parser.add_argument("--ngspice-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_path = Path(__file__)
    if runtime_path.is_symlink() or not runtime_path.is_file():
        raise SystemExit("runtime runner must be a regular non-symlink file")
    runtime_path = runtime_path.resolve()
    if not RUN_ID.fullmatch(args.run_id) or not safe_absolute(args.upstream_root) or not safe_absolute(args.ngspice):
        raise SystemExit("run-id and absolute upstream/ngspice paths are required")
    if not re.fullmatch(r"[0-9a-f]{40}", args.candidate_commit) or not re.fullmatch(r"[0-9a-f]{40}", args.candidate_tree):
        raise SystemExit("candidate commit/tree must be lowercase 40-hex identities")
    if not HEX64.fullmatch(args.candidate_archive_sha256) or not HEX64.fullmatch(args.upstream_archive_sha256):
        raise SystemExit("candidate/upstream archive SHA-256 values must be lowercase 64-hex identities")
    if args.output.exists():
        raise SystemExit("output report already exists; create-new semantics reject overwrite")
    solver_sha256 = args.ngspice_sha256.lower()
    if not HEX64.fullmatch(solver_sha256):
        raise SystemExit("ngspice SHA-256 must be 64 lowercase hexadecimal characters")
    expected_runner_sha256 = args.expected_runner_sha256.lower()
    if not HEX64.fullmatch(expected_runner_sha256):
        raise SystemExit("expected runner SHA-256 must be 64 lowercase hexadecimal characters")
    runtime_runner_sha256 = sha(read_bounded(runtime_path))
    if runtime_runner_sha256 != expected_runner_sha256:
        raise SystemExit("runtime runner SHA-256 does not match caller attestation")
    if not args.ngspice.is_file() or args.ngspice.is_symlink() or sha(read_bounded(args.ngspice)) != solver_sha256:
        raise SystemExit("ngspice must be an attested regular non-symlink file")
    git_path = git_executable()
    cargo = Path(shutil.which("cargo") or Path.home() / ".cargo" / "bin" / "cargo.exe").resolve()
    rustc = Path(shutil.which("rustc") or cargo.with_name("rustc.exe")).resolve()
    python = Path(sys.executable).resolve()
    tool_pre = toolchain_identities(git_path, cargo, rustc, python)
    actual_commit = git(ROOT, "rev-parse", args.candidate_commit, executable=git_path).decode().strip()
    actual_tree = git(ROOT, "rev-parse", f"{actual_commit}^{{tree}}", executable=git_path).decode().strip()
    if actual_commit != args.candidate_commit or actual_tree != args.candidate_tree:
        raise SystemExit("candidate commit/tree identity mismatch")
    with tempfile.TemporaryDirectory(prefix="sipi-as05-candidate-") as candidate_temp:
        candidate_root = Path(candidate_temp) / "candidate"
        candidate_archive = materialize_archive(ROOT, actual_commit, candidate_root, git_path)
        if candidate_archive != args.candidate_archive_sha256:
            raise SystemExit("candidate archive SHA-256 mismatch")
        clean_env = os.environ.copy()
        clean_env.pop("RUSTC_WRAPPER", None)
        clean_env.pop("RUSTC_WORKSPACE_WRAPPER", None)
        clean_env.pop("CARGO_BUILD_RUSTC_WRAPPER", None)
        for ambient in ("SPICE_SCRIPTS", "SPICEINIT", "NGSPICE_INPUT_DIR"):
            clean_env.pop(ambient, None)
        target_dir = candidate_root / ".as05-target"
        clean_env["CARGO_TARGET_DIR"] = str(target_dir)
        clean_env["RUSTC"] = str(rustc)
        build_command = [str(cargo), "build", "--offline", "--locked", "--quiet", "--manifest-path", str(candidate_root / "crates/sipi-agent-spice-direct/Cargo.toml"), "--bin", "sipi-agent-spice-run-hspice"]
        build_code, build_stdout, build_stderr = run_command(build_command, cwd=candidate_root, env=clean_env, timeout=COMMAND_TIMEOUT_SECONDS, output_limit=MAX_ARCHIVE_BYTES)
        if build_code != 0:
            raise SystemExit("clean candidate offline build failed or exceeded output budget")
        binary = target_dir / "debug" / "sipi-agent-spice-run-hspice.exe"
        if not binary.is_file() or binary.is_symlink():
            raise SystemExit("clean candidate binary missing")
        binary_snapshot = physical(binary, "binary", candidate_root)
        solver_pre = tool_identity(args.ngspice, "ngspice", ("-v",))
        if solver_pre["version_exit_code"] != 0:
            raise SystemExit("ngspice preflight version command failed")
        with tempfile.TemporaryDirectory(prefix="sipi-as05-run-") as run_temp:
            run_root = Path(run_temp)
            fixtures = fixture_records(run_root)
            cases = [run_case(candidate_root, run_root, fixture, args.ngspice, solver_sha256, binary, binary_snapshot, clean_env) for fixture in fixtures]
        solver_post = tool_identity(args.ngspice, "ngspice", ("-v",))
        if not identity_equal(solver_pre, solver_post):
            raise SystemExit("ngspice identity changed during replay")
        if solver_post["version_exit_code"] != 0:
            raise SystemExit("ngspice postflight version command failed")
        solver = {**solver_pre, "caller_sha256": solver_sha256, "pre_file_sha256": solver_pre["file_sha256"], "post_file_sha256": solver_post["file_sha256"], "pre_file_bytes": solver_pre["file_bytes"], "post_file_bytes": solver_post["file_bytes"], "pre_basename": solver_pre["basename"], "post_basename": solver_post["basename"]}
        runner_path = candidate_root / "tools" / "run_as05_ngspice_bound.py"
        if not runner_custody(runtime_path, runner_path, expected_runner_sha256):
            raise SystemExit("candidate archive runner SHA-256 mismatch")
        upstream_commit = git(args.upstream_root, "rev-parse", "HEAD", executable=git_path).decode().strip()
        upstream_tree = git(args.upstream_root, "rev-parse", "HEAD^{tree}", executable=git_path).decode().strip()
        if upstream_commit != UPSTREAM_COMMIT or upstream_tree != UPSTREAM_TREE:
            raise SystemExit("pinned upstream commit/tree mismatch")
        upstream_archive = sha(git(args.upstream_root, "archive", "--format=tar", UPSTREAM_COMMIT, executable=git_path))
        if upstream_archive != args.upstream_archive_sha256:
            raise SystemExit("upstream archive SHA-256 mismatch")
        tool_post = toolchain_identities(git_path, cargo, rustc, python)
        if any(not identity_equal(tool_pre[role], tool_post[role]) for role in tool_pre):
            raise SystemExit("tool identity changed during replay")
        if physical(binary, "binary", candidate_root) != binary_snapshot:
            raise SystemExit("candidate binary changed after execution")
        report = {
            "schema": "sipi.as-05-ngspice-scoped-observation.v2-prep",
            "status": "scoped_external_runtime_observation_open",
            "scope": {"external_solver_not_verified": True, "numeric_parity": False, "parity_claim": False, "as05_row_closed": False, "release": False, "environment_injection_not_fully_excluded": True},
            "run_id": args.run_id,
            "fresh_run_nonce": sha(os.urandom(32)),
            "candidate": {"commit": actual_commit, "tree": actual_tree, "archive_sha256": candidate_archive},
            "upstream": {"commit": upstream_commit, "tree": upstream_tree, "archive_sha256": upstream_archive},
            "runner": {"path": "tools/run_as05_ngspice_bound.py", "sha256": runtime_runner_sha256},
            "toolchain": tool_pre,
            "build": {"exit_code": build_code, "stdout_bytes": len(build_stdout), "stdout_sha256": sha(build_stdout), "stderr_bytes": len(build_stderr), "stderr_sha256": sha(build_stderr), "binary_path_redacted": True, "binary_bytes": binary_snapshot["bytes"], "binary_sha256": binary_snapshot["sha256"], "offline": True, "locked": True, "target_dir_redacted": True, "rustc_env_identity": tool_pre["rustc"]["file_sha256"], "wrapper_policy": "RUSTC_WRAPPER_RUSTC_WORKSPACE_WRAPPER_CARGO_BUILD_RUSTC_WRAPPER_cleared"},
            "solver": solver,
            "fixtures": fixtures,
            "cases": cases,
            "path_policy": "path_free_report_create_new_scoped_external_observation_no_parity_no_release",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True).encode() + b"\n"
    try:
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise SystemExit("output report already exists; create-new semantics reject overwrite") from error
    with os.fdopen(descriptor, "wb") as report_file:
        report_file.write(payload)
    print(json.dumps({"report_sha256": report_sha(args.output), "run_id": args.run_id}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
