"""Mutation checks for selected truncation sensitivity evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/verify_p3c_selected_truncation_waveform_sensitivity_observation_evidence.py"
SPEC = importlib.util.spec_from_file_location("verify_truncation_sensitivity", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load() -> dict[str, object]:
    return yaml.safe_load((ROOT / "docs/baselines/p3c-selected-truncation-waveform-sensitivity-observation-evidence.v1.yaml").read_text(encoding="utf-8"))


def rejected(mutator) -> None:
    document = copy.deepcopy(load())
    mutator(document)
    try:
        MODULE.verify_document(document)
    except MODULE.VerificationError:
        return
    raise AssertionError("mutation accepted")


def main() -> int:
    assert MODULE.verify_document(load())["valid"] is True
    rejected(lambda value: value.__setitem__("status", "accepted"))
    rejected(lambda value: value["external_observation"].__setitem__("report_content_sha256", "0" * 64))
    rejected(lambda value: value["external_observation"].__setitem__("causality_iterations", 31))
    rejected(lambda value: value["external_observation"]["full_bounded_causality_diagnostic"].__setitem__("waveform_nrmse_bits", "3f9c4139b95fcc93"))
    rejected(lambda value: value["admission"].__setitem__("full_branch_candidate_or_accepted", True))
    rejected(lambda value: value["external_observation"].__setitem__("report_path", "C:\\private\\report.json"))
    print("selected_truncation_waveform_sensitivity_observation_mutation_tests_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
