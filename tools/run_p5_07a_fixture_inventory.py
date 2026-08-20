"""P5-07a synthetic fixture inventory (MATLAB-oracle-bound set).

Lists every registered COM synthetic fixture with its role, hash,
and the manifest facts (generator model, port orders, frequency
grid), noting any manifest-vs-current hash difference. Hash-bound;
the MATLAB oracle (P5-06a) is the sole oracle for this set.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
INVENTORY = ROOT / "docs" / "baselines" / "p5-07-synthetic-fixture-inventory.v1.yaml"
INVENTORY_SCHEMA = "sipi.p5-07.synthetic-fixture-inventory.v1"
FIXTURE_IDS = [
    "com-synthetic-thru", "com-synthetic-fext", "com-synthetic-next",
    "com-synthetic-erl-reflective-s4p", "com-synthetic-erl-reflective-json",
    "com-synthetic-erl-s2p", "com-synthetic-erl-s2p-json",
    "com-synthetic-kappa-asym-s4p", "com-synthetic-kappa-asym-json",
    "com-synthetic-td-thru", "com-synthetic-td-fext", "com-synthetic-td-next",
    "com-synthetic-td-manifest", "com-synthetic-manifest",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    materials = {m["id"]: m for m in registry["materials"]}
    entries = []
    for material_id in FIXTURE_IDS:
        material = materials.get(material_id)
        if material is None:
            raise SystemExit("missing: " + material_id)
        source = Path(str(material["path"]).replace("/", "\\"))
        actual = sha256_file(source)
        if actual != material["sha256"].lower():
            raise SystemExit("hash drift: " + material_id)
        entries.append({
            "material_id": material_id,
            "logical_name": material["logical_name"],
            "kind": material["kind"],
            "sha256": actual,
            "byte_length": material["byte_length"],
        })
    manifest = materials.get("com-synthetic-manifest")
    manifest_path = Path(str(manifest["path"]).replace("/", "\\"))
    manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) if manifest_path.suffix == ".json" else None
    import json as jsonlib
    manifest_data = jsonlib.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_channels = manifest_data.get("channels", [])
    manifest_hash_diffs = []
    current_by_name = {e["logical_name"]: e["sha256"] for e in entries}
    for channel in manifest_channels:
        file_name = channel.get("file")
        declared = channel.get("sha256", "").lower()
        current = current_by_name.get(file_name)
        if current is not None and declared and declared != current:
            manifest_hash_diffs.append({"file": file_name, "manifest_sha256": declared, "current_sha256": current})
    inventory = {
        "schema": INVENTORY_SCHEMA,
        "status": "synthetic_fixture_set_inventoried_hash_bound",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "oracle_ref": "docs/baselines/p5-06-matlab-oracle-first-run-evidence.v1.yaml",
        "fixture_count": len(entries),
        "fixtures": entries,
        "manifest_facts": {
            "generator": manifest_data.get("generator"),
            "target_frequency_hz": manifest_data.get("target_frequency_hz"),
            "frequency_start_hz": manifest_data.get("frequency_start_hz"),
            "frequency_stop_hz": manifest_data.get("frequency_stop_hz"),
            "frequency_step_hz": manifest_data.get("frequency_step_hz"),
            "file_port_order": manifest_data.get("file_port_order"),
            "com_internal_port_order": manifest_data.get("com_internal_port_order"),
            "models": sorted({c.get("model") for c in manifest_channels}),
        },
        "manifest_hash_diffs": manifest_hash_diffs,
        "non_claims": [
            "not_a_compare",
            "not_product_fixture_admission",
            "not_release_evidence",
        ],
    }
    INVENTORY.write_text(yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")
    print("fixtures=" + str(len(entries)) + " hash_diffs=" + str(len(manifest_hash_diffs)))
    print("inventory written: " + str(INVENTORY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
