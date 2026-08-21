from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_p4a_03d_exact_asset_structural_consumer as GATE


class ExactAssetStructuralConsumerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = GATE.load_yaml(GATE.EVIDENCE)

    def test_static_evidence_is_valid(self) -> None:
        self.assertEqual(GATE.verify_document(self.document), {"valid": True, "dynamic_checked": False})

    def test_mutated_count_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["consumer_observation"]["declaration_count"] = 68
        with self.assertRaises(GATE.StructuralConsumerError):
            GATE.verify_document(document)

    def test_mutated_asset_hash_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["asset"]["sha256"] = "0" * 64
        with self.assertRaises(GATE.StructuralConsumerError):
            GATE.verify_document(document)

    def test_mutated_source_tree_or_blob_is_rejected(self) -> None:
        for field in ("tree", "parser_blob", "consumer_blob"):
            with self.subTest(field=field):
                document = copy.deepcopy(self.document)
                document["source_contract"][field] = "0" * 40
                with self.assertRaises(GATE.StructuralConsumerError):
                    GATE.verify_document(document)

    def test_dynamic_mode_rejects_partial_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GATE.StructuralConsumerError):
                GATE.validate(Path(temporary))

    def test_dynamic_inputs_are_hash_bound(self) -> None:
        source = ROOT / "fixtures" / "ibis" / "as4c512m16md4v-053bin.ibs"
        output = Path(__file__).with_name("_p4a_runner_output.tmp")
        try:
            output.write_text(json.dumps({"declaration_count": 67, "model_names": [], "model_types": {"IO": 40, "Input": 27}, "policy": self.document["consumer_observation"]["policy"]}), encoding="utf-8")
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                shutil.copyfile(source, root / self.document["asset"]["relative_path"])
                with self.assertRaises(GATE.StructuralConsumerError):
                    GATE.verify_external_inputs(self.document, root, output)
        finally:
            output.unlink(missing_ok=True)

    def test_missing_runner_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(ROOT / "fixtures" / "ibis" / "as4c512m16md4v-053bin.ibs", root / self.document["asset"]["relative_path"])
            with self.assertRaises(GATE.StructuralConsumerError):
                GATE.verify_external_inputs(self.document, root, root / "missing.json")

    def test_asset_path_escape_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["asset"]["relative_path"] = "../as4c512m16md4v-053bin.ibs"
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GATE.StructuralConsumerError):
                GATE.verify_external_inputs(document, Path(temporary), Path(temporary) / "missing.json")


if __name__ == "__main__":
    unittest.main()
