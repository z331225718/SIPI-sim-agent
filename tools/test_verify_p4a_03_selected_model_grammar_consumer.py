from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p4a_03_selected_model_grammar",
    ROOT / "tools/verify_p4a_03_selected_model_grammar_consumer.py",
)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def stage(manifest: dict | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="p4a-03bk-gate-"))
    current = manifest or GATE.load_yaml(GATE.MANIFEST)
    paths = [GATE.MANIFEST, GATE.IMPLEMENTATION, GATE.RUNNER, GATE.SPEC, GATE.AUDIT, GATE.EVIDENCE]
    for source in paths:
        target = root / source.relative_to(GATE.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source == GATE.MANIFEST:
            target.write_text(yaml.safe_dump(current, sort_keys=False), encoding="utf-8")
        else:
            target.write_bytes(source.read_bytes())
    return root


class SelectedModelGrammarGateTests(unittest.TestCase):
    def test_current_gate_is_valid(self) -> None:
        result = GATE.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["external_selection_status"], "missing_required_selected_profile")

    def test_defaults_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["grammar"]["defaults"] = "typical"
        with self.assertRaisesRegex(GATE.SelectedModelGrammarError, "grammar_drift"):
            GATE.validate(stage(manifest))

    def test_transient_boundary_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["consumer"]["transient"] = True
        with self.assertRaisesRegex(GATE.SelectedModelGrammarError, "consumer_boundary_drift:transient"):
            GATE.validate(stage(manifest))

    def test_fake_external_profile_mutation_fails_closed(self) -> None:
        manifest = copy.deepcopy(GATE.load_yaml(GATE.MANIFEST))
        manifest["external_official_observation"]["selected_profile_status"] = "selected"
        with self.assertRaisesRegex(GATE.SelectedModelGrammarError, "manifest_external_profile_drift"):
            GATE.validate(stage(manifest))


if __name__ == "__main__":
    unittest.main()
