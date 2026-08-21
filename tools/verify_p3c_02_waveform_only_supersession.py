"""Verify the P3C-02 selected waveform-only supersession record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/p3c-02-waveform-only-supersession.v1.yaml"
SCHEMA = "sipi.p3c-02.waveform-only-supersession.v1"
STATUS = "p3c_02_current_route_obligation_resolved_not_applicable"
REFERENCES = {
    "docs/baselines/owner-decision-reconciliation.v2.yaml": "4e9109e3adde405f3c6529bd6d09f27828a0cc56959eeb024b5600865bbba1f0",
    "docs/baselines/p3c-selected-highloss-prbs9-waveform-only-contract.v3.yaml": "db0d9a663b311105be329d79060f05a5179f40fd7eccf448faf85d45b73da64a",
    "docs/baselines/p3c-selected-highloss-prbs9-waveform-only-core.v3.yaml": "d1562d0fc8de56584b3be1082f7b8dafc9a20693cae44330cb012bbd4e385e36",
    "docs/baselines/p3c-02-current-semantics-gap.v1.yaml": "59dd1e96188038e92944cebec349c8f8c971b7556ef9bd562c38bd79c030884e",
    "docs/baselines/audits/2026-08-21-p3c-02-waveform-only-supersession.md": "2f7e1cf06080867d9bfafc2a5dbdd3874f564dc772b7634972beb1f1fdbc9ba2",
}


class P3C02SupersessionError(RuntimeError):
    pass


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise P3C02SupersessionError(message)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _expect(isinstance(value, dict), "document_not_mapping")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: Path = ROOT) -> dict[str, Any]:
    evidence = _load(EVIDENCE)
    _expect(evidence.get("schema") == SCHEMA, "schema_invalid")
    _expect(evidence.get("status") == STATUS, "status_invalid")

    scope = evidence.get("scope")
    _expect(scope == {
        "work_item": "P3C-02",
        "route": "selected_highloss_exact",
        "resolution": "current_route_semantics_scoped_closed",
        "product_rust_changed": False,
        "historical_evidence_rewritten": False,
        "generic_cores_deleted": False,
        "external_runtime_invoked": False,
        "acceptance_or_release_promoted": False,
    }, "scope_drift")

    owner = evidence.get("owner_decision")
    _expect(isinstance(owner, dict), "owner_decision_missing")
    _expect(owner.get("profile") == "selected_highloss_exact", "profile_drift")
    _expect(owner.get("receiver") == "none", "receiver_drift")
    _expect(owner.get("scope") == "waveform_only", "route_scope_drift")
    _expect(owner.get("included_observables") == ["waveform"], "included_observables_drift")
    _expect(owner.get("excluded_observables") == ["eye", "TIE", "bathtub"], "excluded_observables_drift")
    _expect(owner.get("closed_eye_fallback") == "prohibited", "fallback_drift")

    contract = evidence.get("selected_route_contract")
    _expect(isinstance(contract, dict), "selected_contract_missing")
    _expect(contract.get("receiver_or_equalizer_stage") == "none", "contract_receiver_drift")
    _expect(contract.get("waveform_alignment") == "prohibited", "alignment_drift")
    _expect(str(contract.get("eye_status", "")).startswith("excluded_not_evaluated"), "eye_scope_drift")
    _expect(str(contract.get("jitter_status", "")).startswith("excluded_not_evaluated"), "jitter_scope_drift")

    core = evidence.get("selected_route_core")
    _expect(isinstance(core, dict), "selected_core_missing")
    _expect(core.get("entrypoint") == "compare_selected_highloss_prbs9_waveform_only_v3", "entrypoint_drift")
    _expect(core.get("selected_highloss_waveform_only_contract_ready") is True, "contract_not_ready")
    _expect(core.get("acceptance_ready") is False, "acceptance_promoted")

    supersession = evidence.get("supersession")
    _expect(isinstance(supersession, dict), "supersession_missing")
    _expect(supersession.get("superseded_claim") == "current_selected_route_requires_new_eye_or_bathtub_semantics", "superseded_claim_drift")
    _expect(supersession.get("replacement") == "eye_tie_bathtub_not_applicable_to_current_selected_route", "replacement_drift")
    _expect(supersession.get("prior_record_retained") is True, "historical_record_removed")

    future = evidence.get("future_extension_gate")
    _expect(future == {
        "required": "new_owner_selected_additive_profile",
        "guessing_from_original_project": "prohibited",
        "alignment_or_tolerance_relaxation": "prohibited",
    }, "future_gate_drift")

    bindings = {
        owner["path"]: owner["sha256"],
        contract["path"]: contract["sha256"],
        core["path"]: core["sha256"],
        supersession["prior_gap_path"]: supersession["prior_gap_sha256"],
        evidence["audit"]["path"]: evidence["audit"]["sha256"],
    }
    _expect(bindings == REFERENCES, "reference_inventory_drift")
    for relative, expected in REFERENCES.items():
        path = root / relative
        _expect(path.is_file(), f"reference_missing:{relative}")
        _expect(_sha256(path) == expected, f"reference_hash_invalid:{relative}")

    claims = set(evidence.get("non_claims", []))
    _expect({"not_waveform_acceptance", "not_eye_or_bathtub_acceptance", "not_release_evidence"} <= claims, "non_claim_missing")
    return {"schema": SCHEMA, "valid": True, "status": STATUS, "current_route_closed": True}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        result = validate(ROOT)
    except (OSError, UnicodeError, yaml.YAMLError, KeyError, P3C02SupersessionError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
