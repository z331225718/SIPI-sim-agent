"""Verify the immutable, scoped P5-06 Stage 2b DFE checkpoint record."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any



ARTIFACTS = {
    "matlab_01": ("docs/baselines/p5-06-stage2b-dfe-matlab-01.v1.json", "be3fa58b5ea435e647cf0ba0fed4cbbff27b06e2597f55f7fd723d17f46b8c90"),
    "matlab_02": ("docs/baselines/p5-06-stage2b-dfe-matlab-02.v1.json", "2e2e90ab73f49f76c1aebbe7dd1644dba27c1d197a0f7f929b8574116bcf382e"),
    "rust_01": ("docs/baselines/p5-06-stage2b-dfe-rust-01.v1.json", "de1f440be7dfda78593fbad7d1de735cf68ea912dc5d31e181a38daf70a6f45b"),
    "rust_02": ("docs/baselines/p5-06-stage2b-dfe-rust-02.v1.json", "aaf6829f91b0d7e7c9198a14075a01f7913c98a0b48e57af3103028adcdccb3d"),
    "aggregate": ("docs/baselines/p5-06-stage2b-dfe-aggregate.v1.json", "f6a2a6d33bf12cd0f761baa0bda86c7a987888874b6fd5bdfd27c13c7fe3eb6b"),
}
TOOLS = {
    "aggregate": ("tools/aggregate_p5_06_stage2b_dfe_matrix.py", "6af0640e84c4eb496716be4a86517432bd7c649bc262498adb8ae6ce55db21a5"),
    "runner": ("tools/run_p5_06_stage2b_dfe_matrix.py", "4a37c0a5536211f36d219f09a99f84ca339123fd39084969992acceb65aa2c26"),
    "projector": ("tools/project_p5_06_stage2b_dfe.py", "17a6a34c3b6b9df00c529ce335b2df2ffba5b3f90476a88dfa1053bb63ba7dc8"),
    "matlab_harness": ("tools/sipi_com_dfe_checkpoint_oracle_v1.m", "f7e14d955a116196d5fabc7899d5fb1c5cdf9330c87054d283613c02041f4cf3"),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_document(document: Any) -> None:
    require(isinstance(document, dict), "manifest mapping")
    required = {"schema", "status", "scope", "artifacts", "gate_tools", "gates", "performance", "claims", "non_claims"}
    require(set(document) == required, "manifest keys")
    require(document["schema"] == "sipi.p5-06.stage2b-dfe-checkpoint-acceptance.v1" and document["status"] == "accepted_scoped_dfe_checkpoint", "manifest status")
    scope = document["scope"]
    require(isinstance(scope, dict) and scope["original_workbook_count"] == 13 and scope["eligible_dfe_case_count"] == 25 and scope["source_precision_transport"] == "ieee754_f64_little_endian_hex_receipt", "scope")
    require(scope["finite_tolerance"] == 1.0e-9 and scope["matlab_repeat_tolerance"] == 1.0e-12, "tolerances")
    require(document["artifacts"] == {key: {"path": path, "sha256": digest} for key, (path, digest) in ARTIFACTS.items()}, "artifact receipts")
    require(document["gate_tools"] == {key: {"path": path, "sha256": digest} for key, (path, digest) in TOOLS.items()}, "tool receipts")
    require(document["gates"] == {"matlab_repeat_1e_12": True, "rust_repeat_exact": True, "rust_vs_matlab_1e_9_run_a": True, "rust_vs_matlab_1e_9_run_b": True, "per_workbook_rust_not_slower": True, "total_rust_not_slower": True}, "gates")
    require(document["performance"] == {"matlab_best_total_wall_ns": 1613483260500, "rust_worst_total_wall_ns": 157375059000, "fixed_deployment_speedup_min": 10.252471203203806}, "performance")
    require(document["claims"] == {"stage2b_dfe_checkpoint_acceptance": True, "p5_06_main_closed": False, "full_intermediate_array_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True}, "claims")


def verify(root: Path) -> dict[str, str]:
    manifest = root / "docs/baselines/p5-06-stage2b-dfe-checkpoint-acceptance.v1.yaml"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    validate_document(document)
    for path, receipt in [*ARTIFACTS.values(), *TOOLS.values()]:
        require(sha256(root / path) == receipt, f"receipt drift: {path}")
    aggregate = json.loads((root / ARTIFACTS["aggregate"][0]).read_text(encoding="utf-8"))
    require(aggregate["schema"] == "sipi.p5-06.stage2b-dfe-checkpoint-aggregate.v1" and aggregate["status"] == "accepted_stage2b_dfe_checkpoint", "aggregate status")
    require(aggregate["matrix"] == {"workbook_count": 13, "eligible_dfe_case_count": 25}, "aggregate matrix")
    require(aggregate["gates"] == document["gates"], "aggregate gates")
    require(aggregate["performance"] == {"per_workbook": aggregate["performance"]["per_workbook"], **document["performance"]}, "aggregate performance")
    require(aggregate["claims"] == {"stage2b_dfe_checkpoint_acceptance": True, "p5_06_main_closed": False, "array_acceptance": False, "release": False, "s_parameter_fit": False, "one_final_fd_to_td_impulse": True}, "aggregate claims")
    return {"valid": "true", "manifest_sha256": sha256(manifest), "aggregate_sha256": sha256(root / ARTIFACTS["aggregate"][0])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
