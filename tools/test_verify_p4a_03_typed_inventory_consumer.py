from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p4a_typed_inventory_consumer",
    ROOT / "tools" / "verify_p4a_03_typed_inventory_consumer.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class TypedInventoryConsumerTests(unittest.TestCase):
    def test_current_manifest_and_selected_asset_are_valid(self) -> None:
        result = GATE.validate(ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["selected_asset_model_count"], 67)
        self.assertEqual(result["selected_asset_selector_count"], 4)

    def test_selected_asset_gap_is_observed_not_synthesized(self) -> None:
        observed = GATE.observe_asset(GATE.ASSET.read_bytes())
        self.assertEqual(
            observed["selector_branch_unknown"]["DQ_PIN"],
            "DQ_60OHM_60OHM_PREEMP_ON",
        )

    def test_source_hash_mutation_fails_closed(self) -> None:
        manifest = GATE.load_yaml(GATE.MANIFEST)
        manifest["source"]["implementation_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs" / "baselines").mkdir(parents=True)
            (root / "docs" / "baselines" / "audits").mkdir(parents=True)
            (root / "crates" / "sipi-ibis" / "src").mkdir(parents=True)
            (root / "fixtures" / "ibis").mkdir(parents=True)
            (root / "docs" / "baselines" / GATE.MANIFEST.name).write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
            )
            (root / GATE.IMPLEMENTATION.relative_to(GATE.ROOT)).write_bytes(
                GATE.IMPLEMENTATION.read_bytes()
            )
            (root / GATE.AUDIT.relative_to(GATE.ROOT)).write_bytes(GATE.AUDIT.read_bytes())
            (root / GATE.ASSET.relative_to(GATE.ROOT)).write_bytes(GATE.ASSET.read_bytes())
            with self.assertRaisesRegex(GATE.TypedInventoryError, "implementation_hash_drift"):
                GATE.validate(root)

    def test_audit_path_or_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["audit"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs" / "baselines").mkdir(parents=True)
            (root / "docs" / "baselines" / "audits").mkdir(parents=True)
            (root / "crates" / "sipi-ibis" / "src").mkdir(parents=True)
            (root / "fixtures" / "ibis").mkdir(parents=True)
            (root / "docs" / "baselines" / GATE.MANIFEST.name).write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
            )
            (root / GATE.AUDIT.relative_to(GATE.ROOT)).write_bytes(GATE.AUDIT.read_bytes())
            (root / GATE.IMPLEMENTATION.relative_to(GATE.ROOT)).write_bytes(
                GATE.IMPLEMENTATION.read_bytes()
            )
            (root / GATE.ASSET.relative_to(GATE.ROOT)).write_bytes(GATE.ASSET.read_bytes())
            with self.assertRaisesRegex(GATE.TypedInventoryError, "audit_hash_drift"):
                GATE.validate(root)

    def test_non_claim_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["admission"]["electrical_behavior"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.yaml"
            path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
            original = GATE.MANIFEST
            try:
                GATE.MANIFEST = path
                with self.assertRaisesRegex(GATE.TypedInventoryError, "non_claim_boundary_drift"):
                    GATE.validate(ROOT)
            finally:
                GATE.MANIFEST = original


if __name__ == "__main__":
    unittest.main()
