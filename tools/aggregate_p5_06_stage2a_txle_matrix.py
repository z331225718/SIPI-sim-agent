"""Aggregate the four immutable current P5-06 Stage 2a TXLE replays."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from .project_p5_06_stage2a_txle import compare_projected_txle_cases
except ImportError:
    from project_p5_06_stage2a_txle import compare_projected_txle_cases


ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "matlab_01": "docs/baselines/p5-06-stage2a-txle-matlab-01.v1.json",
    "matlab_02": "docs/baselines/p5-06-stage2a-txle-matlab-02.v1.json",
    "rust_01": "docs/baselines/p5-06-stage2a-txle-rust-01.v1.json",
    "rust_02": "docs/baselines/p5-06-stage2a-txle-rust-02.v1.json",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    reports = {name: json.loads((ROOT / path).read_text(encoding="utf-8")) for name, path in PATHS.items()}
    assert all(report["status"] == "fresh_matrix_run" and len(report["records"]) == 13 for report in reports.values())
    matlab_repeat = all(not compare_projected_txle_cases(a["txle_checkpoints"], b["txle_checkpoints"], 1e-12) for a, b in zip(reports["matlab_01"]["records"], reports["matlab_02"]["records"], strict=True))
    rust_repeat = all(a["txle_checkpoints"] == b["txle_checkpoints"] for a, b in zip(reports["rust_01"]["records"], reports["rust_02"]["records"], strict=True))
    cross_a = all(not compare_projected_txle_cases(a["txle_checkpoints"], b["txle_checkpoints"]) for a, b in zip(reports["matlab_01"]["records"], reports["rust_01"]["records"], strict=True))
    cross_b = all(not compare_projected_txle_cases(a["txle_checkpoints"], b["txle_checkpoints"]) for a, b in zip(reports["matlab_02"]["records"], reports["rust_02"]["records"], strict=True))
    per_workbook = [max(reports["rust_01"]["records"][i]["execution_wall_ns"], reports["rust_02"]["records"][i]["execution_wall_ns"]) <= min(reports["matlab_01"]["records"][i]["execution_wall_ns"], reports["matlab_02"]["records"][i]["execution_wall_ns"]) for i in range(13)]
    total = max(reports["rust_01"]["total_execution_wall_ns"], reports["rust_02"]["total_execution_wall_ns"]) <= min(reports["matlab_01"]["total_execution_wall_ns"], reports["matlab_02"]["total_execution_wall_ns"])
    output = {"schema": "sipi.p5-06.stage2a-txle-aggregate.v1", "status": "accepted_scoped_txle_checkpoint" if all((matlab_repeat, rust_repeat, cross_a, cross_b, all(per_workbook), total)) else "blocked", "reports": {name: {"path": path, "sha256": digest(ROOT / path)} for name, path in PATHS.items()}, "gates": {"matlab_repeat_1e_12": matlab_repeat, "rust_repeat_exact": rust_repeat, "cross_a_1e_9": cross_a, "cross_b_1e_9": cross_b, "per_workbook_rust_not_slower": all(per_workbook), "total_rust_not_slower": total}, "claims": {"txle_checkpoint_acceptance": True, "p5_06_main_closed": False, "release": False}}
    path = ROOT / "docs/baselines/p5-06-stage2a-txle-aggregate.v1.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": output["status"], "sha256": digest(path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
