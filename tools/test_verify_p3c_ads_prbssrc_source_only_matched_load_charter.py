"""Mutation checks for the blocked ADS source-only charter."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_only_gate", ROOT / "tools/verify_p3c_ads_prbssrc_source_only_matched_load_charter.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def document() -> dict[str, object]:
    return yaml.safe_load((ROOT / "docs/baselines/p3c-ads-prbssrc-source-only-matched-load-charter.v1.yaml").read_text(encoding="utf-8"))


def rejected(mutator) -> None:
    value = copy.deepcopy(document())
    mutator(value)
    try:
        GATE.verify_document(value)
    except GATE.VerificationError:
        return
    raise AssertionError("mutation accepted")


def main() -> int:
    assert GATE.verify_document(document())["owner_confirmation_pending"] is True
    rejected(lambda value: value["topology"]["loads"]["tx_plus_match"].__setitem__("resistance_ohms", 100.0))
    rejected(lambda value: value["topology"].__setitem__("observation", "V(rxp)-V(rxm)"))
    rejected(lambda value: value["fixed_diagnostic_mapping"].__setitem__("gain_fit", "allowed"))
    rejected(lambda value: value["owner_confirmation"].__setitem__("external_ads_runner_authorized", True))
    rejected(lambda value: value["admission"].__setitem__("product_source_policy_changed", True))
    print("p3c_ads_prbssrc_source_only_matched_load_charter_mutation_tests_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
