# -*- coding: utf-8 -*-
"""P4A-03l typed IBIS submodel & add submodel cross-check (product vs independent ref).

Drives the product submodel runner (p4a_03l_submodel_runner) over valid and invalid
submodel/add-submodel inputs. An independent Python reference recomputes the lifting rules.
Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03l-submodel-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03l.submodel-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03l.submodel-declaration-v1.typed-submodel"

SUBMODEL_TYPES = {"Dynamic_clamp", "Bus_hold", "Fall_clamp", "Rise_clamp"}
SUBMODEL_MODES = {"Driving", "Non-Driving", "All"}


def ref_lift_submodel(name: str, stype: str, mode: str) -> dict[str, Any]:
    if not name or not name.strip():
        return {"valid": False, "lift_error": "EmptyName"}
    trimmed = name.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    stype_clean = stype.strip()
    if stype_clean not in SUBMODEL_TYPES:
        return {"valid": False, "lift_error": f'UnknownSubmodelType("{stype_clean}")'}
    mode_clean = mode.strip()
    if mode_clean not in SUBMODEL_MODES:
        return {"valid": False, "lift_error": f'UnknownSubmodelMode("{mode_clean}")'}
    return {
        "valid": True,
        "kind": "submodel",
        "submodel_name": trimmed,
        "submodel_type": stype_clean,
        "mode": mode_clean,
    }


def ref_lift_add_submodel(name: str, mode: str) -> dict[str, Any]:
    if not name or not name.strip():
        return {"valid": False, "lift_error": "EmptyName"}
    trimmed = name.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    mode_clean = mode.strip()
    if mode_clean not in SUBMODEL_MODES:
        return {"valid": False, "lift_error": f'UnknownSubmodelMode("{mode_clean}")'}
    return {
        "valid": True,
        "kind": "add_submodel",
        "submodel_name": trimmed,
        "mode": mode_clean,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03l_submodel_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03l_submodel_runner-*.exe"))[-1]

    cases = [
        {
            "label": "submodel_declaration",
            "submodel_name": "SUB_CLAMP",
            "submodel_type": "Dynamic_clamp",
            "mode": "Driving",
        },
        {
            "label": "add_submodel",
            "submodel_name": "SUB_HOLD",
            "mode": "Non-Driving",
        },
        {
            "label": "unknown_submodel_type",
            "submodel_name": "SUB",
            "submodel_type": "UnknownType",
            "mode": "All",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03l-") as tmp:
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

            if "submodel_type" in case:
                reference = ref_lift_submodel(case["submodel_name"], case["submodel_type"], case["mode"])
            else:
                reference = ref_lift_add_submodel(case["submodel_name"], case["mode"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if product.get("kind") != reference["kind"]:
                    matched = False
                if reference["kind"] == "submodel":
                    if (product.get("submodel_name") != reference["submodel_name"] or
                        product.get("submodel_type") != reference["submodel_type"] or
                        product.get("mode") != reference["mode"]):
                        matched = False
                else:
                    if (product.get("submodel_name") != reference["submodel_name"] or
                        product.get("mode") != reference["mode"]):
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
