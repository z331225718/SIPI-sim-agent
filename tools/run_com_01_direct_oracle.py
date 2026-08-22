"""Run the pinned COM-01 Python/Rust config-validate differential.

The runner has two explicit phases.  Preparation binds the pinned upstream
Git object and the candidate executable identity.  Execution uses only an
owner-supplied external workbook and records redacted summaries, never raw
configuration output or local paths.  It intentionally does not promote a
product capability or close a governance row.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

UPSTREAM_COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
UPSTREAM_TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
SCHEMA = "sipi.com-01-direct-port-differential.v1"
CORPUS = Path(__file__).resolve().parents[1] / "docs" / "baselines" / "com-01-direct-port-corpus.v1.json"
REQUIRED_SOURCE_PATHS = (
    "src/agent_com/cli.py",
    "src/agent_com/config/__init__.py",
    "src/agent_com/config/consumption.py",
    "src/agent_com/config/derived.py",
    "src/agent_com/config/excel.py",
    "src/agent_com/config/literals.py",
    "src/agent_com/config/materialize.py",
    "src/agent_com/config/schema.py",
    "src/agent_com/capabilities.py",
    "schemas/behavior-presets.yaml",
    "schemas/r480-config.schema.yaml",
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    output = subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)
    return output if raw else output.decode("ascii").strip()


def git_archive_sha256(root: Path, revision: str, *paths: str) -> str:
    command = ["git", "-C", str(root), "archive", "--format=tar", revision]
    if paths:
        command.extend(["--", *paths])
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None
    state = hashlib.sha256()
    for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
        state.update(block)
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()
    if process.wait() != 0:
        raise RuntimeError(f"cannot hash upstream archive: {stderr}")
    return state.hexdigest()


def source_observation(root: Path, path: str) -> dict[str, Any]:
    ref = f"{UPSTREAM_COMMIT}:{path}"
    content = bytes(git(root, "cat-file", "blob", ref, raw=True))
    return {
        "path": path,
        "git_blob_sha1": str(git(root, "rev-parse", ref)),
        "bytes": int(str(git(root, "cat-file", "-s", ref))),
        "content_sha256": digest(content),
    }


def load_corpus() -> dict[str, Any]:
    document = json.loads(CORPUS.read_text(encoding="utf-8"))
    if document.get("schema") != "sipi.com-01-direct-port-corpus.v1":
        raise RuntimeError("COM-01 corpus schema drift")
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise RuntimeError("COM-01 corpus is empty")
    return document


def scenario_set_sha256(corpus: dict[str, Any] | None = None) -> str:
    document = corpus or load_corpus()
    canonical = json.dumps(document["scenarios"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    return digest(canonical)


def _fixture_cell(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, list):
        if value and isinstance(value[0], list):
            return "[" + "; ".join(" ".join(str(item) for item in row) for row in value) + "]"
        return "[" + " ".join(str(item) for item in value) + "]"
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def derive_package_warning_fixture(primary: Path, agent_com_root: Path, directory: Path) -> Path:
    sys.path.insert(0, str(agent_com_root / "src"))
    from agent_com.config.excel import ComSettings

    settings = ComSettings.from_xlsx(primary)
    path = directory / "com-01-package-warning.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        for row in settings.rows:
            writer.writerow([_fixture_cell(cell.value) for cell in row])
        writer.writerow([".START", "DUP"])
        writer.writerow(["package_marker", "1"])
        writer.writerow([".END"])
        writer.writerow([".START", "DUP"])
        writer.writerow(["package_marker", "1"])
        writer.writerow([".END"])
    return path


def _redact(value: Any, fixture: Path | None = None) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact(item, fixture) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, fixture) for item in value]
    if isinstance(value, str):
        text = value
        if fixture is not None:
            text = text.replace(str(fixture.resolve()), "<fixture>")
            text = text.replace(str(fixture), "<fixture>")
        text = re.sub(r"[A-Za-z]:[\\\\/][^\"\\r\\n]*", "<local-path>", text)
        text = re.sub(r"(?<![A-Za-z0-9_])/(?:Users|home|tmp|var)/[^\"\\r\\n ]*", "<local-path>", text)
        return text
    return value


def _run(command: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _scenario_args(scenario: dict[str, Any], fixture: Path) -> list[str]:
    args = ["config", "validate", str(fixture)]
    profile = scenario.get("profile")
    if profile and profile != "r480":
        args.extend(["--profile", str(profile)])
    reader = scenario.get("reader")
    if reader is not None:
        args.extend(["--reader", str(reader)])
    for fix_id in scenario.get("fix_ids", []):
        args.extend(["--fix-id", str(fix_id)])
    for override in scenario.get("overrides", []):
        args.extend(["--override", str(override)])
    output = scenario.get("output")
    if output == "json":
        args.append("--json")
    elif output == "materialized_json":
        args.append("--materialized-json")
    elif output == "json_and_materialized_json":
        args.extend(["--json", "--materialized-json"])
    return args


def _parse_json_output(output: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def _error_category(stdout: str, stderr: str) -> str:
    text = f"{stdout}\n{stderr}".casefold()
    if (
        "json modes" in text
        or "mutually exclusive" in text
        or "not allowed with argument" in text
    ):
        return "argument_error"
    if "profile" in text:
        return "profile_error"
    if "override" in text:
        return "override_error"
    if "package" in text:
        return "package_error"
    if "supports only" in text or "extension" in text:
        return "unsupported_path"
    if "missing" in text or "not found" in text or "no such" in text:
        return "input_error"
    return "config_error"


def _normal_form(value: Any, fixture: Path) -> Any:
    if isinstance(value, dict):
        return {key: _normal_form(item, fixture) for key, item in value.items() if key not in {"config", "path"}}
    if isinstance(value, list):
        return [_normal_form(item, fixture) for item in value]
    return value


def _value_projection(value: Any, fixture: Path) -> Any:
    normalized = _normal_form(value, fixture)
    if isinstance(normalized, dict):
        normalized = {
            key: item
            for key, item in normalized.items()
            if key != "materialized_fingerprint"
        }
        consumption = normalized.get("config_consumption")
        if isinstance(consumption, dict):
            normalized["config_consumption"] = {
                key: consumption[key]
                for key in (
                    "implemented",
                    "report_only",
                    "unimplemented",
                    "obsolete",
                    "unverified",
                    "summary",
                )
                if key in consumption
            }
    return normalized


def _canonical_sha256(value: Any) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _key_set_sha256(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return _canonical_sha256(sorted(value))


def _difference_keys(left: Any, right: Any, prefix: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        result: list[str] = []
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                result.append(path)
            else:
                result.extend(_difference_keys(left[key], right[key], path))
            if len(result) >= 64:
                return result[:64]
        return result
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [prefix]
        result = []
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            result.extend(_difference_keys(left_item, right_item, f"{prefix}[{index}]"))
            if len(result) >= 64:
                return result[:64]
        return result
    return [] if left == right else [prefix]


def _artifact_summary(
    value: Any,
    fixture: Path,
    stdout: str,
    stderr: str,
    error_category: str | None,
) -> dict[str, Any]:
    if error_category is not None:
        return {
            "error_category": error_category,
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stdout_sha256": digest(stdout.encode("utf-8")),
            "stderr_bytes": len(stderr.encode("utf-8")),
            "stderr_sha256": digest(stderr.encode("utf-8")),
        }
    if not isinstance(value, dict):
        return {
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stdout_sha256": digest(stdout.encode("utf-8")),
        }
    projection = _value_projection(value, fixture)
    summary: dict[str, Any] = {
        "projection_sha256": _canonical_sha256(projection),
        "top_level_keys": sorted(value),
    }
    for key in ("parameters", "options", "package_blocks", "profile", "schema_version"):
        if key in value and not isinstance(value[key], (dict, list)):
            summary[key] = value[key]
    if isinstance(value.get("warnings"), list):
        summary["warnings"] = value["warnings"]
    materialized = value.get("materialized")
    if isinstance(materialized, dict):
        parameters = materialized.get("parameters")
        options = materialized.get("options")
        summary["materialized"] = {
            "parameter_count": len(parameters) if isinstance(parameters, dict) else None,
            "parameter_keys_sha256": _key_set_sha256(parameters),
            "option_count": len(options) if isinstance(options, dict) else None,
            "option_keys_sha256": _key_set_sha256(options),
        }
        summary["materialized_fingerprint"] = value.get("materialized_fingerprint")
    consumption = value.get("config_consumption")
    if isinstance(consumption, dict) and isinstance(consumption.get("summary"), dict):
        summary["consumption_summary"] = consumption["summary"]
    return _redact(summary, fixture)


def compare_scenario(
    scenario: dict[str, Any],
    fixture: Path,
    agent_com_root: Path,
    candidate_binary: Path,
) -> dict[str, Any]:
    args = _scenario_args(scenario, fixture)
    env = {**os.environ, "PYTHONPATH": str(agent_com_root / "src")}
    oracle_code, oracle_stdout, oracle_stderr = _run([sys.executable, "-m", "agent_com.cli", *args], env=env)
    candidate_code, candidate_stdout, candidate_stderr = _run([str(candidate_binary), *args])
    oracle_json = _parse_json_output(oracle_stdout)
    candidate_json = _parse_json_output(candidate_stdout)
    output = str(scenario.get("output"))
    oracle_error_category = None if oracle_code == 0 else _error_category(oracle_stdout, oracle_stderr)
    candidate_error_category = None if candidate_code == 0 else _error_category(candidate_stdout, candidate_stderr)
    if oracle_code != 0 or candidate_code != 0:
        value_match = (
            oracle_code == candidate_code
            and oracle_error_category == candidate_error_category
        )
        fingerprint_match = None
        comparison = "error_code_match" if value_match else "error_code_mismatch"
        difference_keys = [] if value_match else ["exit_or_error_category"]
    elif output == "materialized_json" and oracle_json is not None and candidate_json is not None:
        oracle_cmp = _value_projection(oracle_json, fixture)
        candidate_cmp = _value_projection(candidate_json, fixture)
        value_match = oracle_cmp == candidate_cmp
        fingerprint_match = (
            candidate_json.get("materialized_fingerprint")
            == oracle_json.get("materialized_fingerprint")
        )
        comparison = "values_equal_fingerprint_drift" if value_match and not fingerprint_match else (
            "passed" if value_match else "mismatch"
        )
        difference_keys = _difference_keys(oracle_cmp, candidate_cmp)
    elif oracle_code == 0 and candidate_code == 0 and oracle_json is not None and candidate_json is not None:
        value_match = _normal_form(oracle_json, fixture) == _normal_form(candidate_json, fixture)
        fingerprint_match = None
        comparison = "passed" if value_match else "mismatch"
        difference_keys = _difference_keys(
            _normal_form(oracle_json, fixture),
            _normal_form(candidate_json, fixture),
        )
    else:
        value_match = oracle_stdout.strip() == candidate_stdout.strip()
        fingerprint_match = None
        comparison = "passed" if value_match else "mismatch"
        difference_keys = [] if value_match else ["stdout"]
    return {
        "id": scenario["id"],
        "fixture_role": scenario["fixture_role"],
        "output": output,
        "oracle_exit": oracle_code,
        "candidate_exit": candidate_code,
        "comparison": comparison,
        "value_match": value_match,
        "fingerprint_match": fingerprint_match,
        "difference_keys": difference_keys,
        "oracle_error_category": oracle_error_category,
        "candidate_error_category": candidate_error_category,
        "oracle_summary": _artifact_summary(
            oracle_json, fixture, oracle_stdout, oracle_stderr, oracle_error_category
        ),
        "candidate_summary": _artifact_summary(
            candidate_json, fixture, candidate_stdout, candidate_stderr, candidate_error_category
        ),
    }


def prepare(
    *,
    agent_com_root: Path,
    candidate_root: Path | None = None,
    candidate_commit: str | None = None,
    run_id: str = "prep-20260823-01",
) -> dict[str, Any]:
    if git(agent_com_root, "rev-parse", "HEAD") != UPSTREAM_COMMIT:
        raise RuntimeError("Agent-COM root HEAD is not the pinned commit")
    if git(agent_com_root, "rev-parse", f"{UPSTREAM_COMMIT}^{{tree}}") != UPSTREAM_TREE:
        raise RuntimeError("Agent-COM root tree is not pinned")
    corpus = load_corpus()
    source = {
        "repository": "https://github.com/z331225718/agent-com.git",
        "commit": UPSTREAM_COMMIT,
        "tree": UPSTREAM_TREE,
        "archive_inventory_sha256": git_archive_sha256(agent_com_root, UPSTREAM_COMMIT),
        "declared_license": "MIT",
        "source_paths": [source_observation(agent_com_root, path) for path in REQUIRED_SOURCE_PATHS],
    }
    candidate: dict[str, Any]
    if candidate_root is None or candidate_commit is None:
        candidate = {"status": "unbound_candidate", "reason": "candidate_archive_not_supplied"}
    else:
        if git(candidate_root, "rev-parse", "HEAD") != candidate_commit:
            raise RuntimeError("candidate root does not expose requested commit")
        candidate = {
            "status": "candidate_archive_ready",
            "commit": candidate_commit,
            "tree": git(candidate_root, "rev-parse", f"{candidate_commit}^{{tree}}"),
            "direct_crate_inventory_sha256": git_archive_sha256(
                candidate_root, candidate_commit, "crates/sipi-agent-com-direct"
            ),
        }
    return {
        "schema": SCHEMA,
        "status": "implementation_materialized_open",
        "work_item": "COM-01",
        "run_id": run_id,
        "source": source,
        "candidate": candidate,
        "corpus": {
            "path": "docs/baselines/com-01-direct-port-corpus.v1.json",
            "scenario_count": len(corpus["scenarios"]),
            "scenario_set_sha256": scenario_set_sha256(corpus),
            "fixture_policy": corpus["fixture_policy"],
        },
        "stages": {
            "stage_1_source_and_candidate_archive": {
                "status": "ready",
                "source_mode": "pinned_git_object",
                "candidate_mode": "candidate_archive_only",
            },
            "stage_2_two_run_differential_execution": {
                "status": "ready_with_external_fixture",
                "requires": "owner_supplied_fixture_and_candidate_executable",
            },
        },
        "non_claims": [
            "no_com_runtime_execution",
            "no_product_capability_promotion",
            "no_global_migration_row_close",
            "no_workbook_or_mat_bytes_vendored",
            "no_release_readiness",
        ],
    }


def execute(
    *,
    agent_com_root: Path,
    candidate_binary: Path,
    fixture: Path,
    run_count: int = 2,
) -> dict[str, Any]:
    if git(agent_com_root, "rev-parse", "HEAD") != UPSTREAM_COMMIT:
        raise RuntimeError("Agent-COM root HEAD is not the pinned commit")
    if not fixture.is_file():
        raise RuntimeError(f"fixture does not exist: {fixture}")
    if not candidate_binary.is_file():
        raise RuntimeError(f"candidate executable does not exist: {candidate_binary}")
    corpus = load_corpus()
    reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="com-01-") as temporary:
        tempdir = Path(temporary)
        package_fixture = derive_package_warning_fixture(fixture, agent_com_root, tempdir)
        fixtures = {
            "primary_xlsx": fixture,
            "package_warning_csv": package_fixture,
        }
        for run_index in range(run_count):
            run_id = f"run-{run_index + 1:02d}"
            nonce = secrets.token_hex(32)
            scenarios = []
            for scenario in corpus["scenarios"]:
                role = scenario["fixture_role"]
                if role in fixtures:
                    scenario_fixture = fixtures[role]
                    scenarios.append(compare_scenario(scenario, scenario_fixture, agent_com_root, candidate_binary))
                elif role == "missing_xlsx":
                    missing = tempdir / "missing.xlsx"
                    scenarios.append(compare_scenario(scenario, missing, agent_com_root, candidate_binary))
                elif role == "unsupported_text":
                    unsupported = tempdir / "unsupported.txt"
                    unsupported.write_text("not a configuration", encoding="utf-8")
                    scenarios.append(compare_scenario(scenario, unsupported, agent_com_root, candidate_binary))
                else:
                    raise RuntimeError(f"unknown fixture role: {role}")
            reports.append({
                "run_id": run_id,
                "nonce": nonce,
                "scenarios": scenarios,
                "passed": all(
                    item["comparison"] in {"passed", "error_code_match"}
                    for item in scenarios
                ),
            })
        fixture_entries = [
            {
                "role": role,
                "extension": path.suffix,
                "bytes": path.stat().st_size,
                "sha256": digest(path.read_bytes()),
            }
            for role, path in fixtures.items()
        ]
    return {
        "schema": SCHEMA,
        "status": "passed" if all(report["passed"] for report in reports) else "open_differential_mismatch",
        "work_item": "COM-01",
        "source": {
            "repository": "https://github.com/z331225718/agent-com.git",
            "commit": UPSTREAM_COMMIT,
            "tree": UPSTREAM_TREE,
        },
        "candidate": {
            "executable": candidate_binary.name,
            "path_redacted": True,
        },
        "fixtures": fixture_entries,
        "runs": reports,
        "non_claims": [
            "no_com_runtime_execution",
            "no_product_capability_promotion",
            "no_global_migration_row_close",
            "no_workbook_or_mat_bytes_vendored",
            "no_release_readiness",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-com-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--run-id", default="prep-20260823-01")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument(
        "--candidate-binary",
        type=Path,
        default=Path("crates/sipi-agent-com-direct/target/debug/sipi-com-direct-config-validate.exe"),
    )
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = (
        execute(
            agent_com_root=args.agent_com_root,
            candidate_binary=args.candidate_binary,
            fixture=args.fixture,
            run_count=args.runs,
        )
        if args.fixture is not None
        else prepare(
            agent_com_root=args.agent_com_root,
            candidate_root=args.candidate_root,
            candidate_commit=args.candidate_commit,
            run_id=args.run_id,
        )
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"schema": report["schema"], "status": report["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
