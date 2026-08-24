import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_pb_02_metallic_python_oracle_formal as formal
import aggregate_pb_02_metallic_python_oracle as aggregator


ROOT = Path(__file__).resolve().parents[1]


class VerifyPb02MetallicFormalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = yaml.safe_load(formal.MANIFEST.read_text(encoding="utf-8"))

    def assert_invalid(self, document):
        result = formal.verify(copy.deepcopy(document))
        self.assertFalse(result["valid"], result)

    def coordinated_mutation_is_rejected(self, mutate):
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            report_bindings = self.document["evidence"]["reports"]
            aggregate_binding = self.document["evidence"]["aggregate"]
            paths = {formal.CORPUS, formal.FIXTURE, self.document["audit"]["path"], aggregate_binding["path"], *(formal.HARNESS_PATHS.values()), *(binding["path"] for binding in report_bindings)}
            for relative in paths:
                target = temp_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            document = copy.deepcopy(self.document)
            for binding in document["evidence"]["reports"]:
                path = temp_root / binding["path"]
                report = json.loads(path.read_text(encoding="utf-8"))
                mutate(report)
                path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
                binding["sha256"] = formal.sha256(path)
            previous_root = aggregator.ROOT
            try:
                aggregator.ROOT = temp_root
                output = temp_root / aggregate_binding["path"]
                aggregator.aggregate([temp_root / binding["path"] for binding in document["evidence"]["reports"]], output)
            finally:
                aggregator.ROOT = previous_root
            document["evidence"]["aggregate"]["sha256"] = formal.sha256(output)
            self.assertFalse(formal.verify(document, temp_root)["valid"])

    def test_baseline_formal_evidence_is_valid(self):
        result = formal.verify(copy.deepcopy(self.document))
        self.assertTrue(result["valid"], result)

    def test_promotion_claim_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["claims"]["promotion"] = True
        self.assert_invalid(document)

    def test_selfcompare_run_binding_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["evidence"]["reports"][1]["run_id"] = document["evidence"]["reports"][0]["run_id"]
        self.assert_invalid(document)

    def test_empty_harness_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["harness"] = {}
        self.assert_invalid(document)

    def test_manifest_nested_extra_keys_are_rejected(self):
        for container, key in (("source", "unexpected"), ("harness", "unexpected"), ("evidence", "unexpected"), ("audit", "unexpected")):
            document = copy.deepcopy(self.document)
            document[container][key] = True
            self.assert_invalid(document)
        document = copy.deepcopy(self.document)
        document["evidence"]["reports"][0]["unexpected"] = True
        self.assert_invalid(document)
        document = copy.deepcopy(self.document)
        document["evidence"]["aggregate"]["unexpected"] = True
        self.assert_invalid(document)

    def test_stale_aggregate_binding_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["evidence"]["aggregate"]["sha256"] = "0" * 64
        self.assert_invalid(document)

    def test_audit_alias_and_hash_mutations_are_rejected(self):
        document = copy.deepcopy(self.document)
        document["audit"]["path"] = document["evidence"]["aggregate"]["path"]
        self.assert_invalid(document)
        document = copy.deepcopy(self.document)
        document["audit"]["sha256"] = "0" * 64
        self.assert_invalid(document)

    def test_report_summary_toolchain_and_pe_mutations_are_rejected(self):
        report_path = ROOT / self.document["evidence"]["reports"][0]["path"]
        original = json.loads(report_path.read_text(encoding="utf-8"))
        for mutate in (
            lambda report: report["cases"][0]["payload"]["fields"][0].__setitem__("max_abs", float("nan")),
            lambda report: report["toolchain"]["child_python"]["identity"]["python"].__setitem__("file_sha256", "0" * 64),
            lambda report: report["build"]["binary_custody"].__setitem__("canonical_sha256", "0" * 64),
            lambda report: report["cases"][0]["oracle"].__setitem__("source_command", "sim-rust"),
            lambda report: report.__setitem__("unexpected", True),
            lambda report: report["cases"][0]["payload"]["fields"][0]["candidate"].update({"shape": [2], "count": 1}),
            lambda report: report["build"]["binary_custody"].__setitem__("bytes", 0),
        ):
            report = copy.deepcopy(original)
            mutate(report)
            with tempfile.TemporaryDirectory() as directory:
                temp_root = Path(directory)
                for relative in (self.document["evidence"]["reports"][0]["path"], self.document["evidence"]["reports"][1]["path"], self.document["evidence"]["aggregate"]["path"], self.document["audit"]["path"], formal.CORPUS, formal.FIXTURE, *formal.HARNESS_PATHS.values()):
                    target = temp_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((ROOT / relative).read_bytes())
                target_report = temp_root / self.document["evidence"]["reports"][0]["path"]
                target_report.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
                mutated = copy.deepcopy(self.document)
                mutated["evidence"]["reports"][0]["sha256"] = formal.sha256(target_report)
                self.assertFalse(formal.verify(mutated, temp_root)["valid"])

    def test_coordinated_rehash_and_regenerate_rejects_semantic_mutations(self):
        mutations = (
            lambda report: report["cases"][0]["payload"]["fields"][0]["candidate"].__setitem__("shape", [999]),
            lambda report: report["cases"][0]["payload"]["fields"][0].__setitem__("max_abs", -1.0),
            lambda report: report["cases"][0]["payload"]["fields"][0].update({"max_abs": 1.0, "tolerance": 0.5, "passed": True}),
            lambda report: report["build"]["binary_custody"].__setitem__("bytes", formal.PE_BYTES - 1),
            lambda report: report["build"]["binary_custody"]["normalization"]["ranges"][1].__setitem__("offset", 240),
        )
        for mutate in mutations:
            self.coordinated_mutation_is_rejected(mutate)


if __name__ == "__main__":
    unittest.main()
