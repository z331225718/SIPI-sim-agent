"""Fail closed on the required RFM receiver profile's still-blocked semantics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.receiver-candidate-readiness.v1"
PROFILE_ID = "channel-rfm-block-2-current-drive-v1"
SHA1_LENGTH = 40
SHA256_LENGTH = 64
MISSING = "missing_owner_selection"
EVIDENCE_REF = "docs/baselines/audits/2026-08-08-m5.md#m5b-03c-git-object-rfm-same-config-receiver-parity"
REQUIRED_BY = "user-confirmed-2026-08-10-channel-rfm-receiver"

MISSING_FIELDS = {
    "product_stimulus_and_causal_link_waveform",
    "p3a_periodic_kernel_causalization",
    "ctle_transfer_normalization_and_state",
    "ffe_tap_order_cursor_units_sign_and_initial_state",
    "dfe_tap_order_cursor_units_sign_and_initial_state",
    "cdr_clock_source_acquisition_lock_reset_and_cancel",
    "ber_bit_source_alignment_threshold_warmup_window_metric_and_tolerance",
    "external_reference_environment_and_authorized_fixture_scope",
}


def _load(path: Path) -> dict:
    if yaml is None:
        raise RuntimeError("pyyaml is unavailable")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("readiness document must be a YAML object")
    return document


def _exact(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(char in "0123456789abcdef" for char in value)


def _safe_ref(value: object) -> bool:
    return isinstance(value, str) and value and "\\" not in value and not value.startswith("/") and ".." not in value.split("/")


def _heading_slug(title: str) -> str:
    characters = []
    previous_dash = False
    for character in title.lower():
        if character.isascii() and character.isalnum():
            characters.append(character)
            previous_dash = False
        elif character in {" ", "-"} and not previous_dash:
            characters.append("-")
            previous_dash = True
    return "".join(characters).strip("-")


def _evidence_ref_exists(value: object) -> bool:
    if value != EVIDENCE_REF:
        return False
    path_text, fragment = str(value).split("#", 1)
    path = ROOT / path_text
    if not path.is_file():
        return False
    headings = [line.lstrip("#").strip() for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("#")]
    return fragment in {_heading_slug(heading) for heading in headings}


def _candidate_profile(document: dict) -> dict | None:
    profiles = document.get("profiles")
    if not isinstance(profiles, list):
        return None
    return next((profile for profile in profiles if isinstance(profile, dict) and profile.get("id") == PROFILE_ID), None)


def verify_document(readiness: object, inventory: object) -> dict:
    blockers: list[str] = []
    required_top = {"schema", "status", "candidate_profile_id", "candidate_identity", "external_observation", "owner_decision", "missing_semantics", "non_claims"}
    if not _exact(readiness, required_top):
        return {"valid": False, "blockers": ["readiness has unknown or missing top-level fields"]}
    if readiness["schema"] != SCHEMA or readiness["status"] != "required_selected_missing_receiver_semantics" or readiness["candidate_profile_id"] != PROFILE_ID:
        blockers.append("schema, status, or required profile mismatch")
    profile = _candidate_profile(inventory) if isinstance(inventory, dict) else None
    if profile is None:
        blockers.append("required profile is absent from acceptance inventory")
    elif profile.get("boundary") != "oracle_only" or profile.get("acceptance", {}).get("status") != "required_blocked_missing_receiver_semantics" or profile.get("acceptance", {}).get("required_by") != REQUIRED_BY:
        blockers.append("required profile must remain oracle-only with semantic blockers")
    elif (
        profile.get("environment", {}).get("provenance_ref") != EVIDENCE_REF
        or profile.get("acceptance", {}).get("tolerance_policy_ref") != EVIDENCE_REF
        or profile.get("evidence_refs") != [EVIDENCE_REF]
        or not _evidence_ref_exists(EVIDENCE_REF)
    ):
        blockers.append("required profile receiver evidence anchor is invalid")
    identity = readiness["candidate_identity"]
    identity_keys = {"repository", "commit", "path", "git_blob", "content_sha256"}
    if not _exact(identity, identity_keys) or not isinstance(identity.get("repository"), str) or not _hex(identity.get("commit"), SHA1_LENGTH) or not _safe_ref(identity.get("path")) or not _hex(identity.get("git_blob"), SHA1_LENGTH) or not _hex(identity.get("content_sha256"), SHA256_LENGTH):
        blockers.append("candidate identity is invalid")
    elif profile is not None:
        source = profile.get("source")
        repository = next((item for item in inventory.get("repositories", []) if item.get("id") == identity["repository"]), None)
        if not isinstance(source, dict) or not isinstance(repository, dict) or any((identity[key] != source[key] for key in ("repository", "path", "git_blob", "content_sha256"))) or identity["commit"] != repository.get("commit"):
            blockers.append("candidate identity does not match acceptance inventory")
    observation = readiness["external_observation"]
    observation_keys = {"platform", "engine_sha256", "transfer", "current_to_voltage_sign", "fft_size", "current_sample_count", "sample_interval_seconds", "input_ports", "output_ports", "samples_per_ui", "evidence_ref"}
    if not _exact(observation, observation_keys):
        blockers.append("external observation has unknown or missing fields")
    elif not (
        observation["platform"] == "windows-x86_64"
        and _hex(observation["engine_sha256"], SHA256_LENGTH)
        and observation["transfer"] == "current_drive_voltage_response"
        and observation["current_to_voltage_sign"] == -1
        and observation["fft_size"] == observation["current_sample_count"] == 1024
        and observation["sample_interval_seconds"] == 1.0e-12
        and observation["input_ports"] == [1]
        and observation["output_ports"] == [2]
        and observation["samples_per_ui"] == 8
        and _evidence_ref_exists(observation["evidence_ref"])
    ):
        blockers.append("external observation is not the pinned RFM receiver record")
    decision = readiness["owner_decision"]
    if not _exact(decision, {"required_by", "decision"}) or decision["required_by"] != REQUIRED_BY or decision["decision"] != "required":
        blockers.append("required decision is invalid")
    missing = readiness["missing_semantics"]
    if not _exact(missing, MISSING_FIELDS) or any(value != MISSING for value in missing.values()):
        blockers.append("all receiver semantics must remain explicitly missing owner selection")
    non_claims = readiness["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) < 3 or not all(isinstance(item, str) and item for item in non_claims):
        blockers.append("non-claims are incomplete")
    return {
        "valid": not blockers,
        "status": readiness.get("status"),
        "candidate_profile_id": readiness.get("candidate_profile_id"),
        "required_profile_count": 1,
        "missing_semantics_count": len(missing) if isinstance(missing, dict) else 0,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, default=ROOT / "docs/baselines/channel-rfm-receiver-readiness.v1.yaml")
    parser.add_argument("--inventory", type=Path, default=ROOT / "acceptance-profiles.v1.yaml")
    args = parser.parse_args()
    try:
        report = verify_document(_load(args.readiness), _load(args.inventory))
    except (OSError, RuntimeError) as error:
        print(json.dumps({"valid": False, "blockers": [str(error)]}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
