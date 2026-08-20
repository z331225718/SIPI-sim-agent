# -*- coding: utf-8 -*-
"""P3C-03 C4 metric-profile cross-check: product vs independent ref.

Freezes the owner C4 COM metric profile (COM_dB / ICN_mV / ERL with 1%
relative tolerance). Given a caller-supplied finite reference map, both the
product (c4_metric_specs_v1 via the runner binary) and the independent
reference build the same profile specs and a profile digest over the metric
names. Fail closed: a missing or non-finite reference for any C4 metric is an
error on both sides.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-04x-c4-profile-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-04x.c4-profile-crosscheck-evidence.v1"
C4_METRICS = [("COM_dB", "db"), ("ICN_mV", "mv"), ("ERL", "db")]
REL = 0.01


def reference_c4(references: dict[str, float]) -> dict[str, Any]:
    """Independent reference: build the C4 profile specs + digest."""
    specs = []
    for name, _unit in C4_METRICS:
        if name not in references:
            return {"ok": False, "error": f"missing_reference:{name}"}
        value = references[name]
        try:
            valuef = float(value)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"non_finite_reference:{name}"}
        if valuef != valuef or valuef in (float("inf"), float("-inf")):
            return {"ok": False, "error": f"non_finite_reference:{name}"}
        specs.append({"name": name, "reference": valuef, "relative_tolerance": REL})
    # specs preserve C4 order
    hasher = hashlib.sha256()
    for s in specs:
        hasher.update(s["name"].encode("utf-8"))
        hasher.update(b"\n")
    return {"ok": True, "error": None,
            "metric_names": [n for n, _ in C4_METRICS],
            "relative_tolerance": REL,
            "specs": specs,
            "digest": hasher.hexdigest()}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-compare", "--test", "p3c_04x_c4_profile_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_04x_c4_profile_runner-*.exe"))[-1]

    cases = [
        {"label": "full_references", "refs": {"COM_dB": 3.5, "ICN_mV": 12.0, "ERL": 8.0}},
        {"label": "realistic_values", "refs": {"COM_dB": 3.8, "ICN_mV": 5.2, "ERL": 6.5}},
        {"label": "missing_erl", "refs": {"COM_dB": 3.5, "ICN_mV": 12.0}},
        {"label": "missing_icn", "refs": {"COM_dB": 3.5, "ERL": 8.0}},
        {"label": "single_metric_only_erl", "refs": {"COM_dB": 3.5, "ICN_mV": 12.0, "ERL": 9.0}},
        {"label": "empty", "refs": {}},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p3c-c4-") as tmp:
        work = Path(tmp)
        for case in cases:
            label = case["label"]
            payload = dict(case["refs"])
            input_path = work / "input.json"
            input_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            report_path = work / "product.json"
            r = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0: raise SystemExit("runner failed :: " + r.stdout + r.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))

            prod_ok = bool(product.get("ok"))
            prod_err = product.get("error")
            prod_names = product.get("metric_names") or []
            prod_specs = product.get("specs") or []
            prod_digest = product.get("digest")

            ref = reference_c4(case["refs"])
            ref_ok = bool(ref["ok"])
            ref_err = ref.get("error")
            ref_specs = ref.get("specs") or []
            ref_digest = ref.get("digest")
            ref_names = ref.get("metric_names") or []

            mismatched = (prod_ok != ref_ok or prod_err != ref_err
                          or (prod_specs != ref_specs if prod_ok else False)
                          or (prod_digest != ref_digest if prod_ok else False)
                          or (prod_names != ref_names if prod_ok else False))
            if mismatched: ok_all = False
            entries.append({
                "label": label, "matched": not mismatched,
                "product_ok": prod_ok, "reference_ok": ref_ok,
                "product_error": prod_err, "reference_error": ref_err,
                "product_specs": prod_specs, "reference_specs": ref_specs if ref_ok else [],
                "product_digest": prod_digest, "reference_digest": ref_digest,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct",
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())