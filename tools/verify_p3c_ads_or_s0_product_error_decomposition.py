"""Fail closed verification for P3C same-axis complex error decomposition evidence."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/baselines/p3c-ads-or-s0-product-error-decomposition-observation-evidence.v1.yaml"


class VerificationError(ValueError):
    pass


def fail(condition: bool, reason: str) -> None:
    if condition:
        raise VerificationError(reason)


def verify(document: object) -> dict[str, object]:
    fail(not isinstance(document, dict), "shape")
    required = {"schema", "status", "authority", "predecessor", "external_observation", "independent_audit", "admission", "blockers", "non_claims"}
    fail(set(document) != required, "shape")
    fail(document["schema"] != "sipi.p3c.ads-or-s0-product-error-decomposition-observation-evidence.v1", "schema")
    fail(document["status"] != "external_same_axis_complex_error_decomposition_observed_acceptance_unchanged", "status")
    fail(document["authority"] != {"actor": "user", "decision_ref": "user-delegated-owner-discretion-2026-08-15", "scope": "one_fixed_same_axis_complex_error_decomposition_observation_only"}, "authority")
    observation = document["external_observation"]
    fail(not isinstance(observation, dict) or observation.get("schema") != "sipi.p3c.ads-or-s0-product-error-decomposition-observation.v1" or observation.get("fresh_runs") != 2 or observation.get("report_path_retained") is not False or observation.get("report_byte_length") != 3635 or observation.get("report_content_sha256") != "c7523bbbc525673a9131e1773bd437a3b076aaa20733aed5e6f0dc0a09e6a2bd", "observation")
    decomposition = observation.get("decomposition")
    expected = {
        "pre": ("1e824373075c3ef71b098ba533e6b35b23b3b878083be1d9a262f375a7735b37", "3ed0e4a368f3c8c8", "3f44a2e375e7a361", 14),
        "post": ("2bc9b379dae5dbba227743803cd4e6f5836815b03f29a7a71df1d49587bf63c6", "3f739d2e3bee6f9f", "3f74dc06332b6fd3", 106),
        "paired": ("dad92243662f37b37a882c2ddec4961b37da541daf692b4713a8a306f5604709", "3f739ad5699f0a89", "3f74d2f837696359", 106),
        "closure": ("2dc10498360b88a293970ceb0b6680885ba2bab3e47c34de568e08231412359c", "38abfa9182000000", "3c30000000000000", 51),
    }
    fail(not isinstance(decomposition, dict), "decomposition")
    for key, (digest, l2, maximum, index) in expected.items():
        value = decomposition.get(key)
        fail(not isinstance(value, dict) or value != {"sha256": digest, "l2_squared_bits": l2, "max_abs_bits": maximum, "max_index": index}, f"{key}_fact")
    fail(decomposition.get("cross_term_bits") != "bebe0568ad7d5495", "cross_term")
    audit = document["independent_audit"]
    fail(not isinstance(audit, dict) or audit.get("terminal") != "term_2de7cb74-b803-4e20-bb5b-4803777c24f8", "audit")
    true = {"same_axis_complex_error_decomposition_observed", "pre_surface_delta_observed", "post_surface_delta_reproduced", "paired_transition_delta_reproduced", "cross_term_observed"}
    false = {"ads_algorithm_reproduced", "causality_or_interpolation_cause_identified", "candidate_waveform_accepted", "release_ledger_promoted"}
    admission = document["admission"]
    fail(not isinstance(admission, dict) or set(admission) != true | false or any(admission[key] is not True for key in true) or any(admission[key] is not False for key in false), "gates")
    forbidden = ("file://", "http://", "https://", "c:\\", "spectrum: [", "waveform: [")
    fail(any(token in str(document).lower() for token in forbidden), "leak")
    return {"valid": True, "accepted": False, "audit": audit["status"]}


if __name__ == "__main__":
    try:
        print(verify(yaml.safe_load(PATH.read_text(encoding="utf-8"))))
    except (OSError, ValueError, yaml.YAMLError, VerificationError) as error:
        print(f"p3c_error_decomposition_failed:{error}")
        raise SystemExit(1)
