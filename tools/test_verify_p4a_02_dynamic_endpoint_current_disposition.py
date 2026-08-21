from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p4a_02_current", ROOT / "tools/verify_p4a_02_dynamic_endpoint_current_disposition.py")
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


class DynamicEndpointCurrentDispositionTests(unittest.TestCase):
    def test_current_additive_e3a_disposition_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertFalse(result["dynamic_endpoint_admission"])
        self.assertEqual(result["retained_blocker_count"], 11)

    def test_predecessor_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["predecessors"]["static_scope_split"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.CurrentDispositionError, "predecessor_drift"):
            GATE.validate(stage(manifest))

    def test_dynamic_implementation_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["current_disposition"]["dynamic_endpoint_implementation"] = True
        with self.assertRaisesRegex(GATE.CurrentDispositionError, "dynamic_admission_drift"):
            GATE.validate(stage(manifest))

    def test_removed_blocker_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["dynamic_blocker"]["missing_fields"].pop()
        with self.assertRaisesRegex(GATE.CurrentDispositionError, "retained_blocker_drift"):
            GATE.validate(stage(manifest))

    def test_non_additive_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["additive"] = False
        with self.assertRaisesRegex(GATE.CurrentDispositionError, "additive_promotion_boundary_drift"):
            GATE.validate(stage(manifest))


if __name__ == "__main__":
    unittest.main()
