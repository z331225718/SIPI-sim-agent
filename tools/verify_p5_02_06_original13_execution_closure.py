"""Verify the owner-selected original-13 COM execution closure."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .verify_p5_06_original13_root_matrix_v6 import verify as verify_root_report
    from .verify_p5_06_original13_scalar_reference_custody import validate as validate_scalar_custody
    from .verify_p5_06_tdiln_array_b9 import verify as verify_tdiln
except ImportError:
    from verify_p5_06_original13_root_matrix_v6 import verify as verify_root_report
    from verify_p5_06_original13_scalar_reference_custody import validate as validate_scalar_custody
    from verify_p5_06_tdiln_array_b9 import verify as verify_tdiln


MANIFEST = "docs/baselines/p5-02-06-original13-execution-closure.v1.yaml"
ROOT_REPORTS = (
    "docs/baselines/p5-06-original13-root-matrix-v6-matlab-01.json",
    "docs/baselines/p5-06-original13-root-matrix-v6-matlab-02.json",
    "docs/baselines/p5-06-original13-root-matrix-v6-rust-01.json",
    "docs/baselines/p5-06-original13-root-matrix-v6-rust-02.json",
)
EXPECTED_EVIDENCE = {
    "root_scalar_and_materialization": (
        "docs/baselines/p5-06-original13-root-matrix-v6-acceptance.v1.yaml",
        "8b692c8d4b21d129586dc5368b61246ad5d0d93ea885263f160aa29e1c1c183b",
    ),
    "scalar_reference_custody": (
        "docs/baselines/p5-06-original13-scalar-reference-custody.v2.yaml",
        "7b0fb5a34b066edef52d7fd377206b33ea2b2fe12fc79ac02c9bcbaf595d8808",
    ),
    "tdiln_named_arrays": (
        "docs/baselines/p5-06-tdiln-array-b9-acceptance.v1.yaml",
        "cdd863cf2b8b8370c300a6da2d96e11905b1316f3bd828df3d21ac191f083481",
    ),
    "source_warning_observation": (
        "docs/baselines/p5-06w-source-warning-observation.v1.yaml",
        "ac80d296fc7271a5834c4a1099b3b2a7d663f1a6cb97d50b8566430396e77936",
    ),
}
EXPECTED_SCOPE = {
    "workbooks": 13,
    "package_cases": 28,
    "channel_roles": ["THRU", "FEXT", "NEXT"],
    "matlab_release": "R2024b",
    "candidate": {
        "commit": "b9b195a19d3d209a37a52ba29c730759361dba03",
        "tree": "becca5842b55eeb1d1a310b2c3174458936ec901",
        "archive_sha256": "4e40155745d439a721e0f9923a36a60c9daf2404ff24f574b12a4fd7d425a8a2",
    },
    "upstream": {
        "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
        "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
        "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",
    },
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(root: Path) -> dict[str, object]:
    value = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    expected = {
        "schema", "status", "scope", "evidence", "accepted_surface", "warning_contract",
        "performance", "claims", "non_claims", "audit",
    }
    require(isinstance(value, dict) and set(value) == expected, "manifest keys")
    require(value["schema"] == "sipi.p5-02-06.original13-execution-closure.v1", "schema")
    require(value["status"] == "accepted_selected_original13_execution_surface", "status")
    require(value["scope"] == EXPECTED_SCOPE, "scope")
    require(value["evidence"] == {key: {"path": path, "sha256": digest} for key, (path, digest) in EXPECTED_EVIDENCE.items()}, "evidence")
    require(value["accepted_surface"] == {
        "workbook_cell_matrix_custody": True,
        "runtime_consumed_parameter_and_option_projection": True,
        "matlab_parameter_slot_matrix_observed": True,
        "final_scalar_slots": 303,
        "tdiln_named_vectors": ["time_s", "iln_pulse", "reference_pulse", "fitted_pulse", "pdf_axis", "pdf_probability"],
        "raw_fd_to_td_impulse_without_s_parameter_fit": True,
    }, "accepted surface")
    require(value["warning_contract"] == {
        "source_observed_callsite_lines": [6337, 9715],
        "mapped_callsite": {"identifier": "COM:read_s4p:MaxFreqTooLow", "source_line": 9715, "exact_occurrence_mapping": True},
        "bounded_exception": {"source_line": 6337, "classification": "platform_roundoff_sensitive_nonfunctional_trace_difference", "source_warning_equivalent": False, "blocks_selected_execution_acceptance": False},
    }, "warning contract")
    require(value["performance"] == {"per_workbook_rust_not_slower": True, "total_rust_not_slower": True, "minimum_bound_speedup": 9.237029377981356}, "performance")
    require(value["claims"] == {
        "p5_02_selected_original13_parameter_default_consumption_accepted": True,
        "p5_06_selected_original13_matlab_execution_accepted": True,
        "p5_06_selected_original13_performance_accepted": True,
        "complete_warning_catalog": False,
        "full_result_graph": False,
        "generalized_com_conformance": False,
        "ieee_certification": False,
        "release": False,
    }, "claims")
    require(value["non_claims"] == [
        "no_unselected_workbook_or_profile_claim", "no_full_matlab_result_graph_claim",
        "no_complete_warning_catalog_claim", "no_s_parameter_fit", "no_ieee_certification", "no_release",
    ], "non claims")
    require(value["audit"] == "docs/baselines/audits/2026-09-01-p5-02-06-original13-execution-closure.md", "audit path")
    return value


def verify(root: Path) -> dict[str, str]:
    manifest = load_manifest(root)
    for key, (relative, digest) in EXPECTED_EVIDENCE.items():
        path = root / relative
        require(path.is_file() and sha256(path) == digest, f"evidence drift: {key}")
    audit = root / str(manifest["audit"])
    require(audit.is_file() and "weakest bound remains 9.237x" in audit.read_text(encoding="utf-8"), "audit")

    root_reports = [json.loads((root / relative).read_text(encoding="utf-8")) for relative in ROOT_REPORTS]
    for report in root_reports:
        require(verify_root_report(report), "root report")
    scalar_manifest = json.loads(
        (root / EXPECTED_EVIDENCE["scalar_reference_custody"][0]).read_text(encoding="utf-8")
    )
    require(validate_scalar_custody(scalar_manifest, root).get("valid") is True, "scalar custody")
    require(verify_tdiln(root).get("valid") == "true", "TDILN")

    matlab = root_reports[:2]
    for report in matlab:
        records = report["records"]
        require(len(records) == 13, "MATLAB workbook count")
        for record in records:
            materialization = record["config_materialization"]
            require(materialization["comparison"] == "equal" and materialization["first_difference"] is None, "materialization")
            require(materialization["pinned_sha256"] == materialization["rust_sha256"], "parameter projection")
    warning_text = (root / EXPECTED_EVIDENCE["source_warning_observation"][0]).read_text(encoding="utf-8")
    require("matched_for_every_observed_occurrence: true" in warning_text, "mapped warning")
    require("status: roundoff_sensitive_trace_mismatch" in warning_text, "warning exception")
    return {"schema": "sipi.p5-02-06.original13-execution-closure.verifier.v1", "valid": "true"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(verify(args.root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
