# -*- coding: utf-8 -*-
"""P4A-03e pin-declaration cross-check: product vs independent observer."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
IBS_FILE = ROOT / "fixtures" / "ibis" / "as4c512m16md4v-053bin.ibs"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03e-pin-declaration-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03e.pin-declaration-crosscheck-evidence.v1"
EXPECTED_SHA256 = "d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b"

import hashlib

def observer_pins(text):
    lines = text.splitlines()
    pins = []
    in_pin = False
    for line in lines:
        s = line.strip()
        if s.startswith('[Pin]'): in_pin = True; continue
        if s.startswith('[') and in_pin: break
        if in_pin and s and not s.startswith('|'):
            parts = s.split()
            if len(parts) >= 3:
                pins.append({'pin': parts[0], 'signal': parts[1], 'model': parts[2]})
    return pins

def main() -> int:
    data = IBS_FILE.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        raise SystemExit('IBIS file hash drift')
    text = data.decode('ascii', errors='replace')
    obs = observer_pins(text)

    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03e_pin_declaration_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit('runner build failed: ' + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03e_pin_declaration_runner-*.exe"))[-1]
    run = subprocess.run([str(runner), "--input", str(IBS_FILE)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode != 0: raise SystemExit('runner failed :: ' + run.stdout + run.stderr)
    product = json.loads(run.stdout)

    diffs = []; matched = True
    if product.get("pin_count", -1) != len(obs):
        diffs.append(f"count_drift product={product.get('pin_count')} observer={len(obs)}"); matched = False
    sample = product.get("sample", [])
    for idx, s in enumerate(sample):
        ref = obs[idx]
        if s.get("pin") != ref["pin"] or s.get("signal") != ref["signal"] or s.get("model") != ref["model"]:
            diffs.append(f"sample_drift@{idx}"); matched = False; break

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if matched else "mis_match",
        "policy": "sipi.p4a-03e.pin-declaration.v1.typed",
        "file": IBS_FILE.name,
        "file_sha256": EXPECTED_SHA256,
        "product_pin_count": product.get("pin_count"),
        "observer_pin_count": len(obs),
        "product_sample": sample,
        "observer_sample": obs[:5],
        "matched": matched,
        "diffs": diffs,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "product_pin_count": product.get("pin_count"), "observer_pin_count": len(obs), "matched": matched}, indent=2))
    return 0 if matched else 1

if __name__ == "__main__":
    raise SystemExit(main())