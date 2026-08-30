"""Diagnostic-only long-lived MATLAB Engine replay for the original-13 corpus.

This is intentionally separate from the formal v1/v2 acceptance runner.  It
tests whether one isolated Engine lifecycle avoids R2026a's intermittent
home-session-manager crash without relaxing any existing acceptance gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

try:
    from .run_p5_06_original13_fresh_matrix import (
        CHANNELS, CONFIG_PATHS, digest, inventory, materialize, matlab_metrics,
        worker_environment,
    )
except ImportError:
    from run_p5_06_original13_fresh_matrix import (
        CHANNELS, CONFIG_PATHS, digest, inventory, materialize, matlab_metrics,
        worker_environment,
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def stage(path: Path, nonce: str) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if set(value) != {"schema", "nonce", "stage"} or value["schema"] != "sipi.com.final-surface-stage.v3" or value["nonce"] != nonce:
        return None
    return value["stage"] if isinstance(value["stage"], str) else None


def make_parameter(config: Path, parameter: Path) -> None:
    import numpy as np
    from scipy.io import savemat
    from agent_com.config import ComSettings

    rows = ComSettings.from_xlsx(config).rows
    columns = max(len(row) for row in rows)
    values = np.empty((len(rows), columns), dtype=object)
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            raw = row[column_index].value if column_index < len(row) else None
            if raw is None:
                value = ""
            elif isinstance(raw, (bool, int, float, np.integer, np.floating)):
                value = float(raw)
            elif isinstance(raw, str):
                value = raw
            else:
                raise TypeError(f"unsupported workbook cell type: {type(raw).__name__}")
            values[row_index, column_index] = value
    savemat(parameter, {"parameter": values}, do_compression=False, oned_as="row")


def worker(manifest_path: Path) -> int:
    import matlab.engine

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(manifest["root"])
    source = Path(manifest["source"])
    nonce = manifest["nonce"]
    harness = Path(manifest["harness"])
    cases: list[dict[str, object]] = []
    session = {
        "engine_started": False,
        "all_cases_returned": False,
        "shutdown_complete": False,
        "source_inventory_unchanged": None,
    }
    source_before = inventory(source)
    engine = None
    try:
        engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
        session["engine_started"] = True
        engine.addpath(str(harness.parent), nargout=0)
        engine.addpath(str(source / "matlab_src"), nargout=0)
        resolved = engine.which("com_ieee8023_480", nargout=1)
        expected = str(source / "matlab_src" / "com_ieee8023_480.m")
        if os.path.normcase(str(resolved)) != os.path.normcase(expected):
            raise RuntimeError("pinned MATLAB source resolution drift")
        session["source_resolved"] = True
        for index, relative in enumerate(CONFIG_PATHS):
            case_root = root / f"case-{index:02d}"
            output = case_root / "matlab"
            case_root.mkdir(parents=True)
            parameter = case_root / "parameter.mat"
            make_parameter(source / relative, parameter)
            engine.cd(str(case_root), nargout=0)
            try:
                engine.sipi_com_final_surface_oracle_v3(
                    str(source), str(parameter), str(output), 1.0, 1.0, nonce,
                    *[str(source / path) for _role, path, _bytes, _sha in CHANNELS], nargout=0,
                )
                current_stage = stage(output / "stage.json", nonce)
                summary = output / "summary.json"
                if current_stage != "summary_written" or not summary.is_file():
                    raise RuntimeError("summary stage missing after MATLAB return")
                metrics = matlab_metrics(output)
                cases.append({"workbook_index": index, "status": "engine_call_returned", "stage": current_stage, "summary_sha256": digest(summary), "case_count": len(metrics), "metrics": metrics})
            except Exception as error:
                cases.append({"workbook_index": index, "status": "engine_call_failed", "stage": stage(output / "stage.json", nonce), "error_type": type(error).__name__})
                break
        session["all_cases_returned"] = len(cases) == len(CONFIG_PATHS) and all(case["status"] == "engine_call_returned" for case in cases)
    except Exception as error:
        session["session_error_type"] = type(error).__name__
        session["session_error"] = str(error)[-500:]
    finally:
        try:
            if engine is not None:
                engine.quit()
                session["shutdown_complete"] = True
        except Exception as error:
            session["shutdown_error_type"] = type(error).__name__
        session["source_inventory_unchanged"] = inventory(source) == source_before
    result = {
        "schema": "sipi.p5-06.original13.shared-matlab-diagnostic.v4",
        "nonce": nonce,
        "session": session,
        "cases": cases,
    }
    write_json(Path(manifest["result"]), result)
    return 0 if session["all_cases_returned"] and session["shutdown_complete"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-archive", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--matlab", type=Path)
    parser.add_argument("--python", type=Path)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    if not all((args.upstream_archive, args.output_root, args.matlab, args.python, args.uv)):
        parser.error("--upstream-archive, --output-root, --matlab, --python, and --uv are required outside --worker mode")
    if args.output_root.exists():
        raise FileExistsError(args.output_root)
    args.output_root.mkdir(parents=True)
    source = args.output_root / "upstream-source"
    materialize(args.upstream_archive, source)
    source_before = inventory(source)
    environment = args.output_root / "python-env"
    sync_environment = os.environ.copy()
    sync_environment["UV_PROJECT_ENVIRONMENT"] = str(environment)
    synced = subprocess.run([str(args.uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(args.python)], cwd=source, capture_output=True, check=False, env=sync_environment)
    python = environment / "Scripts" / "python.exe"
    if synced.returncode or not python.is_file():
        raise RuntimeError("pinned Python environment failed")
    nonce = secrets.token_hex(32)
    manifest = {"root": str(args.output_root / "cases"), "source": str(source), "nonce": nonce, "harness": str(Path(__file__).with_name("sipi_com_final_surface_oracle_v3.m")), "result": str(args.output_root / "shared-result.json")}
    manifest_path = args.output_root / "shared-manifest.json"
    write_json(manifest_path, manifest)
    try:
        completed = subprocess.run(
            [str(python), str(Path(__file__).resolve()), "--worker", str(manifest_path)],
            cwd=args.output_root,
            capture_output=True,
            check=False,
            env=worker_environment(source, args.matlab),
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        completed = None
    if not Path(manifest["result"]).is_file():
        result = {
            "schema": "sipi.p5-06.original13.shared-matlab-diagnostic.v4",
            "nonce": nonce,
            "session": {
                "engine_started": None,
                "all_cases_returned": False,
                "shutdown_complete": False,
                "worker_result_missing": True,
                "worker_timed_out": completed is None,
                "source_inventory_unchanged": inventory(source) == source_before,
            },
            "cases": [],
        }
        write_json(Path(manifest["result"]), result)
    result_path = Path(manifest["result"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["session"]["source_inventory_unchanged"] = inventory(source) == source_before
    result["worker"] = {
        "returncode": None if completed is None else completed.returncode,
        "timed_out": completed is None,
        "stdout_sha256": None if completed is None else hashlib.sha256(completed.stdout).hexdigest(),
        "stderr_sha256": None if completed is None else hashlib.sha256(completed.stderr).hexdigest(),
    }
    write_json(result_path, result)
    accepted = (
        completed is not None
        and completed.returncode == 0
        and result["session"]["all_cases_returned"]
        and result["session"]["shutdown_complete"]
        and result["session"]["source_inventory_unchanged"]
    )
    print(json.dumps({"returncode": None if completed is None else completed.returncode, "result_sha256": digest(result_path), "accepted_diagnostic_session": accepted}))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
