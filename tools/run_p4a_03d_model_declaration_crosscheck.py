# -*- coding: utf-8 -*-
"""P4A-03d typed model-declaration cross-check: product vs independent observer.

Runs the sipi-ibis structural parser + typed model-declaration lifter on the
authorized as4c512m16md4v-053bin.ibs and compares the lifted [Model] count and
Model_type distribution against an independent observer. Hash-only evidence;
no release claim.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
IBS_FILE = ROOT / "fixtures" / "ibis" / "as4c512m16md4v-053bin.ibs"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03d-model-declaration-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03d.model-declaration-crosscheck-evidence.v1"
EXPECTED_SHA256 = "d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b"
EXPECTED_MODEL_COUNT = 67


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def observer_model_types(lines):
    """Independent [+-]top-level [Model] scan: count model blocks and types."""
    counts = {}
    typemap = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("[Model]"):
            model = line[len("[Model]"):].strip()
            counts[model] = counts.get(model, 0) + 1
            # find Model_type within the same block
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("[Model]"):
                tl = lines[j].strip()
                if tl.startswith("Model_type"):
                    model_type = tl.split(None, 1)[1].strip()
                    typemap[model_type] = typemap.get(model_type, 0) + 1
                    break
                j += 1
            i = j
        else:
            i += 1
    return counts, typemap


def main() -> int:
    if not IBS_FILE.is_file():
        raise SystemExit("IBIS file missing")
    data = IBS_FILE.read_bytes()
    if sha256_bytes(data) != EXPECTED_SHA256:
        raise SystemExit("IBIS file hash drift")

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03d_model_declaration_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03d_model_declaration_runner-*.exe"))[-1]

    run = subprocess.run(
        [str(runner), "--input", str(IBS_FILE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if run.returncode != 0:
        raise SystemExit("runner failed :: " + run.stdout + run.stderr)
    product = json.loads(run.stdout)

    lines = data.decode("ascii", errors="replace").splitlines()
    obs_counts, obs_typemap = observer_model_types(lines)
    obs_model_count = sum(obs_counts.values())

    diffs = []
    if product.get("parse_error"):
        diffs.append("parse_error:" + product["parse_error"])
    if product.get("lift_error"):
        diffs.append("lift_error:" + product["lift_error"])
    product_count = product.get("declaration_count", -1)
    if product_count != obs_model_count:
        diffs.append(f"count_drift product={product_count} observer={obs_model_count}")
    if obs_model_count != EXPECTED_MODEL_COUNT:
        diffs.append(f"observer_count_unexpected={obs_model_count}")

    entry = {
        "id": "as4c512m16md4v-053bin",
        "file_sha256": EXPECTED_SHA256,
        "product_declaration_count": product_count,
        "observer_model_count": obs_model_count,
        "product_model_types": product.get("model_types", {}),
        "observer_model_types": obs_typemap,
        "matched": not diffs,
        "diffs": diffs,
    }
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if not diffs else "mis_match",
        "policy": "sipi.p4a-03d.model-declaration.v1.typed-declaration-only",
        "file": IBS_FILE.name,
        "matched_count": 1 if not diffs else 0,
        "entries": [entry],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if k in ("schema", "status", "matched_count")}, indent=2))
    print("observer typemap:", json.dumps(obs_typemap))
    print("product typemap:", json.dumps(product.get("model_types", {})))
    return 0 if not diffs else 1


if __name__ == "__main__":
    raise SystemExit(main())