"""Observe one bounded source-native DFE shape before Stage 2b replay.

This is deliberately a source observation, not an acceptance runner.  It
executes the pinned MATLAB core once through the DFE-only harness and records
the source's native vector shape, axis metadata and f64 receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
from pathlib import Path

try:
    from .project_p5_06_stage2b_dfe import project_matlab_summary
    from .run_p5_06_original13_fresh_matrix import (
        CHANNELS, CONFIG_PATHS, UPSTREAM, bounded, canonical, digest, inventory,
        materialize, prepare_matlab_engine, tool_receipt, worker_environment,
    )
    from .run_p5_06_stage2a_txle_matrix import MATLAB_RECEIPT, require_matlab_r2024b
except ImportError:
    from project_p5_06_stage2b_dfe import project_matlab_summary
    from run_p5_06_original13_fresh_matrix import (
        CHANNELS, CONFIG_PATHS, UPSTREAM, bounded, canonical, digest, inventory,
        materialize, prepare_matlab_engine, tool_receipt, worker_environment,
    )
    from run_p5_06_stage2a_txle_matrix import MATLAB_RECEIPT, require_matlab_r2024b


HARNESS = Path(__file__).with_name("sipi_com_dfe_checkpoint_oracle_v1.m")


def require_archive(path: Path) -> None:
    if not path.is_file() or path.stat().st_size != UPSTREAM[3] or digest(path) != UPSTREAM[2]:
        raise RuntimeError("upstream archive identity drift")


def file_identity(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"required tool missing: {path.name}")
    return {"path": f"tools/{path.name}", "bytes": path.stat().st_size, "sha256": digest(path)}


def dfe_engine_worker(spec_path: str) -> None:
    import numpy as np
    from scipy.io import savemat
    import matlab.engine
    from agent_com.config import ComSettings

    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    config, mat, output = Path(spec["config"]), Path(spec["mat"]), Path(spec["output"])
    settings = ComSettings.from_xlsx(config)
    rows = settings.rows
    columns = max(len(row) for row in rows)
    parameter = np.empty((len(rows), columns), dtype=object)
    slots = []
    for row_index, row in enumerate(rows):
        for column_index in range(columns):
            raw = row[column_index].value if column_index < len(row) else None
            if raw is None:
                value, kind = "", "blank"
            elif isinstance(raw, (bool, int, float, np.integer, np.floating)):
                value, kind = float(raw), "number"
            elif isinstance(raw, str):
                value, kind = raw, "string"
            else:
                raise TypeError(f"unsupported workbook cell type: {type(raw).__name__}")
            parameter[row_index, column_index] = value
            slots.append({"row": row_index, "column": column_index, "kind": kind, "value": value})
    savemat(mat, {"parameter": parameter}, do_compression=False, oned_as="row")
    engine = matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.cd(str(output.parent), nargout=0)
        engine.addpath(str(HARNESS.parent), nargout=0)
        engine.sipi_com_dfe_checkpoint_oracle_v1(
            spec["upstream"], str(mat), str(output), float(1), float(1),
            spec["run_nonce"], *spec["channels"], nargout=0,
        )
    finally:
        engine.quit()
    logical = {"shape": [len(rows), columns], "slots": slots}
    Path(spec["worker_result"]).write_text(json.dumps({
        "parameter_shape": logical["shape"],
        "parameter_slot_digest": hashlib.sha256(canonical(logical)).hexdigest(),
        "parameter_mat_bytes": mat.stat().st_size,
        "parameter_mat_sha256": digest(mat),
    }, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--matlab", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--workbook-index", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.report.exists() or args.output_root.exists() or not 0 <= args.workbook_index < len(CONFIG_PATHS):
        raise ValueError("fresh paths and one original-13 workbook index are required")
    require_archive(args.upstream_archive)
    if not HARNESS.is_file():
        raise RuntimeError("DFE harness missing")

    args.output_root.mkdir(parents=True)
    source = args.output_root / "upstream-source"
    materialize(args.upstream_archive, source)
    before = inventory(source)
    environment = args.output_root / "python-env"
    sync_env = os.environ.copy()
    sync_env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    synced = bounded([
        str(args.uv), "sync", "--frozen", "--offline", "--no-install-project", "--python", str(args.python)
    ], source, 300, sync_env)
    worker_python = environment / "Scripts" / "python.exe"
    if synced.returncode or not worker_python.is_file():
        raise RuntimeError("pinned Python environment failed")
    engine_site = prepare_matlab_engine(worker_python, args.uv, args.matlab, args.output_root)
    case_root = args.output_root / "case"
    case_root.mkdir()
    config = source / CONFIG_PATHS[args.workbook_index]
    output = case_root / "matlab"
    output.mkdir()
    spec_path = case_root / "engine-spec.json"
    worker_result = case_root / "engine-result.json"
    nonce = secrets.token_hex(32)
    spec_path.write_text(json.dumps({
        "upstream": str(source), "config": str(config), "mat": str(case_root / "parameter.mat"),
        "output": str(output), "channels": [str(source / path) for _, path, _, _ in CHANNELS],
        "worker_result": str(worker_result), "run_nonce": nonce,
    }), encoding="utf-8")
    run = bounded([str(worker_python), str(Path(__file__).resolve()), "--engine-worker", str(spec_path)], case_root, args.timeout, worker_environment(source, engine_site))
    summary_path = output / "summary.json"
    if run.returncode or not summary_path.is_file() or not worker_result.is_file() or inventory(source) != before:
        raise RuntimeError("source DFE shape observation failed or modified archive")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("matlab_release") != "2024b":
        raise RuntimeError("MATLAB Engine did not report R2024b")
    projected = project_matlab_summary(summary)
    worker = json.loads(worker_result.read_text(encoding="utf-8"))
    size, sha = before[CONFIG_PATHS[args.workbook_index]]
    report = {
        "schema": "sipi.p5-06.stage2b-dfe-shape-observation.v1",
        "status": "source_shape_observed_not_acceptance",
        "run_id": f"stage2b-dfe-shape-{nonce}", "nonce": nonce,
        "source": {
            "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "archive_sha256": UPSTREAM[2], "archive_bytes": UPSTREAM[3]},
            "toolchain": {"uv": tool_receipt(args.uv, "uv"), "matlab": require_matlab_r2024b(args.matlab), "python": tool_receipt(args.python, "python")},
            "gate_tools": {"runner": file_identity(Path(__file__)), "matlab_harness": file_identity(HARNESS), "projection": file_identity(Path(__file__).with_name("project_p5_06_stage2b_dfe.py"))},
        },
        "workbook": {"index": args.workbook_index, "path": CONFIG_PATHS[args.workbook_index], "bytes": size, "sha256": sha},
        "parameter_mat": worker,
        "dfe_checkpoints": projected,
        "claims": {"acceptance": False, "dfe_parity": False, "release": False},
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "report_sha256": digest(args.report), "eligible_cases": len(projected)}))
    return 0


if __name__ == "__main__":
    if len(os.sys.argv) == 3 and os.sys.argv[1] == "--engine-worker":
        dfe_engine_worker(os.sys.argv[2])
    else:
        raise SystemExit(main())
