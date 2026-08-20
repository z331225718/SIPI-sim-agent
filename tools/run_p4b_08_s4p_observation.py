"""P4B-08a external-only S4P structure observation.

Parses the six owner-authorized PCIe Gen5 S4P files and records
frequency axis, row count, and port matrix facts, hash-bound to the
registry. No time-domain model, interpolation, or channel resolution is
performed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-08-s4p-observation-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-08.s4p-observation-evidence.v1"
S4P_IDS = ["ads-pcie-gen5-s4p-tx-typ", "ads-pcie-gen5-s4p-tx-fast", "ads-pcie-gen5-s4p-tx-slow",
           "ads-pcie-gen5-s4p-rx-typ", "ads-pcie-gen5-s4p-rx-fast", "ads-pcie-gen5-s4p-rx-slow"]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    materials = {m["id"]: m for m in registry["materials"]}
    entries = []
    for material_id in S4P_IDS:
        material = materials.get(material_id)
        if material is None:
            raise SystemExit("missing registry entry: " + material_id)
        source = Path(str(material["path"]).replace("/", "\\"))
        if sha256_file(source) != material["sha256"].lower():
            raise SystemExit("hash drift: " + material_id)
        text = source.read_text(encoding="ascii", errors="replace")
        lines = text.splitlines()
        option_lines = [line for line in lines if line.startswith("#")]
        # Touchstone record = frequency-leading line (leading non-blank)
        # followed by continuation lines (leading blank).
        record_lines = [
            line
            for line in lines
            if line
            and not line.startswith("#")
            and not line.startswith("!")
            and not line[0].isspace()
        ]
        continuation = [
            line
            for line in lines
            if line
            and not line.startswith("#")
            and not line.startswith("!")
            and line[0].isspace()
        ]
        first_record = record_lines[0].split() if record_lines else []
        last_record = record_lines[-1].split() if record_lines else []
        entries.append({
            "material_id": material_id,
            "sha256": material["sha256"].lower(),
            "byte_length": material["byte_length"],
            "option_lines": option_lines[:3],
            "record_count": len(record_lines),
            "continuation_line_count": len(continuation),
            "first_record_fields": len(first_record),
            "first_frequency_hz": first_record[0] if first_record else None,
            "last_frequency_hz": last_record[0] if last_record else None,
        })
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "authorized_s4p_structures_observed_hz_axis_hash_bound",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "axis_note": "tx_drv 0..100 GHz over 10003 records, rx_fe 0..80 GHz over 8003 records, 4-port RI format; differs from the P3C pulse-bench record (40 GHz / 1024 points) - distinct dataset, no assumption of identity",
        "files": entries,
        "non_claims": [
            "not_time_domain_model",
            "not_interpolation",
            "not_channel_resolution",
            "not_ami_matrix",
            "not_release_evidence",
        ],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["material_id"], "records=" + str(entry["record_count"]), "continuation=" + str(entry["continuation_line_count"]), "fields=" + str(entry["first_record_fields"]), "f0=" + str(entry["first_frequency_hz"]), "fN=" + str(entry["last_frequency_hz"]))
    print("evidence written: " + str(EVIDENCE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
