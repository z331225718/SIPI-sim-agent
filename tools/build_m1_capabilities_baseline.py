"""Deterministically normalize the nonpublic M0 inventory for M1 consumers."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/baselines/capability-inventory.yaml"
OUTPUT = ROOT / "docs/baselines/capabilities.baseline.v1.json"
ALLOWED = {"schema", "status", "schema_frozen", "runtime_consumable", "advertise", "policy", "sources", "environments", "legacy_artifacts", "instances", "capabilities", "unmapped_capability_gaps", "non_claims"}
CAPABILITY_FIELDS = {"id", "operation", "payload_schema", "engine_instance", "behavior_profile", "platform", "execution_mode", "role", "implementation_state", "evidence_state", "release_channel", "enforcement", "required_fixtures", "optional_fixtures", "evidence", "blockers"}

def main() -> None:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    unknown = set(raw) - ALLOWED
    if unknown or set(raw) != ALLOWED: raise ValueError(f"unmapped inventory fields: {sorted(unknown or (ALLOWED-set(raw)))}")
    if raw["schema"] != "sipi.capability-inventory.m0.v1" or raw["schema_frozen"] or raw["runtime_consumable"] or raw["advertise"]: raise ValueError("input is not a nonpublic M0 inventory")
    capabilities=[]
    for item in raw["capabilities"]:
        if set(item) != CAPABILITY_FIELDS: raise ValueError(f"unmapped capability fields: {sorted(set(item) ^ CAPABILITY_FIELDS)}")
        capabilities.append({
            "source_inventory_id": item["id"],
            "key": {"operation":item["operation"], "payload_schema":item["payload_schema"], "engine_instance":item["engine_instance"], "behavior_profile":item["behavior_profile"], "platform":{"os":"windows", "architecture":"x86_64", "source_literal":item["platform"]}, "execution_mode":item["execution_mode"]},
            "role":item["role"], "implementation_state":item["implementation_state"], "evidence_state":item["evidence_state"], "release_channel":item["release_channel"], "enforcement_state":item["enforcement"],
            "fixtures":{"required":item["required_fixtures"],"optional":item["optional_fixtures"]}, "evidence_refs":[item["evidence"]], "blockers":item["blockers"]})
    out={"schema":"sipi.capabilities-baseline.v1","status":"baseline_nonpublic","runtime_consumable":False,"advertise":False,"default_auto_eligible":False,"source":{"path":"docs/baselines/capability-inventory.yaml","schema":raw["schema"],"sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper(),"converter_version":"m1-01b.1","observed_metadata":{"status":raw["status"],"schema_frozen":raw["schema_frozen"],"runtime_consumable":raw["runtime_consumable"],"advertise":raw["advertise"],"policy":raw["policy"]}},"capability_key_fields":["operation","payload_schema","engine_instance","behavior_profile","platform.os","platform.architecture","execution_mode"],"catalogs":{"sources":raw["sources"],"environments":raw["environments"],"legacy_artifacts":raw["legacy_artifacts"],"instances":raw["instances"]},"capabilities":capabilities,"unmapped_capability_gaps":raw["unmapped_capability_gaps"],"non_claims":raw["non_claims"]}
    OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=True)+"\n", encoding="utf-8")

if __name__ == "__main__": main()
