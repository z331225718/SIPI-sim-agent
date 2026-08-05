"""Reject accidental promotion or drift in the nonpublic M0 inventory."""
from __future__ import annotations
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]

def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)

def load(relative: str) -> dict:
    return json.loads((R / relative).read_text(encoding="utf-8"))

def unique(items: list[dict], key: str, label: str) -> set[str]:
    values = [item[key] for item in items]
    require(values and len(values) == len(set(values)), f"{label} must be nonempty and unique")
    return set(values)

def validate(data: dict) -> None:
    snapshot = load("docs/baselines/source-snapshot.v1.json")
    fixtures = load("fixtures/manifest.v1.json")
    platform = load("docs/baselines/platform-support.v1.json")
    baselines = {name: load(f"docs/baselines/{name}-baseline.json") for name in ("agent-spice", "pybert", "agent-com")}
    require(data["schema"] == "sipi.capability-inventory.m0.v1", "schema")
    require(data["status"] == "provisional_nonpublic_inventory", "status")
    require(not data["schema_frozen"] and not data["runtime_consumable"] and not data["advertise"], "M0 flags")
    require(platform["status"] == "selected_for_m0_not_certified", "platform support state")
    snapshot_by_root = {item["id"]: item for item in snapshot["repositories"]}
    source_ids = unique(data["sources"], "id", "sources")
    for source in data["sources"]:
        require(source["source_tag"] is None and source["tag_state"] == "missing" and source["license_state"] == "blocked_unknown", "source policy")
        if source["id"] != "agent-com-candidate":
            observed = snapshot_by_root[{"agent-spice-source":"agent-spice", "pybert-source":"py-bert-agent", "agent-com-source":"agent-com"}[source["id"]]]
            require((source["head"], source["tree"]) == (observed["head"], observed["tree"]), f"source snapshot: {source['id']}")
        else:
            candidate = baselines["agent-com"]["candidate"]
            require((source["head"], source["tree"]) == (candidate["head"], candidate["tree"]), "COM candidate source")
    environment_ids = unique(data["environments"], "id", "environments")
    require(all(item["platform_ref"] == "docs/baselines/platform-support.v1.json" for item in data["environments"]), "platform reference")
    require(all(item["python"] == "3.12.13" for item in data["environments"]), "Python environment")
    pybert_env = next(item for item in data["environments"] if item["id"] == "pybert-env")
    expected_locks = {
        "agent-spice-env": {"native/agent-spice-sim/Cargo.lock": "D8D0CC39F9A86148DF5A6CA24F4FA2077974C0C639D4E91AE524A357E39FC09A"},
        "pybert-env": {"uv.lock": "624B62D7A84FBC48579DE17E2AE171F5E4190D6AD7E5231E67DDAFB9D3FA0D86", "native/pybert-core/Cargo.lock": "9E021C575B3228465EAF5B227A0882F3C4C4BD40178EC5362A5845DD30F55715"},
        "agent-com-env": {"requirements-parity.lock": "5DB4A6486981C6398FE92C0ED25B5219872298E75A61FCD7DC80878595D67F87"},
    }
    expected_provenance = {
        "agent-spice-env": {"native/agent-spice-sim/Cargo.lock": "source_lock"},
        "pybert-env": {"uv.lock": "source_lock", "native/pybert-core/Cargo.lock": "generated_replay_not_source"},
        "agent-com-env": {"requirements-parity.lock": "source_lock"},
    }
    for environment in data["environments"]:
        require({lock["path"]: lock["sha256"] for lock in environment["locks"]} == expected_locks[environment["id"]], "environment lock hash")
        require({lock["path"]: lock["provenance_state"] for lock in environment["locks"]} == expected_provenance[environment["id"]], "environment lock provenance")
    instance_ids = unique(data["instances"], "id", "instances")
    require(all(item["source_ref"] in source_ids and item["environment_ref"] in environment_ids for item in data["instances"]), "instance references")
    fixture_by_id = {item["id"]: item for item in fixtures["assets"]}
    require(len(fixture_by_id) == len(fixtures["assets"]), "fixture manifest uniqueness")
    capabilities = data["capabilities"]; require(capabilities, "capabilities empty")
    keys = set()
    for item in capabilities:
        key = tuple(item[field] for field in ("operation", "payload_schema", "engine_instance", "behavior_profile", "platform", "execution_mode"))
        require(key not in keys, "duplicate capability key"); keys.add(key)
        require(item["engine_instance"] in instance_ids, "unknown capability instance")
        require(item["operation"] in {"circuit.solve.v1", "network.fit.v1", "link.simulate.v1", "com.r480.run.v1"}, "operation")
        require(item["evidence_state"] in {"baseline_passed", "blocked", "unverified"} and item["release_channel"] == "internal" and item["enforcement"] == "unverified", "promotion")
        required, optional = set(item["required_fixtures"]), set(item["optional_fixtures"])
        require(not required & optional and required | optional <= set(fixture_by_id), "fixture references")
        require(item["blockers"] and all({"owner", "reason", "repro_lane"} <= set(blocker) for blocker in item["blockers"]), "blockers")
        if item["evidence_state"] == "baseline_passed":
            path, pointer = item["evidence"].split("#", 1)
            node = load(path)
            for part in pointer.split("."): node = node[part]
            require(node["exit_code"] == 0 and any(key.endswith("log_sha256") for key in node), "passing evidence")
    profile_state = {item["behavior_profile"]: (item["implementation_state"], item["evidence_state"]) for item in capabilities}
    require(profile_state["s2p-s4p"] == ("absent", "unverified") and profile_state["pam4-statistical-eye"] == ("absent", "unverified") and profile_state["duobinary-statistical-eye"] == ("absent", "unverified") and profile_state["full-tx-jitter"] == ("partial", "blocked"), "PyBERT profile matrix")
    rfm = next(item for item in capabilities if item["id"] == "py-agent-spice-rfm")
    require(rfm["execution_mode"] == "composite_pyo3_subprocess", "RFM execution mode")
    for profile in ("r480", "experimental_corrected"):
        row = next(item for item in capabilities if item["behavior_profile"] == profile)
        require(set(row["required_fixtures"]) >= {"agent-com-matlab-source-and-workbooks", "agent-com-synthetic-sparameter-fixtures", "agent-com-authoritative-matlab-golden"}, "COM fixture floor")

def main() -> int:
    validate(load("docs/baselines/capability-inventory.yaml"))
    print("capability-inventory.yaml: valid nonpublic M0 inventory")
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"capability-inventory.yaml: invalid: {error}"); raise SystemExit(1)
