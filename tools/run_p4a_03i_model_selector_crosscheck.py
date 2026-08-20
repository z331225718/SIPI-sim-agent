# -*- coding: utf-8 -*-
"""P4A-03i typed IBIS model selector & series pin mapping cross-check (product vs ref).

Drives the product model selector runner (p4a_03i_model_selector_runner) over valid
and invalid selector/series-pin inputs. An independent Python reference recomputes
the lifting rules. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03i-model-selector-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03i.model-selector-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03i.model-selector-declaration-v1.typed-selector-series"


def ref_lift_selector(name: str, branches: list[dict[str, Any]]) -> dict[str, Any]:
    if not name or not name.strip():
        return {"valid": False, "lift_error": "EmptyName"}
    trimmed = name.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    if not branches:
        return {"valid": False, "lift_error": "EmptyBranches"}
    for b in branches:
        mn = b.get("model_name", "").strip()
        if not mn:
            return {"valid": False, "lift_error": "EmptyName"}
        if not mn.isascii():
            return {"valid": False, "lift_error": "NonAsciiName"}
    return {
        "valid": True,
        "kind": "selector",
        "selector_name": trimmed,
        "branch_count": len(branches),
    }


def ref_lift_series_pin(pf: str, ps: str, mn: str) -> dict[str, Any]:
    pf, ps, mn = pf.strip(), ps.strip(), mn.strip()
    if not pf or not ps or not mn:
        return {"valid": False, "lift_error": "EmptyName"}
    if not pf.isascii() or not ps.isascii() or not mn.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if pf == ps:
        return {"valid": False, "lift_error": "IdenticalSeriesPins"}
    return {
        "valid": True,
        "kind": "series_pin_mapping",
        "pin_first": pf,
        "pin_second": ps,
        "model_name": mn,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03i_model_selector_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03i_model_selector_runner-*.exe"))[-1]

    cases = [
        {
            "label": "model_selector",
            "selector_name": "SPEED_SEL",
            "branches": [
                {"model_name": "MODE_FAST", "description": "Fast corner"},
                {"model_name": "MODE_SLOW", "description": "Slow corner"},
            ],
        },
        {
            "label": "series_pin_mapping",
            "pin_first": "A1",
            "pin_second": "A2",
            "model_name": "R_SERIES_50",
        },
        {
            "label": "identical_series_pins",
            "pin_first": "A1",
            "pin_second": "A1",
            "model_name": "R_SERIES_50",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03i-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.json"
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))

            if "selector_name" in case:
                reference = ref_lift_selector(case["selector_name"], case["branches"])
            else:
                reference = ref_lift_series_pin(case["pin_first"], case["pin_second"], case["model_name"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if product.get("kind") != reference["kind"]:
                    matched = False
                if reference["kind"] == "selector":
                    if (product.get("selector_name") != reference["selector_name"] or
                        product.get("branch_count") != reference["branch_count"]):
                        matched = False
                else:
                    if (product.get("pin_first") != reference["pin_first"] or
                        product.get("pin_second") != reference["pin_second"] or
                        product.get("model_name") != reference["model_name"]):
                        matched = False
            else:
                if str(product.get("lift_error")) != str(reference.get("lift_error")):
                    matched = False

            if not matched:
                ok_all = False

            entries.append({
                "label": case["label"],
                "matched": matched,
                "product": product,
                "reference": reference,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": POLICY,
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
