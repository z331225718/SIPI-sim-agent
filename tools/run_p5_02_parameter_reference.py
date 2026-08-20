"""P5-02 external-only canonical parameter reference generator.

Observes the owner-authorized MATLAB r4.80 source (com_ieee8023_480.m)
for xls_parameter(parameter, 'KEY', ...) call sites and records the
canonical key inventory with call-line originals (default expressions
included verbatim) as a hash-bound oracle reference. This is external
custody observation tooling, not product code; nothing is copied into
the product tree. The reference is the basis for the P5-02 canonical
parameter JSON contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "authorized-material-registry.v1.yaml"
REFERENCE = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-reference.v1.yaml"
REFERENCE_SCHEMA = "sipi.p5-02.canonical-parameter-reference.v1"
MATLAB_ID = "com-r480-matlab-source"
CALL_RE = re.compile(r"xls_parameter\s*\(([^)]*)\)")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    material = next((m for m in registry["materials"] if m["id"] == MATLAB_ID), None)
    if material is None:
        raise SystemExit("matlab source not registered")
    source = Path(str(material["path"]).replace("/", "\\"))
    expected = material["sha256"].lower()
    actual = sha256_file(source)
    if actual != expected:
        raise SystemExit(f"source hash drift: {actual} != {expected}")
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    keys = {}
    for line_number, line in enumerate(lines, 1):
        for match in CALL_RE.finditer(line):
            arguments = match.group(1)
            key_match = re.search(r"'([^']+)'", arguments)
            if key_match is None:
                continue
            key = key_match.group(1)
            entry = keys.setdefault(key, {"lines": [], "call_texts": []})
            entry["lines"].append(line_number)
            entry["call_texts"].append(line.strip())
    keys_sorted = {key: keys[key] for key in sorted(keys, key=str.casefold)}
    call_count = sum(len(entry["call_texts"]) for entry in keys_sorted.values())
    reference = {
        "schema": REFERENCE_SCHEMA,
        "status": "canonical_parameter_keys_observed_hash_bound",
        "authorization_ref": "docs/baselines/authorized-material-registry.v1.yaml",
        "source": str(source),
        "source_sha256": actual,
        "byte_length": source.stat().st_size,
        "key_count": len(keys_sorted),
        "call_count": call_count,
        "keys": {
            key: {"occurrences": len(entry["lines"]), "lines": entry["lines"], "call_texts": entry["call_texts"]}
            for key, entry in keys_sorted.items()
        },
        "non_claims": [
            "not_a_product_contract",
            "not_parameter_defaults_resolved",
            "not_warning_contract",
            "not_compute_parity",
            "not_release_evidence",
        ],
    }
    REFERENCE.write_text(yaml.safe_dump(reference, sort_keys=False), encoding="utf-8")
    print(f"keys={len(keys_sorted)} calls={call_count}")
    print(f"reference written: {REFERENCE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
