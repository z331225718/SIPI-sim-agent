# -*- coding: utf-8 -*-
"""P4A-03t typed IBIS bus label cross-check (product vs independent ref).

Drives the product bus label runner (p4a_03t_bus_label_runner) over valid
and invalid bus label inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03t-bus-label-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03t.bus-label-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03t.bus-label-declaration-v1.typed-bus-label"


def ref_lift_bus_label(bname: str, pins: list[str]) -> dict[str, Any]:
    if not bname or not bname.strip():
        return {"valid": False, "lift_error": "EmptyBusLabelName"}
    b_trimmed = bname.strip()
    if not b_trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in b_trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    if not pins:
        return {"valid": False, "lift_error": "EmptyMemberPins"}

    seen = set()
    clean_pins = []
    for p in pins:
        pt = p.strip()
        if not pt:
            return {"valid": False, "lift_error": "EmptyBusLabelName"}
        if not pt.isascii():
            return {"valid": False, "lift_error": "NonAsciiName"}
        if not all(c.isalnum() or c in "_-." for c in pt):
            return {"valid": False, "lift_error": "InvalidName"}
        if pt in seen:
            return {"valid": False, "lift_error": f'DuplicateMemberPin("{pt}")'}
        seen.add(pt)
        clean_pins.append(pt)

    return {
        "valid": True,
        "bus_label_name": b_trimmed,
        "member_pins": clean_pins,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03t_bus_label_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03t_bus_label_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_bus_label",
            "bus_label_name": "DQ_BUS",
            "member_pins": ["DQ0", "DQ1", "DQ2"],
        },
        {
            "label": "empty_member_pins",
            "bus_label_name": "DQ_BUS",
            "member_pins": [],
        },
        {
            "label": "duplicate_member_pin",
            "bus_label_name": "DQ_BUS",
            "member_pins": ["DQ0", "DQ0"],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03t-") as tmp:
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
            reference = ref_lift_bus_label(case["bus_label_name"], case["member_pins"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("bus_label_name") != reference["bus_label_name"] or
                    product.get("member_pins") != reference["member_pins"]):
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
