from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p4a_02_scope_split",
    ROOT / "tools/verify_p4a_02_static_declaration_scope_and_dynamic_blocker.py",
)
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


class StaticScopeDynamicBlockerTests(unittest.TestCase):
    def test_current_split_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertFalse(result["dynamic_endpoint_admission"])
        self.assertEqual(result["missing_dynamic_fields"], 11)

    def test_predecessor_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["predecessors"]["dynamic_composition_contract"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.ScopeSplitError, "predecessor_hash_drift"):
            GATE.validate(stage(manifest))

    def test_missing_dynamic_field_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["dynamic_endpoint_blocker"]["missing_fields"].pop()
        with self.assertRaisesRegex(GATE.ScopeSplitError, "dynamic_blocker_field_drift"):
            GATE.validate(stage(manifest))

    def test_dynamic_admission_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["dynamic_endpoint_blocker"]["admission"] = True
        with self.assertRaisesRegex(GATE.ScopeSplitError, "dynamic_blocker_admission_drift"):
            GATE.validate(stage(manifest))

    def test_audit_hash_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["audit"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.ScopeSplitError, "audit_hash_drift"):
            GATE.validate(stage(manifest))


if __name__ == "__main__":
    unittest.main()
