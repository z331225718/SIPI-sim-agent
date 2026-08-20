"""P5-06c external-only normalized-input surface parser.

Reads the authorized 120g C2M TP1a config sheet (COM_Settings) and
cross-references every canonical R480 parameter key (P5-02h v2)
against the config values, recording case-resolved inputs and the
port-order fact. Hash-bound; no comparison or product derivation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import openpyxl
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
CANONICAL = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
SURFACE = ROOT / "docs" / "baselines" / "p5-06-normalized-input-surface.v1.yaml"
SURFACE_SCHEMA = "sipi.p5-06.normalized-input-surface.v1"
CONFIG_ID = "com-r480-config-120g-c2m"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    material = next((m for m in registry["materials"] if m["id"] == CONFIG_ID), None)
    if material is None:
        raise SystemExit("config not registered")
    config_path = Path(str(material["path"]).replace("/", "\\"))
    if sha256_file(config_path) != material["sha256"].lower():
        raise SystemExit("config hash drift")
    canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
    workbook = openpyxl.load_workbook(config_path, read_only=True, data_only=True)
    sheet = workbook["COM_Settings"]
    config_values = {}
    port_order = None
    rows = list(sheet.iter_rows(values_only=True))
    block_starts = set()
    for row in rows[:3]:
        for index, cell in enumerate(row):
            if isinstance(cell, str) and cell.strip() in ("Parameter", "I/O control"):
                block_starts.add(index)
    for row in rows:
        for start in block_starts:
            key = row[start] if start < len(row) else None
            value = row[start + 1] if start + 1 < len(row) else None
            if isinstance(key, str) and key.strip():
                stripped = key.strip()
                if value is not None:
                    config_values.setdefault(stripped, []).append(value)
                if stripped == "Port Order" and isinstance(value, str):
                    port_order = value.strip()
    keys_out = {}
    matched = 0
    for key in canonical["keys"]:
        if key in config_values:
            keys_out[key] = {"config_value": config_values[key][0], "in_config": True}
            matched += 1
        else:
            keys_out[key] = {"in_config": False}
    surface = {
        "schema": SURFACE_SCHEMA,
        "status": "normalized_input_surface_observed_hash_bound",
        "config_ref": "docs/baselines/authorized-material-registry.v1.yaml#com-r480-config-120g-c2m",
        "config_sha256": material["sha256"].lower(),
        "canonical_ref": "docs/baselines/p5-r480-canonical-parameter-json.v2.yaml",
        "canonical_keys": len(keys_out),
        "keys_in_config": matched,
        "port_order_observed": port_order,
        "keys": keys_out,
        "non_claims": [
            "not_a_compare",
            "not_default_resolution",
            "not_warnings_contract",
            "not_release_evidence",
        ],
    }
    SURFACE.write_text(yaml.safe_dump(surface, sort_keys=False), encoding="utf-8")
    print("canonical keys: " + str(len(keys_out)) + " in config: " + str(matched) + " port_order: " + str(port_order))
    print("surface written: " + str(SURFACE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
