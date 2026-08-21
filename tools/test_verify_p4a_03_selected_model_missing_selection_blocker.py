from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_03_selection", ROOT / "tools/verify_p4a_03_selected_model_missing_selection_blocker.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def stage(manifest: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp())
    current = manifest or GATE.load_yaml(GATE.MANIFEST)
    sources = [GATE.AUDIT]
    sources.extend(GATE.ROOT / Path(spec["path"]) for spec in current["predecessors"].values())
    for source in sources:
        target = root / source.relative_to(GATE.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = root / GATE.MANIFEST.relative_to(GATE.ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")
    return root


class SelectedModelMissingSelectionTests(unittest.TestCase):
    def test_current_non_unique_selection_blocker_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual((result["model_count"], result["selector_branch_model_count"]), (95, 94))
        self.assertFalse(result["implementation_admitted"])

    def test_predecessor_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["predecessors"]["complete_typed_inventory"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.MissingSelectionError, "predecessor_drift"):
            GATE.validate(stage(manifest))

    def test_selector_cardinality_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["exact_external_inventory"]["selectors"]["DQ_PIN"] = 1
        with self.assertRaisesRegex(GATE.MissingSelectionError, "external_inventory_drift:selectors"):
            GATE.validate(stage(manifest))

    def test_fake_unique_model_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["mechanical_uniqueness"]["model_unique"] = True
        with self.assertRaisesRegex(GATE.MissingSelectionError, "mechanical_uniqueness_drift:model_unique"):
            GATE.validate(stage(manifest))

    def test_implementation_admission_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["disposition"]["selected_model_scoped_grammar_admitted"] = True
        with self.assertRaisesRegex(GATE.MissingSelectionError, "implementation_admission_drift"):
            GATE.validate(stage(manifest))


if __name__ == "__main__":
    unittest.main()
