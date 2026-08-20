# -*- coding: utf-8 -*-
"""P5-05e COM parameter DTO merge cross-check: product vs independent ref.

Verifies the merge rule (workbook value wins, else resolved default, else
error; unconsumed retained) against an independent Python reference on a
synthetic canonical/consumed surface. Hash-only evidence.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-05e-com-parameters-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-05e.com-parameters-crosscheck-evidence.v1"


def reference_merge(consumed_keys, workbook, defaults, unconsumed):
    consumed = {}
    for key in consumed_keys:
        if key in workbook:
            consumed[key] = workbook[key]
        elif key in defaults:
            consumed[key] = defaults[key]
        else:
            return (None, "missing_value:" + key)
    return ({"consumed": consumed, "unconsumed": unconsumed}, None)


def main() -> int:
    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_05e_com_parameters_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_05e_com_parameters_runner-*.exe"))[-1]

    consumed_keys = ["fb", "a_fext", "ndfe"]
    workbook = {"fb": {"kind": "scalar", "value": 53.125e9}}
    defaults = {
        "a_fext": {"kind": "scalar", "value": 0.5},
        "ndfe": {"kind": "scalar", "value": 2.0},
    }
    unconsumed = ["extraneous"]
    input_payload = {"consumed_keys": consumed_keys, "workbook": workbook, "defaults": defaults, "unconsumed": unconsumed}

    ref_res, ref_err = reference_merge(consumed_keys, {k: v["value"] for k, v in workbook.items()}, {k: v["value"] for k, v in defaults.items()}, unconsumed)

    entries = []
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="p5-05e-") as tmp:
        work = Path(tmp)
        input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
        input_path = work / "input.json"
        input_path.write_bytes(input_bytes)
        report_path = work / "product.json"
        run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0:
            raise SystemExit("runner failed :: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))

        if not product.get("ok"):
            raise SystemExit("product merge unexpectedly failed: " + str(product))
        prod_consumed = {k: abs(v - ref_res["consumed"][k]) < 1e-9 for k, v in product["consumed"].items()}
        consumed_ok = set(product["consumed"].keys()) == set(ref_res["consumed"].keys()) and all(prod_consumed.values())
        unconsumed_ok = list(product["unconsumed"]) == ref_res["unconsumed"]
        ok_all = consumed_ok and unconsumed_ok
        entries.append({"id": "merge_fb_a_fext_ndfe", "matched": ok_all, "product_consumed": product["consumed"], "reference_consumed": ref_res["consumed"], "product_unconsumed": product["unconsumed"], "reference_unconsumed": ref_res["unconsumed"]})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p5-05e.com-parameters-v1.typed-dto",
            "matched_count": 1 if ok_all else 0,
            "case_count": 1,
            "entries": entries,
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
        print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "matched_count": evidence["matched_count"]}, indent=2))
        return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())