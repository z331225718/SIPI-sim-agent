"""Verify the additive owner authorization for the recommended remaining-item bundle."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/baselines/owner-recommended-bundle-authorization.v1.yaml"
PROMPT = ROOT / "docs/owner-response-request-20260821-remaining-22.md"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-owner-recommended-bundle-authorization.md"
SCHEMA = "sipi.owner-recommended-bundle-authorization.v1"
PROMPT_SHA256 = "68063ad2f1e9e182ff16eb1651eaa68534d0bbfbdfa73edc815d2eb5b66211ab"


class AuthorizationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuthorizationError(f"document_not_mapping:{path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise AuthorizationError(reason)


def validate(document: dict[str, Any] | None = None) -> dict[str, Any]:
    document = _load(DOCUMENT) if document is None else document
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "authorized_policy_external_facts_pending", "status_invalid")
    authority = document.get("authority")
    _require(isinstance(authority, dict), "authority_invalid")
    _require(authority.get("actor") == "user", "authority_actor_invalid")
    _require(authority.get("recorded_at") == "2026-08-21", "authority_date_invalid")
    _require(authority.get("reply") == "全部按推荐", "authority_reply_invalid")
    prompt = authority.get("prompt")
    _require(prompt == {
        "path": "docs/owner-response-request-20260821-remaining-22.md",
        "sha256": PROMPT_SHA256,
        "baseline_commit": "58ddf6f9",
    }, "prompt_binding_invalid")
    _require(PROMPT.is_file() and _sha256(PROMPT) == PROMPT_SHA256, "prompt_content_drift")

    decisions = document.get("decisions")
    _require(isinstance(decisions, dict), "decisions_invalid")
    _require(set(decisions) == {"D1", "D2", "D3", "D4", "D5", "D6", "E3", "E4", "E7"}, "decision_set_invalid")
    for key in ("D1", "D2", "D4", "D5", "D6", "E3", "E4"):
        _require(decisions.get(key) == "A", f"decision_invalid:{key}")
    _require(decisions.get("E7") == "accepted", "external_boundary_decision_invalid")
    _require(decisions.get("D3") == {
        "option": "A",
        "oracle": "pinned_agent_com_r480",
        "metrics": ["COM_dB", "ERL_dB", "TD_ILN_dB"],
        "absolute_tolerance_db": 0.1,
        "alignment": "prohibited",
        "checkpoint": "strict_same_checkpoint_pending_exact_name",
    }, "d3_policy_invalid")

    _require(document.get("external_boundary") == {
        "access": "read_only_external",
        "execution": "clean_or_isolated_outside_repository",
        "repository_evidence": "hash_length_bounded_aggregate_only",
        "third_party_bytes_in_repository": "prohibited",
        "third_party_bytes_in_release": "prohibited",
        "redistribution_without_explicit_proof": "prohibited",
        "source_specific_license_audit_required": True,
    }, "external_boundary_invalid")
    _require(document.get("release_target") == {
        "platform": "windows_x86_64_msvc",
        "minimum_os": "windows_10_or_server_2016",
        "package_contents": ["sipi.exe", "LICENSE"],
        "fresh_machine_required": True,
    }, "release_target_invalid")
    unresolved = document.get("unresolved_external_facts")
    _require(isinstance(unresolved, list) and len(unresolved) == 8 and len(set(unresolved)) == 8, "unresolved_facts_invalid")
    non_claims = document.get("non_claims")
    _require(isinstance(non_claims, list) and set(non_claims) == {
        "owner_policy_does_not_create_third_party_rights",
        "recommended_option_does_not_authorize_guessing_missing_values",
        "external_execution_authorization_is_not_product_acceptance",
        "tolerance_selection_is_not_oracle_authority",
        "specified_cli_is_not_external_oracle_acceptance",
        "p7_release_gates_remain_blocked",
        "historical_evidence_is_not_rewritten",
    }, "non_claims_invalid")
    _require(document.get("audit_ref") == "docs/baselines/audits/2026-08-21-owner-recommended-bundle-authorization.md", "audit_ref_invalid")
    _require(AUDIT.is_file(), "audit_missing")
    return {"schema": SCHEMA, "valid": True, "decisions": len(decisions), "external_facts_pending": len(unresolved)}


def main() -> int:
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, yaml.YAMLError, AuthorizationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
