import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_pb_01_03_branch_inventory as verifier


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_REL = verifier.INVENTORY.relative_to(ROOT)


class Pb0103InventoryVerifierTests(unittest.TestCase):
    def _fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        paths = [root / INVENTORY_REL, root / verifier.AGGREGATE, root / verifier.AUDIT]
        paths.extend(root / report for report in verifier.REPORTS)
        paths.append(root / verifier.AGGREGATOR)
        for source in (verifier.INVENTORY, ROOT / verifier.AGGREGATE, ROOT / verifier.AUDIT, ROOT / verifier.AGGREGATOR, ROOT / "tools/verify_pb_01_03_branch_inventory.py", ROOT / "tools/test_verify_pb_01_03_branch_inventory.py"):
            target = root / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        for report in verifier.REPORTS:
            target = root / report
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / report).read_bytes())
        document = yaml.safe_load((root / INVENTORY_REL).read_text(encoding="utf-8"))
        document["audit"]["sha256"] = verifier._sha(root / verifier.AUDIT)
        for index, report in enumerate(verifier.REPORTS, start=1):
            document["audit"]["exact_file_bindings"][f"report_{index:02d}"]["sha256"] = verifier._sha(root / report)
        document["audit"]["exact_file_bindings"]["aggregate"]["sha256"] = verifier._sha(root / verifier.AGGREGATE)
        document["audit"]["exact_file_bindings"]["aggregator"]["sha256"] = verifier._sha(root / verifier.AGGREGATOR)
        (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        # The inventory itself is not part of the hash graph, so this fixture
        # intentionally validates the actual copied payloads only.
        return temporary, root, document

    def test_current_inventory_is_valid(self):
        result = verifier.verify_inventory()
        self.assertEqual(result["status"], "passed", result)

    def test_report_hash_mutation_is_rejected(self):
        temporary, root, document = self._fixture()
        try:
            document["audit"]["exact_file_bindings"]["report_01"]["sha256"] = "0" * 64
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertIn("report_1 file binding drift", result["blockers"])
        finally:
            temporary.cleanup()

    def test_aggregate_binding_mutation_is_rejected(self):
        temporary, root, document = self._fixture()
        try:
            aggregate = json.loads((root / verifier.AGGREGATE).read_text(encoding="utf-8"))
            aggregate["reports"][0]["sha256"] = "0" * 64
            (root / verifier.AGGREGATE).write_text(json.dumps(aggregate), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertIn("aggregate file binding drift", result["blockers"])
        finally:
            temporary.cleanup()

    def test_absolute_path_mutation_is_rejected(self):
        temporary, root, document = self._fixture()
        try:
            document["audit"]["path"] = "C:/outside/audit.md"
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertTrue(any("unsafe path" in item for item in result["blockers"]))
        finally:
            temporary.cleanup()

    def test_promotion_and_external_claim_mutations_are_rejected(self):
        temporary, root, document = self._fixture()
        try:
            document["claims"]["promotion"] = True
            document["claims"]["external_asset_parity"] = True
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertIn("claims exact structure drift", result["blockers"])
        finally:
            temporary.cleanup()

    def test_row_case_and_policy_promotions_are_rejected(self):
        temporary, root, document = self._fixture()
        try:
            document["rows"][1]["status"] = "passed"
            document["cases"][0]["status"] = "python_numeric_parity"
            document["replay_policy"]["pb01"]["fresh_runs_required"] = 1
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertGreaterEqual(sum("exact structure drift" in item for item in result["blockers"]), 3)
        finally:
            temporary.cleanup()

    def test_upstream_source_and_nonclaims_mutations_are_rejected(self):
        temporary, root, document = self._fixture()
        try:
            document["upstream"]["source_mode"] = "working_tree"
            document["source_scope"]["upstream_source_blob_oid"]["src/pybert/cli.py"] = "0" * 40
            document["non_claims"] = []
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertGreaterEqual(sum("exact structure drift" in item for item in result["blockers"]), 3)
        finally:
            temporary.cleanup()

    def test_report_comparison_mutation_is_rejected_even_when_binding_is_rewritten(self):
        temporary, root, document = self._fixture()
        try:
            report_path = root / verifier.REPORTS[0]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["replay"]["comparison"]["arrays"][0]["passed"] = False
            report_path.write_text(json.dumps(report), encoding="utf-8")
            document["audit"]["exact_file_bindings"]["report_01"]["sha256"] = verifier._sha(report_path)
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertIn("report_1 content SHA drift", result["blockers"])
        finally:
            temporary.cleanup()

    def test_audit_source_map_mutation_is_rejected(self):
        temporary, root, document = self._fixture()
        try:
            document["audit"]["source_map"] = "release_accepted"
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertIn("audit exact values drift", result["blockers"])
        finally:
            temporary.cleanup()

    def test_audit_promotion_extra_key_is_rejected(self):
        temporary, root, document = self._fixture()
        try:
            document["audit"]["promotion"] = True
            (root / INVENTORY_REL).write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            result = verifier.verify_inventory(root, root / INVENTORY_REL)
            self.assertIn("audit exact schema drift", result["blockers"])
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
