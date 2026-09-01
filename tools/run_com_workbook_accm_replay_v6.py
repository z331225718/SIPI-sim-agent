"""Current-candidate external Agent-COM replay for the two-workbook ACCM slice.

This deliberately reuses v5's archive materialization, toolchain custody,
and real upstream `uv --frozen --offline` invocation.  v6 changes only the
observed current result projection: current Rust publishes DFE values, while
the upstream public `RunResult` still has no port-order field to compare.
"""

from __future__ import annotations

import argparse
import json
import math
import secrets
from pathlib import Path
from typing import Any

try:
    from tools import run_com_workbook_accm_replay_v5 as legacy
except ModuleNotFoundError as error:
    if error.name != "tools":
        raise
    import run_com_workbook_accm_replay_v5 as legacy


CANDIDATE_COMMIT = "b1cc58842bdf19b2085a4dcd3733788b11ee3af3"
CANDIDATE_TREE = "0f198735134f7dd03733006fa0e3b60b70854722"
CANDIDATE_ARCHIVE_SHA256 = "4764945edce6f42b799b0a34f95816ecf52c1081af1895280efd797fb99b0631"
CANDIDATE_ARCHIVE_BYTES = 59_648_000
NUMERIC_TOLERANCE = 1.0e-9
STATUS = "scoped_numeric_parity_observed"
COMMON_METRIC_KEYS = ("FOM", "COM_dB", "VEC_dB", "VEO_mV", "sigma_N_V")


def configure_legacy() -> None:
    """Bind the inherited custody runner to this immutable candidate."""
    legacy.CANDIDATE_COMMIT = CANDIDATE_COMMIT
    legacy.CANDIDATE_TREE = CANDIDATE_TREE
    legacy.CANDIDATE_ARCHIVE_SHA256 = CANDIDATE_ARCHIVE_SHA256
    legacy.CANDIDATE_ARCHIVE_BYTES = CANDIDATE_ARCHIVE_BYTES


def numeric_match(comparison: dict[str, Any]) -> bool:
    """Require every published scalar in the selected public projection."""
    if comparison.get("cursor_index_match") is not True:
        return False
    for key in ("sigma_n_v_abs_delta", "fom_db_abs_delta"):
        value = comparison.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not math.isfinite(float(value)) or float(value) > NUMERIC_TOLERANCE:
            return False
    metrics = comparison.get("metric_abs_delta")
    if not isinstance(metrics, dict) or set(metrics) != set(legacy.METRIC_KEYS):
        return False
    for key in COMMON_METRIC_KEYS:
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not math.isfinite(float(value)) or float(value) > NUMERIC_TOLERANCE:
            return False
    # The remaining candidate values have no corresponding upstream public
    # RunResult field. They are retained in the receipt but not promoted to
    # a fabricated equality assertion.
    if any(metrics.get(key) is not None for key in set(metrics) - set(COMMON_METRIC_KEYS)):
        return False
    dfe = comparison.get("dfe")
    return isinstance(dfe, dict) and dfe.get("upstream_published") is True and dfe.get("candidate_published") is True


def normalize(report: dict[str, Any]) -> dict[str, Any]:
    """Replace v5's historical missing-DFE/port-wire conclusion, not its I/O."""
    if not isinstance(report, dict) or report.get("schema") not in {
        "sipi.com.workbook-accm-replay.v5.diagnostic",
        "sipi.com.workbook-accm-replay.v6.diagnostic",
    }:
        raise ValueError("unexpected v5 replay report")
    controls = report.get("controls")
    if not isinstance(controls, list) or len(controls) != len(legacy.CONTROL_VECTORS):
        raise ValueError("control matrix is missing")
    projected_controls: list[dict[str, Any]] = []
    for control in controls:
        if not isinstance(control, dict):
            raise ValueError("control is malformed")
        comparisons = control.get("comparison")
        if not isinstance(comparisons, list) or len(comparisons) != 2:
            raise ValueError("case comparison is missing")
        projected = []
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                raise ValueError("comparison is malformed")
            item = dict(comparison)
            # Agent-COM uses this internally but does not include it in its
            # public RunResult. Its absence is not a numeric mismatch.
            item["port_order_public_result"] = "not_exposed_by_upstream"
            item["numeric_within_tolerance"] = numeric_match(item)
            projected.append(item)
        projected_controls.append({**control, "comparison": projected})
    blockers = [
        blocker
        for blocker in report.get("blockers", [])
        if blocker != "candidate_dfe_taps_not_published"
    ]
    matched = not blockers and all(
        comparison["numeric_within_tolerance"]
        for control in projected_controls
        for comparison in control["comparison"]
    )
    return {
        **report,
        "schema": "sipi.com.workbook-accm-replay.v6.diagnostic",
        "status": STATUS if matched else "blocked",
        "matched": matched,
        "acceptance": False,
        "blockers": sorted(set(blockers)),
        "controls": projected_controls,
        "port_order": {
            "source_key": "Port Order",
            "source_cell": "COM_Settings!G7",
            "one_based": legacy.PORT_ORDER,
            "public_result_comparison": "not_exposed_by_upstream",
        },
        "non_claims": [
            "no S-parameter fit",
            "channel uses one final FD-to-TD impulse",
            "no full Agent-COM result-graph parity",
            "no release or promotion claim",
            "no generic COM profile claim",
        ],
    }


def run_one(
    repo: Path,
    upstream_repo: Path,
    scratch_root: Path,
    cargo: Path,
    python: Path,
    run_id: str,
    nonce: str,
    *,
    uv: Path | None = None,
    rustc: Path | None = None,
) -> dict[str, Any]:
    configure_legacy()
    report = legacy.run_one(
        repo,
        upstream_repo,
        scratch_root,
        cargo,
        python,
        run_id,
        nonce,
        uv=uv,
        rustc=rustc,
    )
    return normalize(report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--run-id", default=secrets.token_hex(32))
    parser.add_argument("--nonce", default=secrets.token_hex(32))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run_one(
        args.repo,
        args.upstream_repo,
        args.scratch_root,
        args.cargo,
        args.python,
        args.run_id,
        args.nonce,
        uv=args.uv,
        rustc=args.rustc,
    )
    legacy.assert_report_path_free(result)
    if args.report.exists():
        raise FileExistsError("report path already exists")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "run_id": result["run_id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
