"""Mutation gate tests for the AS-03 current immutable observation."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_as_03_numeric_bound_current_6b8dacb4 as verifier


class CurrentAs03GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = yaml.safe_load(verifier.MANIFEST.read_text(encoding="utf-8"))

    def blocked(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        self.assertFalse(verifier.verify(verifier.MANIFEST, document=document)["valid"])

    def test_baseline(self) -> None:
        self.assertTrue(verifier.verify()["valid"])

    def test_candidate_anchor_drift(self) -> None:
        self.blocked(lambda doc: doc["source"]["candidate"].__setitem__("commit", "0" * 40))

    def test_runner_anchor_drift(self) -> None:
        self.blocked(lambda doc: doc["harness"]["runner"].__setitem__("sha256", "0" * 64))

    def test_source_map_path_and_sha_drift(self) -> None:
        self.blocked(lambda doc: doc["provenance"]["source_map"].update(path="docs/escape.yaml", sha256="0" * 64))

    def test_report_hash_run_id_nonce_drift(self) -> None:
        self.blocked(lambda doc: doc["reports"][0].update(sha256="0" * 64, run_id="wrong", fresh_run_nonce="0" * 64))

    def test_aggregate_anchor_drift(self) -> None:
        self.blocked(lambda doc: doc["aggregate"].__setitem__("sha256", "0" * 64))

    def test_audit_stale_hash(self) -> None:
        self.blocked(lambda doc: doc["audit"].__setitem__("sha256", "0" * 64))

    def test_global_promotion_is_rejected(self) -> None:
        self.blocked(lambda doc: doc.__setitem__("parity_claim", True))

    def test_manifest_extra_key_is_rejected(self) -> None:
        self.blocked(lambda doc: doc.__setitem__("release", True))

    def test_report_metric_forge_is_rejected(self) -> None:
        report_path = verifier.ROOT / self.document["reports"][0]["path"]
        original = report_path.read_bytes()
        report = json.loads(original)
        report["metrics"]["candidate_y_rms_siemens"] = 99.0
        try:
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertFalse(verifier.verify()["valid"])
        finally:
            report_path.write_bytes(original)

    def test_report_tool_identity_forge_is_rejected(self) -> None:
        report_path = verifier.ROOT / self.document["reports"][0]["path"]
        original = report_path.read_bytes()
        report = json.loads(original)
        report["toolchain"]["cargo"]["pre_post_equal"] = False
        try:
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertFalse(verifier.verify()["valid"])
        finally:
            report_path.write_bytes(original)

    def test_aggregate_forge_is_rejected(self) -> None:
        aggregate_path = verifier.ROOT / self.document["aggregate"]["path"]
        original = aggregate_path.read_bytes()
        aggregate = json.loads(original)
        aggregate["custody_valid"] = False
        try:
            aggregate_path.write_text(json.dumps(aggregate), encoding="utf-8")
            self.assertFalse(verifier.verify()["valid"])
        finally:
            aggregate_path.write_bytes(original)

    def test_nonfinite_report_metric_is_rejected(self) -> None:
        report_path = verifier.ROOT / self.document["reports"][1]["path"]
        original = report_path.read_bytes()
        report = json.loads(original)
        report["metrics"]["candidate_y_mean_rms_siemens"] = float("nan")
        try:
            report_path.write_text(json.dumps(report), encoding="utf-8")
            self.assertFalse(verifier.verify()["valid"])
        finally:
            report_path.write_bytes(original)

    def test_legacy_v2_evidence_mutation_is_rejected(self) -> None:
        self.blocked(lambda doc: doc["legacy_v2_evidence"]["metrics"].__setitem__("candidate_y_rms_siemens", 0.0))

    def test_aggregate_parity_promotion_is_rejected(self) -> None:
        aggregate_path = verifier.ROOT / self.document["aggregate"]["path"]
        original = aggregate_path.read_bytes()
        aggregate = json.loads(original)
        aggregate["parity_claim"] = True
        try:
            aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.assertFalse(verifier.verify()["valid"])
        finally:
            aggregate_path.write_bytes(original)

    def test_malformed_manifest_is_blocked_without_raise(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
            handle.write("schema: [broken\n")
            path = Path(handle.name)
        try:
            result = verifier.verify(path)
            self.assertFalse(result["valid"])
            self.assertIn("manifest malformed", result["blockers"])
        finally:
            path.unlink(missing_ok=True)

    def test_malformed_report_is_blocked_without_raise(self) -> None:
        report_path = verifier.ROOT / self.document["reports"][0]["path"]
        original = report_path.read_bytes()
        try:
            report_path.write_bytes(b"{not-json")
            self.assertFalse(verifier.verify()["valid"])
        finally:
            report_path.write_bytes(original)

    def test_malformed_aggregate_is_blocked_without_raise(self) -> None:
        aggregate_path = verifier.ROOT / self.document["aggregate"]["path"]
        original = aggregate_path.read_bytes()
        try:
            aggregate_path.write_bytes(b"{not-json")
            self.assertFalse(verifier.verify()["valid"])
        finally:
            aggregate_path.write_bytes(original)

    def test_audit_legacy_anchor_mutation_is_rejected(self) -> None:
        audit_path = verifier.ROOT / self.document["audit"]["path"]
        original = audit_path.read_bytes()
        try:
            audit_path.write_bytes(original.replace(b"same fixture bytes and AS-03 args", b"different fixture bytes and args"))
            self.assertFalse(verifier.verify()["valid"])
        finally:
            audit_path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
