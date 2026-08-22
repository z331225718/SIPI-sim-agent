"""Run one COM-01 leaf differential from immutable Git archives.

The candidate, corpus, semantic comparison runner, upstream Python source,
and primary workbook all come from pinned commits.  The report stores only
source identities and bounded summaries; configuration values are never
written to evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.com-01-direct-replay.v1"
CANDIDATE_COMMIT = "8bcfd1d1bc511461615f19338e453f0148e5dcb1"
CANDIDATE_TREE = "ed221a36f2d3325b0aac3f3336a9c8a14d13e99a"
UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
FIXTURE_RELATIVE = Path(
    "matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx"
)
CORPUS_RELATIVE = Path("docs/baselines/com-01-direct-port-corpus.v1.json")
SEMANTIC_RUNNER_RELATIVE = Path("tools/run_com_01_direct_oracle.py")
CRATE_RELATIVE = Path("crates/sipi-agent-com-direct")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_OUTCOMES = {
    "passed": 6,
    "error_code_match": 7,
    "values_equal_fingerprint_drift": 1,
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout if raw else completed.stdout.decode("ascii").strip()


def _commit_tree(root: Path, commit: str) -> tuple[str, str]:
    resolved = str(_git(root, "rev-parse", f"{commit}^{{commit}}"))
    tree = str(_git(root, "rev-parse", f"{resolved}^{{tree}}"))
    return resolved, tree


def _extract_archive(payload: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise RuntimeError(f"archive link is not admitted: {member.name}")
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.name}")
            archive.extract(member, destination)


def _materialize_archive(root: Path, commit: str, destination: Path) -> dict[str, str]:
    payload = bytes(_git(root, "archive", "--format=tar", commit, raw=True))
    _extract_archive(payload, destination)
    resolved, tree = _commit_tree(root, commit)
    return {"commit": resolved, "tree": tree, "archive_sha256": _sha256(payload)}


def _safe_archived_file(root: Path, relative: Path) -> Path:
    raw = os.fspath(relative)
    host = Path(raw)
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if (
        not raw
        or "\x00" in raw
        or host.is_absolute()
        or bool(host.anchor)
        or posix.is_absolute()
        or bool(posix.anchor)
        or windows.is_absolute()
        or bool(windows.anchor)
        or bool(windows.drive)
        or ".." in re.split(r"[\\/]", raw)
    ):
        raise RuntimeError("archived file path must be repository-relative")
    archive_root = root.resolve()
    path = (root / relative).resolve()
    if archive_root not in path.parents or not path.is_file():
        raise RuntimeError(f"archived file is missing or escaped: {relative.as_posix()}")
    return path


def _inventory(root: Path, prefixes: Iterable[Path]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for prefix in prefixes:
        path = root / prefix
        files = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for file in files:
            payload = file.read_bytes()
            entries.append(
                {
                    "path": file.relative_to(root).as_posix(),
                    "bytes": len(payload),
                    "sha256": _sha256(payload),
                }
            )
    entries.sort(key=lambda item: item["path"])
    return {
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
        "sha256": _sha256(_canonical(entries)),
    }


def _resolve_executable(value: str, role: str) -> Path:
    literal = Path(value)
    if literal.is_file():
        return literal.resolve()
    resolved = shutil.which(value)
    if resolved is None or not Path(resolved).is_file():
        raise RuntimeError(f"{role} executable cannot be resolved")
    return Path(resolved).resolve()


def _tool_identity(path: Path, role: str, version_args: tuple[str, ...]) -> dict[str, Any]:
    version = subprocess.run(
        [str(path), *version_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if version.returncode != 0:
        raise RuntimeError(f"{role} version command failed")
    executable = path.name
    if not executable or any(separator in executable for separator in ("/", "\\")):
        raise RuntimeError(f"{role} executable identity is not path-free")
    return {
        "role": role,
        "executable": executable,
        "path_redacted": True,
        "file_sha256": _sha256(path.read_bytes()),
        "version_exit_code": 0,
        "version_output_sha256": _sha256(version.stdout + b"\x00" + version.stderr),
    }


def _toolchain(cargo_value: str, python_value: str, timeout_seconds: int) -> tuple[dict[str, Any], dict[str, Path]]:
    cargo = _resolve_executable(cargo_value, "cargo")
    rustc = cargo.with_name(f"rustc{cargo.suffix}")
    if not rustc.is_file():
        rustc = _resolve_executable("rustc", "rustc")
    python = _resolve_executable(python_value, "python")
    identity = {
        "cargo": _tool_identity(cargo, "cargo", ("-Vv",)),
        "rustc": _tool_identity(rustc, "rustc", ("-Vv",)),
        "python": _tool_identity(python, "python", ("--version",)),
        "timeout_seconds": timeout_seconds,
    }
    return identity, {"cargo": cargo, "rustc": rustc, "python": python}


def _normalized_build_log(payload: bytes) -> str:
    counts: Counter[str] = Counter()
    for line in payload.decode("utf-8", errors="replace").splitlines():
        text = line.strip().casefold()
        if text.startswith("compiling "):
            counts["compiling"] += 1
        elif text.startswith("finished "):
            counts["finished"] += 1
        elif text.startswith("warning"):
            counts["warning"] += 1
        elif text.startswith("error"):
            counts["error"] += 1
        elif text:
            counts["other"] += 1
    return json.dumps(counts, sort_keys=True, separators=(",", ":"))


def _build_candidate(
    candidate_root: Path,
    target_root: Path,
    tools: dict[str, Path],
    timeout_seconds: int,
    source_date_epoch: str,
) -> tuple[Path, dict[str, Any]]:
    environment = dict(os.environ)
    environment.pop("RUSTC_WRAPPER", None)
    environment.pop("RUSTC_WORKSPACE_WRAPPER", None)
    environment.update(
        {
            "RUSTC": str(tools["rustc"]),
            "CARGO_TARGET_DIR": str(target_root),
            "CARGO_INCREMENTAL": "0",
            "SOURCE_DATE_EPOCH": source_date_epoch,
            "RUSTFLAGS": (
                f"-C link-arg=/Brepro --remap-path-prefix={candidate_root}=C:/sipi-candidate"
            ),
        }
    )
    completed = subprocess.run(
        [
            str(tools["cargo"]),
            "build",
            "--manifest-path",
            str(candidate_root / CRATE_RELATIVE / "Cargo.toml"),
            "--bin",
            "sipi-com-direct-config-validate",
            "--release",
            "--locked",
            "--offline",
        ],
        cwd=candidate_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("candidate archive build failed")
    binary = target_root / "release" / "sipi-com-direct-config-validate"
    if os.name == "nt":
        binary = binary.with_suffix(".exe")
    if not binary.is_file():
        raise RuntimeError("candidate archive build did not produce config-validate")
    return binary, {
        "binary_sha256": _sha256(binary.read_bytes()),
        "build_stdout_sha256": _sha256(_normalized_build_log(completed.stdout).encode("ascii")),
        "build_stderr_sha256": _sha256(_normalized_build_log(completed.stderr).encode("ascii")),
        "build_log_policy": "stable_event_categories",
    }


def _load_archived_runner(path: Path, corpus: Path, timeout_seconds: int) -> ModuleType:
    name = f"com01_archived_oracle_{secrets.token_hex(8)}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load archived semantic runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CORPUS = corpus
    original_artifact_summary = module._artifact_summary

    def redacted_artifact_summary(
        value: Any,
        fixture: Path,
        stdout: str,
        stderr: str,
        error_category: str | None,
    ) -> dict[str, Any]:
        return original_artifact_summary(
            value,
            fixture,
            module._redact(stdout, fixture),
            module._redact(stderr, fixture),
            error_category,
        )

    module._artifact_summary = redacted_artifact_summary

    def bounded_run(command: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str, str]:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode, completed.stdout, completed.stderr

    module._run = bounded_run
    return module


def _run_scenarios(
    module: ModuleType,
    upstream_root: Path,
    candidate_binary: Path,
    fixture: Path,
    scratch: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    corpus = module.load_corpus()
    package_fixture = module.derive_package_warning_fixture(fixture, upstream_root, scratch)
    fixtures = {"primary_xlsx": fixture, "package_warning_csv": package_fixture}
    scenarios: list[dict[str, Any]] = []
    for scenario in corpus["scenarios"]:
        role = scenario["fixture_role"]
        if role in fixtures:
            scenario_fixture = fixtures[role]
        elif role == "missing_xlsx":
            scenario_fixture = scratch / "missing.xlsx"
        elif role == "unsupported_text":
            scenario_fixture = scratch / "unsupported.txt"
            scenario_fixture.write_text("not a configuration", encoding="utf-8")
        else:
            raise RuntimeError(f"unknown fixture role: {role}")
        scenarios.append(
            module.compare_scenario(scenario, scenario_fixture, upstream_root, candidate_binary)
        )
    fixture_summaries = [
        {
            "role": role,
            "extension": path.suffix,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path.read_bytes()),
        }
        for role, path in fixtures.items()
    ]
    return scenarios, fixture_summaries


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_repo = args.candidate_repo.resolve()
    upstream_repo = args.upstream_repo.resolve()
    candidate_commit, candidate_tree = _commit_tree(candidate_repo, args.candidate_commit)
    upstream_commit, upstream_tree = _commit_tree(upstream_repo, args.upstream_commit)
    if (candidate_commit, candidate_tree) != (CANDIDATE_COMMIT, CANDIDATE_TREE):
        raise RuntimeError("candidate commit/tree is not the COM-01 preparation commit")
    if (upstream_commit, upstream_tree) != (UPSTREAM_COMMIT, UPSTREAM_TREE):
        raise RuntimeError("upstream commit/tree is not pinned")
    toolchain, runtime_tools = _toolchain(args.cargo, args.python, args.timeout_seconds)
    if runtime_tools["python"] != Path(sys.executable).resolve():
        raise RuntimeError("python identity must match the interpreter executing the replay")
    source_date_epoch = str(_git(candidate_repo, "show", "-s", "--format=%ct", candidate_commit))
    fresh_run_nonce = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="com-01-bound-") as directory:
        run_root = Path(directory)
        candidate_root = run_root / "candidate"
        upstream_root = run_root / "upstream"
        target_root = run_root / "candidate-target"
        scratch = run_root / "scenario-output"
        target_root.mkdir()
        scratch.mkdir()
        candidate_info = _materialize_archive(candidate_repo, candidate_commit, candidate_root)
        upstream_info = _materialize_archive(upstream_repo, upstream_commit, upstream_root)
        candidate_inventory = _inventory(
            candidate_root, (CRATE_RELATIVE, CORPUS_RELATIVE, SEMANTIC_RUNNER_RELATIVE)
        )
        upstream_inventory = _inventory(
            upstream_root,
            (
                Path("src/agent_com"),
                Path("schemas/r480-config.schema.yaml"),
                Path("schemas/behavior-presets.yaml"),
                FIXTURE_RELATIVE,
            ),
        )
        fixture = _safe_archived_file(upstream_root, FIXTURE_RELATIVE)
        corpus = _safe_archived_file(candidate_root, CORPUS_RELATIVE)
        semantic_runner = _safe_archived_file(candidate_root, SEMANTIC_RUNNER_RELATIVE)
        module = _load_archived_runner(semantic_runner, corpus, args.timeout_seconds)
        binary, build = _build_candidate(
            candidate_root,
            target_root,
            runtime_tools,
            args.timeout_seconds,
            source_date_epoch,
        )
        scenarios, fixtures = _run_scenarios(
            module, upstream_root, binary, fixture, scratch
        )
        corpus_document = json.loads(corpus.read_text(encoding="utf-8"))
        candidate_record = {
            **candidate_info,
            "inventory": candidate_inventory,
            "cargo_lock_sha256": _sha256(
                _safe_archived_file(candidate_root, CRATE_RELATIVE / "Cargo.lock").read_bytes()
            ),
            "source_date_epoch": source_date_epoch,
            **build,
        }
        upstream_record = {**upstream_info, "inventory": upstream_inventory}
        harness_record = {
            "orchestration_runner_sha256": _sha256(Path(__file__).read_bytes()),
            "semantic_runner_sha256": _sha256(semantic_runner.read_bytes()),
            "corpus_sha256": _sha256(corpus.read_bytes()),
            "scenario_set_sha256": module.scenario_set_sha256(corpus_document),
            "scenario_count": len(corpus_document["scenarios"]),
            "process_timeout_seconds": args.timeout_seconds,
            "diagnostic_path_normalization": "redacted_before_hash",
        }
    outcomes = dict(sorted(Counter(item["comparison"] for item in scenarios).items()))
    values_aligned = all(
        item["comparison"]
        in {"passed", "error_code_match", "values_equal_fingerprint_drift"}
        for item in scenarios
    )
    fingerprint_drift_count = outcomes.get("values_equal_fingerprint_drift", 0)
    expected_open = values_aligned and outcomes == EXPECTED_OUTCOMES
    return {
        "schema": SCHEMA,
        "status": (
            "open_differential_mismatch_fingerprint_only" if expected_open else "blocked"
        ),
        "work_item": "COM-01",
        "run_id": args.run_id,
        "fresh_run_nonce": fresh_run_nonce,
        "source_mode": "git_archive_at_immutable_commit",
        "candidate": candidate_record,
        "upstream": upstream_record,
        "harness": harness_record,
        "toolchain": toolchain,
        "fixtures": fixtures,
        "outcomes": outcomes,
        "values_aligned": values_aligned,
        "fingerprint_drift_count": fingerprint_drift_count,
        "scenarios": scenarios,
        "artifact_policy": "hashes_counts_error_categories_and_bounded_difference_keys_only",
        "non_claims": [
            "no_complete_com_parity",
            "no_global_migration_row_close",
            "no_product_capability_promotion",
            "no_release_readiness",
            "no_configuration_value_payloads_committed",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--candidate-commit", default=CANDIDATE_COMMIT)
    parser.add_argument("--upstream-repo", type=Path, default=Path(r"C:\Users\z3312\code\COM"))
    parser.add_argument("--upstream-commit", default=UPSTREAM_COMMIT)
    parser.add_argument("--cargo", default=str(Path.home() / ".cargo" / "bin" / "cargo.exe"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    try:
        report = run(args)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), file=sys.stderr)
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"status": report["status"], "report": args.report.name}, sort_keys=True))
    return 0 if report["status"] == "open_differential_mismatch_fingerprint_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
