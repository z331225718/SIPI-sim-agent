"""Fail closed verification for the current P3B Link stage capability ledger."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "docs/baselines/p3b-link-stage-capability-ledger.v1.yaml"
SCHEMA = "sipi.link-stage-capability-ledger.v1"
EXPECTED = {
    "direct_launch": ("plan.tx", "supported"),
    "causal_fir_channel": ("plan.channel", "supported"),
    "ctle_bypass": ("plan.rx.ctle", "explicit_bypass"),
    "ffe_bypass": ("plan.rx.ffe", "explicit_bypass"),
    "deterministic_seed": ("request.seed", "reject"),
    "prbs_stimulus": ("plan.tx.kind=prbs", "reject"),
    "noise_injection": ("plan.noise", "reject"),
    "jitter_time_warp": ("plan.timebase.jitter", "reject"),
    "dfe_stage": ("plan.rx.dfe", "reject"),
    "cdr_stage": ("plan.rx.cdr", "reject"),
    "ber_stage": ("plan.rx.ber", "reject"),
    "fixed_receiver_library": ("sipi-link::run_fixed_receiver_v1", "library_only_profile_blocked"),
}
DISPOSITIONS = {"supported", "explicit_bypass", "reject", "library_only_profile_blocked"}


def verify(document: object) -> dict:
    blockers: list[str] = []
    if not isinstance(document, dict) or set(document) != {
        "schema", "status", "scope", "profile_context", "entries", "non_claims"
    }:
        return {"valid": False, "blockers": ["ledger top-level schema is invalid"]}
    if document["schema"] != SCHEMA or document["status"] != "provisional":
        blockers.append("ledger identity is invalid")
    if document["scope"] != "sipi.link.causal-fir-request.v1":
        blockers.append("ledger scope drifted")
    if document["profile_context"] != {
        "receiver_profile": "channel-rfm-block-2-current-drive-v1",
        "receiver_profile_status": "blocked_cdr_ambiguous_under_approved_charter",
    }:
        blockers.append("receiver profile context drifted")
    entries = document["entries"]
    if not isinstance(entries, list):
        blockers.append("entries must be a list")
        entries = []
    by_id = {entry.get("id"): entry for entry in entries if isinstance(entry, dict)}
    if len(by_id) != len(entries) or set(by_id) != set(EXPECTED):
        blockers.append("ledger entry ids are incomplete or duplicated")
    for entry_id, (interface, disposition) in EXPECTED.items():
        entry = by_id.get(entry_id)
        if not isinstance(entry, dict):
            continue
        if entry.get("interface") != interface or entry.get("disposition") != disposition:
            blockers.append(f"{entry_id}: interface or disposition drifted")
            continue
        allowed = {"id", "interface", "disposition", "test_ref"}
        if disposition in {"supported", "explicit_bypass", "library_only_profile_blocked"}:
            allowed.add("implementation_ref")
        if disposition == "reject":
            allowed.add("required_owner_input")
        if disposition == "library_only_profile_blocked":
            allowed.add("blocked_by")
        if set(entry) != allowed:
            blockers.append(f"{entry_id}: fields are invalid")
        if not isinstance(entry.get("test_ref"), str) or not entry["test_ref"]:
            blockers.append(f"{entry_id}: missing test anchor")
        if disposition in {"supported", "explicit_bypass", "library_only_profile_blocked"} and (
            not isinstance(entry.get("implementation_ref"), str) or not entry["implementation_ref"]
        ):
            blockers.append(f"{entry_id}: missing implementation anchor")
        if disposition == "reject" and (
            not isinstance(entry.get("required_owner_input"), str) or not entry["required_owner_input"]
        ):
            blockers.append(f"{entry_id}: missing owner input")
        if disposition == "library_only_profile_blocked" and entry.get("blocked_by") != "blocked_cdr_ambiguous_under_approved_charter":
            blockers.append(f"{entry_id}: blocked status drifted")
    if not isinstance(document["non_claims"], list) or len(document["non_claims"]) != 3 or not all(
        isinstance(value, str) and value for value in document["non_claims"]
    ):
        blockers.append("non-claims are incomplete")
    return {"valid": not blockers, "blockers": blockers, "entry_count": len(entries)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.ledger.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, sort_keys=True))
        return 2
    result = verify(document)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
