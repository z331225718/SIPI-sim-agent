"""Generate the M3/G2b certified capability catalog for hard enforcement.

M2's ``build_m2_capabilities_certified.py`` refuses every ``hard`` enforcement
entry because hard enforcement certification requires M3/G2b lifecycle
evidence.  This tool lifts that gate for the Windows x86_64 managed worker
only: an engine may declare ``hard`` resource enforcement in
``sipi.m2.certified`` entries only when the declaration references a G2b fault
fixture whose evidence (``tests/adapters/test_g2b_fault_fixtures.py``,
fixture id ``g2b-windows-managed-worker-v1``) covers every advertised hard
field on the exact platform/execution key.

Linux/macOS hard enforcement stays uncertified (their fault fixtures are not
part of this certification run); wall_time/memory/cpu/process/artifact all
must be covered by a real fault hit before being advertised as hard.
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
G2B_FIXTURE_ID = "g2b-windows-managed-worker-v1"
G2B_EVIDENCE_FILE = "tests/adapters/test_g2b_fault_fixtures.py"
G2B_COVERED_FIELDS = {
    "wall_time_s": "wall_time",
    "cpu_time_s": "cpu_time",
    "memory_bytes": "memory",
    "process_count": "process_count",
    "artifact_bytes": "artifact_bytes",
}


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
    platform = engine["runtime"]
    is_windows_managed = platform["os"] == "windows" and platform["architecture"] == "x86_64" and declaration.get("execution_mode", "process") == "managed_worker"
    for name in RESOURCE_FIELDS:
        if enforcement.get(name) != "hard":
            continue
        if not is_windows_managed:
            raise ValueError(f"{engine['instance_id']} hard {name} is only certified on Windows x86_64 managed worker (G2b)")
        fixture = f"{G2B_FIXTURE_ID}:{G2B_COVERED_FIELDS[name]}"
        if not any(fixture == ref or fixture in ref for ref in evidence_refs):
            raise ValueError(f"{engine['instance_id']} hard {name} requires G2b fault fixture evidence ref {fixture!r}")
    return {
        "operation": declaration["operation"],
        "payload_schema": declaration["payload_schema"],
        "engine_instance": engine["instance_id"],
        "bundle_hash": bundle_hash,
        "behavior_profile": declaration["behavior_profile"],
        "platform": {"os": platform["os"], "architecture": platform["architecture"]},
        "execution_mode": declaration.get("execution_mode", "process"),
        "role": declaration["role"],
        "evidence_state": "certified",
        "release_channel": "stable",
        "resource_enforcement": dict(enforcement),
        "evidence_refs": list(evidence_refs),
        "certified_at": declaration["certified_at"],
        "expires_at": declaration["expires_at"],
        "limits": dict(declaration.get("limits") or {}),
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
            "Hard enforcement certified on Windows x86_64 managed worker only (G2b fixture g2b-windows-managed-worker-v1).",
            "Linux/macOS hard enforcement is not certified by this catalog.",
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
