"""Verify the immutable selected-profile TP0V R2024b v4 formal record."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/com-tp0v-current-asset-r2024b-formal.v4.yaml"
RECORD_IDS = ("matlab-01", "matlab-02", "rust-01", "rust-02")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_bound(entry: Any, label: str) -> dict[str, Any]:
    require(isinstance(entry, dict) and set(entry) == {"path", "bytes", "sha256"}, f"{label}: receipt shape")
    relative = Path(entry["path"])
    require(not relative.is_absolute() and ".." not in relative.parts, f"{label}: unsafe path")
    path = (ROOT / relative).resolve()
    require(ROOT in path.parents and path.is_file(), f"{label}: missing record")
    require(path.stat().st_size == entry["bytes"] and sha256(path) == entry["sha256"], f"{label}: content drift")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(document: dict[str, Any]) -> dict[str, Any]:
    require(document.get("schema") == "sipi.com.tp0v-current-asset-formal.v4", "schema")
    require(document.get("status") == "accepted_selected_profile", "status")
    scope = document.get("scope")
    require(isinstance(scope, dict) and scope.get("matlab") == "R2024b" and scope.get("package_case_index") == 0 and scope.get("normal_erl_port") == 1, "scope")
    require(scope.get("rust_route") == "public_root_sipi_com_run" and scope.get("channel_processing") == "raw_fd_to_td_no_s_parameter_fit", "route/processing")
    candidate = document.get("candidate")
    require(isinstance(candidate, dict) and candidate.get("commit") == "b255967c91898f720a16e5029af09521f94fa7df", "candidate")
    records = document.get("records")
    require(isinstance(records, dict) and set(records) == set(RECORD_IDS), "record set")
    payloads = {name: read_bound(records[name], name) for name in RECORD_IDS}
    for name, payload in payloads.items():
        require(payload.get("run_id") == name and payload.get("status") == "passed", f"{name}: replay status")
        require(payload.get("candidate") == candidate, f"{name}: candidate drift")
        require(payload.get("gates", {}).get("internal_exact_repeat") is True, f"{name}: repeat")
    aggregate = read_bound(document.get("aggregate"), "aggregate")
    require(aggregate.get("status") == "passed" and aggregate.get("blockers") == [], "aggregate status")
    gates = aggregate.get("gates", {})
    for name in ("independent_replay_roots", "independent_replay_nonces", "internal_exact_repeat", "ordered_elementwise_vector_comparison", "performance_each_case_rust_strictly_faster", "mat_bridge"):
        require(gates.get(name) is True, f"aggregate gate: {name}")
    d3 = document.get("d3")
    require(d3 == {"status": "not_evaluated_configuration_disables_tdiln", "compute_tdiln": 0, "global_d3_blocker_open": True}, "D3 boundary")
    provenance = document.get("provenance")
    require(isinstance(provenance, dict) and provenance.get("prep_manifest") == "docs/baselines/com-tp0v-current-asset-scoped-acceptance.v4.yaml" and provenance.get("source_reports_are_bound_replay_receipts") is True, "provenance")
    audit = provenance.get("audit")
    require(isinstance(audit, dict) and set(audit) == {"path", "sha256"}, "audit receipt")
    audit_path = (ROOT / audit["path"]).resolve()
    require(ROOT in audit_path.parents and audit_path.is_file() and sha256(audit_path) == audit["sha256"], "audit drift")
    return {"valid": True, "status": document["status"], "scope": "selected_tp0v_case0_port1", "global_d3_blocker_open": True}


if __name__ == "__main__":
    print(json.dumps(validate(yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))), sort_keys=True))
