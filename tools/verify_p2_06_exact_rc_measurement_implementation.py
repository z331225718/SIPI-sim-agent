"""Verify the bounded P2-06 exact RC measurement consumer record."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/baselines/p2-06-exact-rc-measurement-implementation.v1.yaml"
COMPARE_RECORD = ROOT / "docs/baselines/p2-06-exact-rc-measurement-current-external-compare.v1.yaml"
SOURCE = ROOT / "crates/sipi-tran/src/parsed_rc_measurement_v1.rs"
SCHEMA = "sipi.p2-06.exact-rc-measurement-implementation.v1"
SOURCE_SHA256 = "af16bf6503bc25a40fcb2f4c87b820dbf5b65119145264af4d79789851769d3c"
REPORT_SHA256 = "ebc5fa065cde1d35419566afc1cacafbfd450abdd199eeddaf98761180e49eb5"


class ExactRcEvidenceError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExactRcEvidenceError("record_invalid") from error
    if not isinstance(value, dict):
        raise ExactRcEvidenceError("record_invalid")
    return value


def sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ExactRcEvidenceError("source_missing") from error


def expected() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "implemented_exact_profile_external_measurement_not_bound",
        "authority": {
            "actor": "project",
            "source_audit": "docs/baselines/p2-06-bounded-measurement-source-dependency-audit.v1.yaml",
            "scope": "exact-profile parsed RC transient and one sampled MAX measurement",
        },
        "implementation": {
            "policy": "sipi.p2-06.exact-rc-measurement-deck-v1",
            "source": "crates/sipi-tran/src/parsed_rc_measurement_v1.rs",
            "source_sha256": SOURCE_SHA256,
            "accepted_order": [
                "title", "V1 in 0 PULSE", "R1 in out", "C1 out 0", ".tran",
                ".measure TRAN name MAX V(out)", ".end",
            ],
            "numeric_suffixes": ["f", "p", "n", "u", "m", "k", "meg", "g", "t"],
            "measurement_domain": "actual finite emitted V(out) samples",
            "solver": "existing one-node RC/PULSE backward-Euler kernel",
        },
        "fail_closed": {
            "non_ascii": True,
            "input_and_line_budgets": True,
            "output_and_breakpoint_budgets": True,
            "wrong_or_duplicate_lines": True,
            "wrong_elements_or_nodes": True,
            "op_or_ac_analysis": True,
            "measurement_extensions": True,
        },
        "completion": {
            "bounded_consumer_implemented": True,
            "sampled_waveform_oracle_observed": True,
            "external_measurement_result_observed": False,
            "same_input_parsed_circuit_compare": False,
            "p2_06_scoped_close": False,
            "compare_evidence": "docs/baselines/p2-06-exact-rc-measurement-current-external-compare.v1.yaml",
        },
        "non_claims": [
            "This is not a generic SPICE parser or MNA runtime.",
            "OP and AC analyses are rejected, not accepted and ignored.",
            "The external run compares waveforms and a locally reduced sampled maximum; it does not observe Agent-Spice measurement output.",
            "This exact consumer is a completed prerequisite, not a scoped closure of generalized P2-06.",
        ],
    }


def expected_compare() -> dict[str, Any]:
    return {
        "schema": "sipi.p2-06.exact-rc-measurement-current-external-compare.v1",
        "status": "waveform_observed_measurement_authority_not_bound",
        "scope": "exact bounded RC/PULSE transient plus sampled MAX V(out)",
        "external_report": {
            "schema": "sipi.p2-06.exact-rc-measurement-compare.v1",
            "sha256": REPORT_SHA256,
            "custody": "operator_external_only",
        },
        "source": {
            "commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5",
            "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402",
            "path": "native/AgentSpice.Engine/fixtures/rc.cir",
            "git_blob": "f9c29055902fe8aa2b268b4375a5bdbbf67df9da",
            "content_sha256": "bcdbd81a40dde01f0e72a8c36be928b6a7325fabbc25f83f72073757154dcefc",
            "redistribution": "external_only",
        },
        "oracle": {
            "executable_sha256": "c6e5022f0b3442cc72bef6ff54cd6116f70f2f85b3dcff91072277e534030913",
            "git_dirty": False,
            "runs": 2,
            "sample_count": 4,
        },
        "product": {
            "executable_sha256": "db68675b319cb00eac2ba1e874a67431aeac7163f20cdd07a3b9cab0977440c9",
            "runs": 2,
            "source_sha256": {
                "Cargo.lock": "feb03cb9c16268fc06a2df23573806d8b40c335757bddab412ce9f2630cd8866",
                "crates/sipi-runtime/src/lib.rs": "c2b22b3aeed6d0d4f0e40847def056619253cd4cdb83713b549d8e45d5e39e03",
                "crates/sipi-tran/Cargo.toml": "52bd5dc83f33ab1745e829f6862d7e9e39d2cbf95318d8e24fe8dfcc4fa7df5f",
                "crates/sipi-tran/src/bin/sipi_tran_exact_rc_measurement_harness.rs": "66c95d2da0b2216473772c89457a8d7a099b41507c4d57aef73e3e2da3a3ae09",
                "crates/sipi-tran/src/lib.rs": "baf7da2de3952fe992fb836113bf7d614e9e5f76849c3af74bbc85a3538ec1fb",
                "crates/sipi-tran/src/parsed_rc_measurement_v1.rs": SOURCE_SHA256,
                "crates/sipi-types/src/lib.rs": "3de5e2cb9e0875adac7f17cd3de237e3002292412b1d41ff6609b829d7af3a18",
            },
        },
        "comparison": {
            "time_axis_seconds_max_absolute_error": 0.0,
            "voltage_in_volts_max_absolute_error": 0.0,
            "voltage_out_volts_max_absolute_error": 9.963737488231927e-7,
            "max_v_out_volts_max_absolute_error": 9.963737488231927e-7,
            "voltage_absolute_tolerance": 2.0e-6,
            "voltage_relative_tolerance": 5.0e-4,
        },
        "closure": {
            "exact_profile_scoped_close": False,
            "same_input_parsed_circuit_compare": False,
            "external_measurement_result_observed": False,
            "sampled_max_reduced_by_product_comparator": True,
            "generic_spice_or_mna": False,
            "op_or_ac": False,
            "general_measurements": False,
        },
    }


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    if document != expected():
        raise ExactRcEvidenceError("record_content_invalid")
    return {"valid": True, "status": document["status"]}


def verify(root: Path = ROOT, report_path: Path | None = None) -> dict[str, Any]:
    document = load(root / RECORD.relative_to(ROOT))
    result = validate_document(document)
    compare = load(root / COMPARE_RECORD.relative_to(ROOT))
    if compare != expected_compare():
        raise ExactRcEvidenceError("compare_record_invalid")
    source = root / SOURCE.relative_to(ROOT)
    if sha256(source) != SOURCE_SHA256:
        raise ExactRcEvidenceError("source_hash_drift")
    text = source.read_text(encoding="utf-8")
    markers = (
        "parse_exact_rc_measurement_deck_v1",
        "simulate_one_node_rc_pulse(",
        "UnsupportedAnalysis",
        ".measure",
        "reduce(f64::max)",
    )
    if any(marker not in text for marker in markers):
        raise ExactRcEvidenceError("implementation_marker_missing")
    for relative, expected_hash in compare["product"]["source_sha256"].items():
        if sha256(root / relative) != expected_hash:
            raise ExactRcEvidenceError(f"product_source_drift:{relative}")
    if report_path is not None:
        if sha256(report_path) != REPORT_SHA256:
            raise ExactRcEvidenceError("external_report_hash_mismatch")
        report = load(report_path)
        if report.get("schema") != compare["external_report"]["schema"] or report.get("accepted") is not True:
            raise ExactRcEvidenceError("external_report_invalid")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps({"schema": SCHEMA, **verify(args.root, args.report)}, sort_keys=True))
        return 0
    except ExactRcEvidenceError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
