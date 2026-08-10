"""Verify the fail-closed P4A official pure-IBIS discovery-only record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.p4a-official-pure-ibis-discovery-preflight.v1"
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "p4a-official-pure-ibis-discovery-preflight.v1.yaml"
DIRECTORY_URL = "https://ibis.org/xml/sample1/"
CANDIDATE_URL = "https://ibis.org/xml/sample1/sample1%28original%29.ibs"


class DiscoveryError(RuntimeError):
    pass


def _exact_keys(value: dict[str, Any], keys: set[str], reason: str) -> None:
    if set(value) != keys:
        raise DiscoveryError(reason)


def validate_manifest(document: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(document, {"schema", "status", "promotion_eligible", "public_source", "candidates", "non_claims"}, "manifest_shape_invalid")
    if document["schema"] != SCHEMA or document["status"] != "official_candidate_discovery_preflight_passed" or document["promotion_eligible"] is not False:
        raise DiscoveryError("manifest_status_invalid")

    expected_source = {
        "directory_url": DIRECTORY_URL,
        "accessed_on": "2026-08-10",
        "source_class": "official_public_site",
        "directory_listing_observed": True,
    }
    if document["public_source"] != expected_source:
        raise DiscoveryError("public_source_invalid")

    candidates = document["candidates"]
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise DiscoveryError("candidate_list_invalid")
    candidate = candidates[0]
    expected_candidate = {
        "id": "ibis-org-sample1-original-ibs",
        "canonical_url": CANDIDATE_URL,
        "source_page_anchor": DIRECTORY_URL,
        "directory_entry_name": "sample1(original).ibs",
        "source_class": "official_public_site",
        "format_status": "stated_or_unverified_pure_ibs",
        "asset_identity": "url_only_unresolved",
        "license_notice_status": "not_observed_from_directory_listing",
        "eligibility": "discovery_only",
        "required": False,
        "bytes_fetched": False,
        "prohibited_uses": ["product_input", "product_fixture", "oracle_runnable", "required_profile", "release_input", "parser_test_input"],
    }
    if candidate != expected_candidate:
        raise DiscoveryError("candidate_scope_invalid")
    forbidden_keys = {"content_sha256", "asset_sha256", "local_path", "tracked_path", "bytes", "license_text", "notice_text"}
    if forbidden_keys & set(candidate):
        raise DiscoveryError("discovery_candidate_contains_material")

    non_claims = document["non_claims"]
    if not isinstance(non_claims, list) or len(non_claims) != 4 or not all(isinstance(item, str) and item for item in non_claims):
        raise DiscoveryError("non_claims_invalid")
    return {
        "schema": SCHEMA,
        "status": "official_candidate_discovery_preflight_passed",
        "candidate_id": candidate["id"],
        "required": False,
        "eligibility": "discovery_only",
        "asset_identity": "url_only_unresolved",
        "promotion_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise DiscoveryError("manifest_invalid")
        report = validate_manifest(document)
    except (OSError, yaml.YAMLError, DiscoveryError, TypeError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.report:
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "official_candidate_discovery_preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
