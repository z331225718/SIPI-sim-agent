"""Run selected original-13 workbooks through MATLAB source-warning observation only.

The runner deliberately excludes Rust execution and numerical acceptance.  It
exists to collect bounded, source-local warning call facts before a candidate
warning can be promoted into the direct Rust result wire.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

try:
    from tools.run_com_tdiln_original13_diagnostic import (
        _engine_worker,
        _parse_indices,
        _run_engine_worker,
        _worker_environment,
    )
    from tools.run_p5_06_original13_fresh_matrix import (
        CONFIG_PATHS,
        bounded,
        digest,
        prepare_matlab_engine,
    )
except ImportError:
    from run_com_tdiln_original13_diagnostic import (
        _engine_worker,
        _parse_indices,
        _run_engine_worker,
        _worker_environment,
    )
    from run_p5_06_original13_fresh_matrix import (
        CONFIG_PATHS,
        bounded,
        digest,
        prepare_matlab_engine,
    )


SCHEMA = "sipi.com.source-warning-observation-run.v1"
WARNING_SCHEMA = "sipi.com.pinned-source-warning-call-observation.v1"
SOURCE_LINES = (6337, 9715)
CHANNELS = (
    "thru_10db_at_26p56ghz.s4p",
    "fext_m40db_at_26p56ghz.s4p",
    "next_m40db_at_26p56ghz.s4p",
)


def _source_events(summary: Any) -> list[dict[str, Any]]:
    if not isinstance(summary, dict):
        raise ValueError("MATLAB summary must be an object")
    capture = summary.get("source_warning_calls")
    if not isinstance(capture, dict) or capture.get("schema") != WARNING_SCHEMA:
        raise ValueError("MATLAB source-warning schema drift")
    if capture.get("capture_incomplete") is not False:
        raise ValueError("MATLAB source-warning capture incomplete")
    events = capture.get("events")
    if not isinstance(events, list):
        raise ValueError("MATLAB source-warning events must be an array")
    result: list[dict[str, Any]] = []
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict) or event.get("sequence") != sequence:
            raise ValueError("MATLAB source-warning sequence drift")
        identifier = event.get("identifier")
        line = event.get("source_line")
        trace = event.get("source_trace")
        if not isinstance(identifier, str) or line not in SOURCE_LINES or not isinstance(trace, dict):
            raise ValueError("MATLAB source-warning event shape drift")
        # Exclude source messages: they contain external fixture paths and are
        # not needed to establish the static callsite or input trace.
        result.append({
            "sequence": sequence,
            "identifier": identifier,
            "source_line": line,
            "source_trace": trace,
        })
    return result


def _case_record(index: int, source_root: Path, worker_python: Path, engine_site: Path, harness: Path, output_root: Path, timeout: int) -> dict[str, Any]:
    workbook = source_root / CONFIG_PATHS[index]
    channels = [source_root / "fixtures" / "synthetic" / name for name in CHANNELS]
    if not workbook.is_file() or any(not path.is_file() for path in channels):
        raise FileNotFoundError(f"original-13 input missing for index {index}")
    case_root = output_root / f"case-{index:02d}"
    case_root.mkdir()
    matlab_output = case_root / "matlab"
    matlab_output.mkdir()
    spec = {
        "source_root": str(source_root),
        "config": str(workbook),
        "parameter_mat": str(case_root / "parameter.mat"),
        "output": str(matlab_output),
        "harness": str(harness),
        "nonce": secrets.token_hex(32),
        "channels": [str(path) for path in channels],
    }
    completed = _run_engine_worker(
        worker_python,
        spec,
        case_root,
        _worker_environment(source_root, engine_site, case_root / "matlab-pref"),
        timeout,
    )
    summary_path = matlab_output / "summary.json"
    if completed.returncode != 0 or not summary_path.is_file():
        return {
            "workbook_index": index,
            "workbook": CONFIG_PATHS[index],
            "status": "matlab_failed",
            "matlab_exit_code": completed.returncode,
            "matlab_detail_sha256": hashlib.sha256(completed.stdout + completed.stderr).hexdigest(),
        }
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "workbook_index": index,
        "workbook": CONFIG_PATHS[index],
        "status": "passed_observation",
        "matlab_summary_sha256": digest(summary_path),
        "core_duration_seconds": summary.get("core_duration_seconds"),
        "events": _source_events(summary),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--harness", type=Path)
    parser.add_argument("--indices", required=True, help="comma-separated original-13 indices")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.output.exists() or not args.source_root.is_dir() or not args.matlab.is_file() or args.timeout <= 0:
        raise ValueError("invalid output/source/tool/timeout request")
    indices = _parse_indices(args.indices)
    harness = args.harness or Path(__file__).with_name("sipi_com_tdiln_matrix_diagnostic_v1.m")
    if not harness.is_file():
        raise FileNotFoundError("TDILN MATLAB harness missing")
    args.output.mkdir(parents=True)
    environment = args.output / "python-env"
    sync_env = os.environ.copy()
    sync_env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    sync = bounded(
        [str(args.uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(args.python)],
        args.source_root,
        300,
        sync_env,
    )
    worker_python = environment / "Scripts" / "python.exe"
    if sync.returncode != 0 or not worker_python.is_file():
        raise RuntimeError("frozen Agent-COM Python environment failed")
    engine_site = prepare_matlab_engine(worker_python, args.uv, args.matlab, args.output)
    records = []
    for index in indices:
        try:
            records.append(_case_record(index, args.source_root, worker_python, engine_site, harness, args.output, args.timeout))
        except Exception as error:
            records.append({
                "workbook_index": index,
                "workbook": CONFIG_PATHS[index],
                "status": "runner_failed",
                "error_type": type(error).__name__,
                "error_sha256": hashlib.sha256(str(error).encode()).hexdigest(),
            })
    passed = all(record["status"] == "passed_observation" for record in records)
    report = {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "non_claims": ["not_rust_parity", "not_complete_warning_catalog", "not_release_evidence"],
        "source_commit_unverified": True,
        "matlab_harness_sha256": digest(harness),
        "matlab_launch": "python_engine_noFigureWindows_singleCompThread",
        "records": records,
        "status": "passed_observation" if passed else "blocked",
    }
    (args.output / "report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"status": report["status"], "records": len(records)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
