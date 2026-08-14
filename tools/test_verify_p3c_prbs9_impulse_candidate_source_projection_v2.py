"""Mutation checks for the blocked PRBS9 source projection v2 charter."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_projection_v2", ROOT / "tools/verify_p3c_prbs9_impulse_candidate_source_projection_v2.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def document() -> dict[str, object]:
    return yaml.safe_load((ROOT / "docs/baselines/p3c-prbs9-impulse-candidate-source-projection.v2.yaml").read_text(encoding="utf-8"))


def rejected(mutator) -> None:
    value = copy.deepcopy(document())
    mutator(value)
    try:
        GATE.verify_document(value)
    except GATE.VerificationError:
        return
    raise AssertionError("mutation accepted")


def main() -> int:
    assert GATE.verify_document(document())["owner_confirmation_pending"] is False
    rejected(lambda value: value["policy_candidate"]["ui_boundary_for_global_ui_greater_than_zero"].__setitem__("phase_0", "current_symbol_level"))
    rejected(lambda value: value["policy_candidate"].__setitem__("source_amplitude_volts_differential", [-0.5, 0.5]))
    rejected(lambda value: value["owner_confirmation"].__setitem__("phase_0_prior_phase_1_current", False))
    rejected(lambda value: value["admission"].__setitem__("selected_source_projection_v2_implemented", False))
    print("p3c_prbs9_impulse_candidate_source_projection_v2_mutation_tests_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
