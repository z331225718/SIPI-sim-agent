"""Verify the additive original-13 MATLAB scalar-reference custody record."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

try:
    from .run_p5_06_original13_fresh_matrix import METRICS, digest
    from .verify_p5_06_original13_root_matrix_v6 import verify as verify_v6_report
except ImportError:
    from run_p5_06_original13_fresh_matrix import METRICS, digest
    from verify_p5_06_original13_root_matrix_v6 import verify as verify_v6_report


HEX = re.compile(r"^[0-9a-f]{64}$")
MANIFEST = "docs/baselines/p5-06-original13-scalar-reference-custody.v2.yaml"


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def canonical_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def scalar_bundle(report: dict[str, object]) -> str:
    """Hash ordered scalar slots using an explicit, platform-independent encoding."""
    out = hashlib.sha256(b"sipi.p5-06.original13.scalar-reference-bundle.v2\0")

    def field(value: str) -> None:
        encoded = value.encode("utf-8")
        out.update(struct.pack("<I", len(encoded)))
        out.update(encoded)

    records = report.get("records")
    require(isinstance(records, list), "bundle records")
    for record in records:
        require(isinstance(record, dict), "bundle record")
        workbook_index = record.get("workbook_index")
        cases = record.get("metrics")
        require(isinstance(workbook_index, int) and isinstance(cases, list), "bundle coordinates")
        for case_index, case in enumerate(cases):
            require(isinstance(case, dict), "bundle case")
            for metric_name in METRICS:
                if metric_name not in case:
                    continue
                value = case[metric_name]
                field(str(workbook_index))
                field(str(case_index))
                field(metric_name)
                if isinstance(value, bool):
                    raise VerificationError("boolean scalar")
                if isinstance(value, (int, float)):
                    number = float(value)
                    require(math.isfinite(number), "nonfinite numeric scalar")
                    out.update(b"F")
                    out.update(struct.pack("<d", number))
                elif value == "+Inf":
                    out.update(b"P")
                elif value == "-Inf":
                    out.update(b"M")
                else:
                    raise VerificationError("scalar token")
    return out.hexdigest()


def normalized_input_bundle(report: dict[str, object]) -> str:
    records = report.get("records")
    require(isinstance(records, list), "normalized records")
    normalized_records = []
    for record in records:
        require(isinstance(record, dict), "normalized record")
        materialization = record.get("config_materialization")
        require(isinstance(materialization, dict), "normalized MATLAB materialization")
        normalized_records.append({
            "workbook_index": record.get("workbook_index"),
            "workbook": record.get("workbook"),
            "case_count": record.get("case_count"),
            "parameter_shape": materialization.get("parameter_shape"),
            "parameter_slot_digest": materialization.get("parameter_slot_digest"),
            "pinned_sha256": materialization.get("pinned_sha256"),
            "rust_sha256": materialization.get("rust_sha256"),
        })
    return canonical_digest({"channels": report.get("channels"), "records": normalized_records})


def scalar_slots(report: dict[str, object]) -> list[tuple[int, int, str, object]]:
    slots: list[tuple[int, int, str, object]] = []
    for record in report["records"]:
        for case_index, case in enumerate(record["metrics"]):
            for metric_name in METRICS:
                if metric_name in case:
                    slots.append((record["workbook_index"], case_index, metric_name, case[metric_name]))
    return slots


def compare_scalar(left: object, right: object, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(float(left)) and math.isfinite(float(right)) and abs(float(left) - float(right)) <= tolerance
    return left == right and left in ("+Inf", "-Inf")


def read_json(root: Path, relative: str) -> dict[str, object]:
    path = root / relative
    require(path.is_file(), f"missing {relative}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"object {relative}")
    return value


def require_file(root: Path, receipt: object) -> None:
    require(isinstance(receipt, dict) and set(receipt) == {"path", "bytes", "sha256"}, "file receipt shape")
    path = receipt.get("path")
    require(isinstance(path, str) and not Path(path).is_absolute() and ".." not in Path(path).parts, "safe receipt path")
    local = root / path
    require(local.is_file() and local.stat().st_size == receipt.get("bytes") and digest(local) == receipt.get("sha256"), f"file receipt {path}")


def validate(document: object, root: Path) -> dict[str, object]:
    require(isinstance(document, dict), "manifest")
    expected = {
        "schema", "status", "basis", "scope", "normalized_inputs", "oracle_runtime", "reference_bundle",
        "comparison_policy", "custody", "reports", "aggregate", "audit", "gate_tools", "claims", "non_claims",
    }
    require(set(document) == expected, "manifest keys")
    require(document["schema"] == "sipi.p5-06.original13-scalar-reference-custody.v2", "schema")
    require(document["status"] == "accepted_current_original13_scalar_reference", "status")
    require(document["scope"] == {"route": ["com", "run"], "workbooks": 13, "package_cases": 28, "scalar_slots": 303, "channels": ["THRU", "FEXT", "NEXT"]}, "scope")
    basis = document["basis"]
    require(isinstance(basis, dict) and set(basis) == {"path", "sha256"} and basis["path"] == "docs/baselines/p5-06-original13-root-matrix-v6-acceptance.v1.yaml" and isinstance(basis["sha256"], str) and HEX.fullmatch(basis["sha256"]), "basis receipt")
    require(digest(root / basis["path"]) == basis["sha256"], "basis drift")

    reports = document["reports"]
    require(isinstance(reports, list) and len(reports) == 4, "reports")
    engines = ("matlab", "matlab", "rust", "rust")
    loaded: list[dict[str, object]] = []
    report_hashes: list[str] = []
    for receipt, engine in zip(reports, engines):
        require(isinstance(receipt, dict) and set(receipt) == {"path", "engine", "bytes", "sha256"} and receipt["engine"] == engine, "report receipt")
        require_file(root, {key: receipt[key] for key in ("path", "bytes", "sha256")})
        report = read_json(root, receipt["path"])
        verify_v6_report(report)
        require(report["engine"] == engine, "report engine")
        loaded.append(report)
        report_hashes.append(receipt["sha256"])
    require(len(set(report_hashes)) == 4, "reused report")
    require(len({report["run_id"] for report in loaded}) == 4 and len({report["nonce"] for report in loaded}) == 4 and len({report["root_id"] for report in loaded}) == 4, "reused run identity")

    aggregate = document["aggregate"]
    require_file(root, aggregate)
    aggregate_data = read_json(root, aggregate["path"])
    require(aggregate_data.get("status") == "accepted_stage1" and aggregate_data.get("gates") == {
        "matlab_repeat_1e_12": True, "rust_repeat_exact": True, "rust_vs_matlab_1e_9": True,
        "per_workbook_rust_not_slower": True, "total_rust_not_slower": True,
    }, "aggregate acceptance")
    require([entry.get("report_sha256") for entry in aggregate_data.get("runs", [])] == report_hashes, "aggregate report order")

    matlab_a, matlab_b, rust_a, rust_b = loaded
    require(normalized_input_bundle(matlab_a) == normalized_input_bundle(matlab_b), "normalized input repeat drift")
    for rust in (rust_a, rust_b):
        require([(record["workbook"], record["case_count"]) for record in rust["records"]] == [(record["workbook"], record["case_count"]) for record in matlab_a["records"]], "candidate input surface drift")
        require(rust["channels"] == matlab_a["channels"], "candidate channel drift")
    normalized = document["normalized_inputs"]
    require(normalized == {"encoding": "canonical-json-sha256-v1", "sha256": normalized_input_bundle(matlab_a)}, "normalized input custody")

    reference = document["reference_bundle"]
    expected_reference = {
        "encoding": "domain-separated-scalar-slots-v2-f64le", "matlab_sha256": scalar_bundle(matlab_a),
        "rust_sha256": scalar_bundle(rust_a),
    }
    require(reference == expected_reference, "reference bundle custody")
    require(scalar_bundle(matlab_a) == scalar_bundle(matlab_b), "MATLAB reference bundle drift")
    require(scalar_bundle(rust_a) == scalar_bundle(rust_b), "Rust candidate bundle drift")
    matlab_slots = scalar_slots(matlab_a)
    rust_slots = scalar_slots(rust_a)
    require(len(matlab_slots) == len(rust_slots) == 303, "scalar slot count")
    require(all(left[:3] == right[:3] and compare_scalar(left[3], right[3], 1.0e-9) for left, right in zip(matlab_slots, rust_slots)), "cross scalar mismatch")

    require(document["comparison_policy"] == {"matlab_repeat_tolerance": 1.0e-12, "rust_repeat": "exact", "cross_tolerance": 1.0e-9, "slot_order": "workbook_index,case_index,runner_METRICS_order", "finite_only": True, "same_sign_infinity_only": True, "nan": "rejected", "alignment": "forbidden"}, "comparison policy")
    source = matlab_a["source"]
    require(document["oracle_runtime"] == {"matlab": source["toolchain"]["matlab"], "python": source["toolchain"]["python"], "upstream": source["upstream"], "harness": source["gate_tools"]["matlab_harness"]}, "oracle runtime custody")
    for report in loaded[1:]:
        require(report["source"]["upstream"] == source["upstream"] and report["source"]["toolchain"] == source["toolchain"], "oracle runtime drift")

    custody = document["custody"]
    require(custody == {"report_paths_distinct": True, "report_sha256_distinct": True, "root_id_distinct": True, "run_id_distinct": True, "nonce_distinct": True, "source_inventory_unchanged": True, "paths": "redacted_or_repo_relative", "payload_location": "docs/baselines"}, "custody policy")
    require(all(record["source_inventory_unchanged"] is True for report in loaded for record in report["records"]), "inventory drift")

    gate_tools = document["gate_tools"]
    require(isinstance(gate_tools, dict) and set(gate_tools) == {"runner", "aggregate", "report_verifier", "tests"}, "gate tool keys")
    for receipt in gate_tools.values():
        require_file(root, receipt)
    require(document["claims"] == {"current_original13_scalar_reference": True, "matlab_one_to_one": True, "public_root_route": True, "array_acceptance": False, "warning_or_full_result_graph_acceptance": False, "release": False}, "claims")
    require(document["non_claims"] == ["no_legacy_three_metric_contract_claim", "no_array_or_intermediate_checkpoint_acceptance", "no_warning_or_full_result_graph_acceptance", "no_generalized_com_acceptance", "no_ieee_certification", "no_release"], "non claims")
    audit = document["audit"]
    require_file(root, audit)
    return {"valid": True, "status": document["status"], "matlab_reference_sha256": scalar_bundle(matlab_a), "rust_candidate_sha256": scalar_bundle(rust_a)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--manifest", default=MANIFEST)
    args = parser.parse_args()
    root = args.root.resolve()
    document = read_json(root, args.manifest)
    print(json.dumps(validate(document, root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
