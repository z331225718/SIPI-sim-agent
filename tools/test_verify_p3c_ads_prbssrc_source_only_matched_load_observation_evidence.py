"""Mutation checks for ADS source-only observation evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_only_evidence", ROOT / "tools/verify_p3c_ads_prbssrc_source_only_matched_load_observation_evidence.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def document() -> dict[str, object]:
    return yaml.safe_load((ROOT / "docs/baselines/p3c-ads-prbssrc-source-only-matched-load-observation-evidence.v1.yaml").read_text(encoding="utf-8"))


def rejected(mutator) -> None:
    value = copy.deepcopy(document())
    mutator(value)
    try:
        GATE.verify_document(value)
    except GATE.VerificationError:
        return
    raise AssertionError("mutation accepted")


def main() -> int:
    assert GATE.verify_document(document())["source_only_observed"] is True
    rejected(lambda value: value["external_observation"].__setitem__("canonical_payload_sha256", "0" * 64))
    rejected(lambda value: value["external_observation"]["third_period_ui_interior"].__setitem__("nrmse_bits", "3ff0000000000000"))
    rejected(lambda value: value["admission"].__setitem__("product_source_policy_changed", True))
    rejected(lambda value: value["admission"].__setitem__("source_explains_full_channel_residual", True))
    rejected(lambda value: value["external_observation"].__setitem__("report_path", "C:\\external\\report.json"))
    print("p3c_ads_prbssrc_source_only_observation_evidence_mutation_tests_passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
