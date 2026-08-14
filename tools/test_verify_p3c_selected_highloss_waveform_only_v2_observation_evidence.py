"""Mutation checks for finite-edge v2 waveform-only evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v2_waveform_evidence", ROOT / "tools/verify_p3c_selected_highloss_waveform_only_v2_observation_evidence.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)

def document(): return yaml.safe_load((ROOT / "docs/baselines/p3c-selected-highloss-waveform-only-v2-observation-evidence.v1.yaml").read_text(encoding="utf-8"))
def rejected(mutator):
    value = copy.deepcopy(document()); mutator(value)
    try: GATE.verify_document(value)
    except GATE.VerificationError: return
    raise AssertionError("mutation accepted")

def main() -> int:
    assert GATE.verify_document(document())["accepted"] is False
    rejected(lambda value: value["admission"].__setitem__("selected_highloss_waveform_only_profile_accepted", True))
    rejected(lambda value: value["external_observation"].__setitem__("waveform_nrmse_bits", "3f847ae147ae147b"))
    print("p3c_selected_highloss_waveform_only_v2_observation_evidence_mutation_tests_passed")
    return 0
if __name__ == "__main__": raise SystemExit(main())
