"""Mutation checks for the ADS source-only v2 evidence gate."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_only_v2_evidence", ROOT / "tools/verify_p3c_ads_prbssrc_source_only_v2_observation_evidence.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def document() -> dict[str, object]:
    return yaml.safe_load((ROOT / "docs/baselines/p3c-ads-prbssrc-source-only-v2-observation-evidence.v1.yaml").read_text(encoding="utf-8"))


def rejected(mutator) -> None:
    value = copy.deepcopy(document())
    mutator(value)
    try:
        GATE.verify_document(value)
    except GATE.VerificationError:
        return
    raise AssertionError("mutation accepted")


def main() -> int:
    assert GATE.verify_document(document())["strict_bitwise_identity"] is False
    rejected(lambda value: value["strict_numeric_result"].__setitem__("exact_bitwise_identity_observed", True))
    rejected(lambda value: value["admission"].__setitem__("product_projection_v2_source_strobe_match_observed", True))
    rejected(lambda value: value["external_observation"].__setitem__("report_content_sha256", "0" * 64))
    print("p3c_ads_prbssrc_source_only_v2_observation_evidence_mutation_tests_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
