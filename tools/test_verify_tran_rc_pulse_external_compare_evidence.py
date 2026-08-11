"""Tests for the fixed TRAN external comparison evidence verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("tran_evidence", ROOT / "tools" / "verify_tran_rc_pulse_external_compare_evidence.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def digest(character: str) -> str:
    return character * 64


class EvidenceTests(unittest.TestCase):
    def evidence(self) -> dict:
        revision = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        tree = GATE._current_object("crates/sipi-tran")
        source = GATE._load(GATE.CONTRACT)["source"]
        return {
            "schema": GATE.SCHEMA,
            "status": "accepted",
            "profile_id": GATE.PROFILE_ID,
            "contract": {"schema": "sipi.tran.rc-pulse.acceptance.v1", "sha256": GATE._sha256_file(GATE.CONTRACT)},
            "external_report": {"schema": GATE.REPORT_SCHEMA, "sha256": digest("a"), "custody": "operator_external_only"},
            "source": {key: source[key] for key in ("canonical_origin", "commit", "tree", "path", "git_blob", "content_sha256", "redistribution")},
            "oracle": {"executable_sha256": digest("b"), "build_info_sha256": digest("c")},
            "product": {"source_commit": revision, "source_trees": {"sipi-tran": tree, "sipi-types": GATE._current_object("crates/sipi-types"), "sipi-runtime": GATE._current_object("crates/sipi-runtime")}, "cargo_lock_blob": GATE._current_object("Cargo.lock"), "executable_sha256": digest("e")},
            "replays": {
                "oracle_runs": 2,
                "oracle_samples": {"length": 4, "time_sha256_f64le": digest("1"), "voltage_in_sha256_f64le": digest("2"), "voltage_out_sha256_f64le": digest("3")},
                "product_samples": {"length": 4, "time_sha256_f64le": digest("4"), "voltage_in_sha256_f64le": digest("5"), "voltage_out_sha256_f64le": digest("6")},
            },
            "comparison": {
                "time_axis_seconds": {"absolute_tolerance": 1.0e-15, "relative_tolerance": 0.0, "max_absolute_error": 0.0, "max_relative_error": 0.0, "allowed_error_at_worst_index": 1.0e-15, "worst_index": 0},
                "voltage_in_volts": {"absolute_tolerance": 1.0e-9, "relative_tolerance": 1.0e-9, "max_absolute_error": 0.0, "max_relative_error": 0.0, "allowed_error_at_worst_index": 1.0e-9, "worst_index": 0},
                "voltage_out_volts": {"absolute_tolerance": 2.0e-6, "relative_tolerance": 5.0e-4, "max_absolute_error": 0.0, "max_relative_error": 0.0, "allowed_error_at_worst_index": 2.0e-6, "worst_index": 0},
            },
            "non_claims": ["hash-only external evidence"],
        }

    def test_synthetic_evidence_binds_to_current_product_source(self) -> None:
        self.assertTrue(GATE.verify_document(self.evidence())["valid"])

    def test_rejects_contract_source_product_and_report_drift(self) -> None:
        cases = [
            ("contract", lambda value: value["contract"].update({"sha256": digest("f")})),
            ("source", lambda value: value["source"].update({"commit": "0" * 40})),
            ("product_tree", lambda value: value["product"]["source_trees"].update({"sipi-tran": "0" * 40})),
            ("one_replay", lambda value: value["replays"].update({"oracle_runs": 1})),
            ("missing_metric", lambda value: value["comparison"].pop("voltage_out_volts")),
            ("widened_tolerance", lambda value: value["comparison"]["voltage_out_volts"].update({"relative_tolerance": 1.0})),
            ("error_over_bound", lambda value: value["comparison"]["voltage_out_volts"].update({"max_absolute_error": 3.0e-6})),
            ("bad_custody", lambda value: value["external_report"].update({"custody": "tracked"})),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                value = self.evidence()
                mutate(value)
                with self.assertRaises(GATE.EvidenceError):
                    GATE.verify_document(value)

    def test_optional_report_requires_hash_and_full_binding(self) -> None:
        evidence = self.evidence()
        report = {
            "schema": GATE.REPORT_SCHEMA,
            "profile_id": GATE.PROFILE_ID,
            "status": "passed",
            "accepted": True,
            "contract_sha256": evidence["contract"]["sha256"],
            "source": evidence["source"],
            "environment": {"platform": "windows-x86_64"},
            "oracle": {"sha256": evidence["oracle"]["executable_sha256"], "build_info": {"test": "build"}, "runs": {"first": evidence["replays"]["oracle_samples"], "second": evidence["replays"]["oracle_samples"]}},
            "product": {"sha256": evidence["product"]["executable_sha256"], "source_commit": evidence["product"]["source_commit"], "samples": evidence["replays"]["product_samples"]},
            "comparisons": [
                {"observable": name, "passed": True, **metrics}
                for name, metrics in evidence["comparison"].items()
            ],
            "non_claims": ["test"],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            evidence["oracle"]["build_info_sha256"] = GATE._canonical_json_sha256(report["oracle"]["build_info"])
            evidence["external_report"]["sha256"] = GATE._sha256_file(path)
            self.assertTrue(GATE.verify_document(evidence, path)["report_bound"])
            report["product"]["source_commit"] = "0" * 40
            path.write_text(json.dumps(report), encoding="utf-8")
            evidence["external_report"]["sha256"] = GATE._sha256_file(path)
            with self.assertRaises(GATE.EvidenceError):
                GATE.verify_document(evidence, path)

    def test_report_binding_rejects_oracle_and_metric_tampering(self) -> None:
        evidence = self.evidence()
        report = {
            "schema": GATE.REPORT_SCHEMA,
            "profile_id": GATE.PROFILE_ID,
            "status": "passed",
            "accepted": True,
            "contract_sha256": evidence["contract"]["sha256"],
            "source": evidence["source"],
            "environment": {"platform": "windows-x86_64"},
            "oracle": {"sha256": evidence["oracle"]["executable_sha256"], "build_info": {"test": "build"}, "runs": {"first": evidence["replays"]["oracle_samples"], "second": evidence["replays"]["oracle_samples"]}},
            "product": {"sha256": evidence["product"]["executable_sha256"], "source_commit": evidence["product"]["source_commit"], "samples": evidence["replays"]["product_samples"]},
            "comparisons": [{"observable": name, "passed": True, **metrics} for name, metrics in evidence["comparison"].items()],
            "non_claims": ["test"],
        }
        evidence["oracle"]["build_info_sha256"] = GATE._canonical_json_sha256(report["oracle"]["build_info"])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.json"
            for label, mutate in (
                ("oracle", lambda: report["oracle"].update({"sha256": digest("0")})),
                ("metrics", lambda: report["comparisons"][2].update({"max_absolute_error": 1.0})),
            ):
                with self.subTest(label=label):
                    candidate = copy.deepcopy(report)
                    if label == "oracle":
                        candidate["oracle"]["sha256"] = digest("0")
                    else:
                        candidate["comparisons"][2]["max_absolute_error"] = 1.0
                    path.write_text(json.dumps(candidate), encoding="utf-8")
                    evidence["external_report"]["sha256"] = GATE._sha256_file(path)
                    with self.assertRaises(GATE.EvidenceError):
                        GATE.verify_document(evidence, path)


if __name__ == "__main__":
    unittest.main()
