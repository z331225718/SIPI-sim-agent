"""Generate the M2 certified capability catalog from attested engine.lock entries.

An engine is certifiable only when: the bundle passes attestation, the license
is not blocked, and its engine.lock extensions carry a ``sipi.m2.certified``
declaration list with fixture evidence references.  Hard resource enforcement
cannot be certified before M3/G2b.  With no certifiable entries the catalog is
left absent instead of advertising an empty set.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import BundleVerificationError, verify_engine_bundle
from sipi_contracts import parse_capabilities_certified, parse_engine_lock

RESOURCE_FIELDS = ("wall_time_s", "cpu_time_s", "memory_bytes", "process_count", "artifact_bytes")
KEY_FIELDS = ["operation", "payload_schema", "engine_instance", "behavior_profile", "platform.os", "platform.architecture", "execution_mode"]
CERT_EXTENSION = "sipi.m2.certified"


def _entry(engine: dict, declaration: dict, bundle_hash: str) -> dict:
    required = {"operation", "payload_schema", "behavior_profile", "role", "evidence_refs", "certified_at", "expires_at"}
    missing = sorted(required - set(declaration))
    if missing:
        raise ValueError(f"{engine['instance_id']} certified declaration missing: {missing}")
    evidence_refs = declaration["evidence_refs"]
    if not isinstance(evidence_refs, (list, tuple)) or not evidence_refs or not all(isinstance(item, str) and item for item in evidence_refs):
        raise ValueError(f"{engine['instance_id']} certified declaration requires non-empty evidence_refs")
    enforcement = declaration.get("resource_enforcement")
    if enforcement is None:
        enforcement = {name: "unsupported" for name in RESOURCE_FIELDS}
    if any(enforcement.get(name) == "hard" for name in RESOURCE_FIELDS):
        raise ValueError(f"{engine['instance_id']} hard enforcement cannot be certified before M3/G2b")
    return {
        "operation": declaration["operation"],
        "payload_schema": declaration["payload_schema"],
        "engine_instance": engine["instance_id"],
        "bundle_hash": bundle_hash,
        "behavior_profile": declaration["behavior_profile"],
        "platform": {"os": engine["runtime"]["os"], "architecture": engine["runtime"]["architecture"]},
        "execution_mode": declaration.get("execution_mode", "process"),
        "role": declaration["role"],
        "evidence_state": "certified",
        "release_channel": "stable",
        "resource_enforcement": enforcement,
        "evidence_refs": list(evidence_refs),
        "certified_at": declaration["certified_at"],
        "expires_at": declaration["expires_at"],
        "limits": declaration.get("limits") or {},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    lock_path = root / "engine.lock"
    output = root / "docs" / "baselines" / "capabilities.certified.v1.json"
    if not lock_path.is_file():
        print("engine.lock absent; no certified capabilities (catalog not written)")
        return 0
    lock = parse_engine_lock(lock_path.read_text(encoding="utf-8")).wire
    entries: list[dict] = []
    for engine in lock["engines"]:
        if engine["license_provenance"]["distribution_status"] == "blocked_unknown":
            print(f"skip {engine['instance_id']}: license blocked")
            continue
        try:
            verify_engine_bundle(engine, root)
        except BundleVerificationError as error:
            print(f"skip {engine['instance_id']}: attestation failed: {error}")
            continue
        declarations = engine.get("extensions", {}).get(CERT_EXTENSION)
        if not isinstance(declarations, (list, tuple)) or not declarations:
            print(f"skip {engine['instance_id']}: no {CERT_EXTENSION} declaration")
            continue
        bundle_hash = "sha256:" + engine["bundle"]["sha256"]
        for declaration in declarations:
            entries.append(_entry(engine, declaration, bundle_hash))
    if not entries:
        print("no certified capabilities; catalog not written")
        return 0
    catalog = {
        "schema": "sipi.capabilities-certified.v1",
        "status": "certified",
        "advertise": True,
        "capability_key_fields": KEY_FIELDS,
        "entries": entries,
        "non_claims": [
            "Hard resource enforcement is certified only after M3/G2b evidence.",
            "Certification applies only to the attested bundle hash and platform.",
        ],
    }
    parsed = parse_capabilities_certified(catalog, producer=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(parsed.to_wire(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} with {len(entries)} certified entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
