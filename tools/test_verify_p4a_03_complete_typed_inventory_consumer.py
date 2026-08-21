from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p4a_03_typed_inventory",
    ROOT / "tools/verify_p4a_03_complete_typed_inventory_consumer.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def stage(manifest: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp())
    for source in (GATE.PREDECESSOR, GATE.IMPLEMENTATION, GATE.RUNNER, GATE.ASSET, GATE.DISPOSITION, GATE.EVIDENCE, GATE.AUDIT):
        target = root / source.relative_to(GATE.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = root / GATE.MANIFEST.relative_to(GATE.ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(manifest or GATE.load_yaml(GATE.MANIFEST), sort_keys=False),
        encoding="utf-8",
    )
    return root


class TypedInventoryConsumerTests(unittest.TestCase):
    def test_current_external_declaration_linkage_scope_is_closed(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual((result["model_count"], result["selector_count"], result["pin_count"]), (95, 4, 200))

    def test_complete_document_observation_fails_without_final_end(self) -> None:
        data = GATE.OFFICIAL_SOURCE.read_bytes().rsplit(b"[End]", 1)[0]
        with tempfile.NamedTemporaryFile(delete=False) as temporary:
            temporary.write(data)
            path = Path(temporary.name)
        with self.assertRaisesRegex(GATE.TypedInventoryError, "official_complete_document_boundary_drift"):
            GATE.validate(official_source=path)

    def test_implementation_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["source"]["implementation_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.TypedInventoryError, "implementation_hash_drift"):
            GATE.validate(stage(manifest))

    def test_audit_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["audit"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.TypedInventoryError, "audit_hash_drift"):
            GATE.validate(stage(manifest))

    def test_electrical_claim_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["admission"]["electrical_behavior"] = True
        with self.assertRaisesRegex(GATE.TypedInventoryError, "non_claim_boundary_drift"):
            GATE.validate(stage(manifest))


if __name__ == "__main__":
    unittest.main()
