from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "current_dft",
    ROOT / "tools/verify_p3c_selected_highloss_residual_dft_v2_current_head_observation_evidence.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Tests(unittest.TestCase):
    def test_valid_and_mutations(self) -> None:
        document = yaml.safe_load(
            (
                ROOT
                / "docs/baselines/p3c-selected-highloss-residual-dft-v2-current-head-observation-evidence.v1.yaml"
            ).read_text(encoding="utf-8")
        )
        # The record commit may be newer than the replay candidate, but every
        # product source in the bound execution inventory must remain exact.
        self.assertTrue(MODULE.verify(document, current=True)["valid"])
        for path, value in (
            (["external_observation", "clean_archive_commit"], "0" * 40),
            (["external_observation", "fixed_dft", "window"], "hann"),
            (["external_observation", "source_sha256"], "0" * 64),
            (["external_observation", "bands", 0, "residual_energy_bits"], "0" * 16),
            (["authority", "decision_ref"], "other-policy"),
            (["blockers", 0], "removed"),
            (["admission", "acceptance_ready"], True),
        ):
            changed = copy.deepcopy(document)
            cursor = changed
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.assertRaises(MODULE.VerificationError):
                MODULE.verify(changed)


if __name__ == "__main__":
    unittest.main()
