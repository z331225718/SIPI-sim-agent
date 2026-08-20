# -*- coding: utf-8 -*-
"""P4A-03v typed IBIS series pin group cross-check (product vs independent ref).

Drives the product series pin group runner (p4a_03v_series_pin_group_runner) over valid
and invalid series pin group inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03v-series-pin-group-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03v.series-pin-group-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03v.series-pin-mapping-group-v1.typed-group"


def ref_lift_series_pin_group(gname: str, pin_pairs: list[dict[str, str]]) -> dict[str, Any]:
    if not gname or not gname.strip():
        return {"valid": False, "lift_error": "EmptyGroupName"}
    g_trimmed = gname.strip()
    if not g_trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in g_trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    if not pin_pairs:
        return {"valid": False, "lift_error": "EmptyPinPairs"}

    seen = set()
    clean_pairs = []
    for pair in pin_pairs:
        p1 = pair.get("pin_first", "").strip()
        p2 = pair.get("pin_second", "").strip()
        if not p1 or not p2:
            return {"valid": False, "lift_error": "EmptyGroupName"}
        if not p1.isascii() or not p2.isascii():
            return {"valid": False, "lift_error": "NonAsciiName"}
        if not all(c.isalnum() or c in "_-." for c in p1) or not all(c.isalnum() or c in "_-." for c in p2):
            return {"valid": False, "lift_error": "InvalidName"}
        if p1 == p2:
            return {"valid": False, "lift_error": f'IdenticalPinPair("{p1}")'}
        pair_key = (p1, p2)
        if pair_key in seen:
            return {"valid": False, "lift_error": f'DuplicatePinPair("{p1}", "{p2}")'}
        seen.add(pair_key)
        clean_pairs.append({"pin_first": p1, "pin_second": p2})

    return {
        "valid": True,
        "group_name": g_trimmed,
        "pin_pair_count": len(clean_pairs),
        "pin_pairs": clean_pairs,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03v_series_pin_group_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03v_series_pin_group_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_group_declaration",
            "group_name": "SERIES_GRP1",
            "pin_pairs": [
                {"pin_first": "P1", "pin_second": "P2"},
                {"pin_first": "P3", "pin_second": "P4"},
            ],
        },
        {
            "label": "empty_pin_pairs",
            "group_name": "GRP1",
            "pin_pairs": [],
        },
        {
            "label": "duplicate_pin_pair",
            "group_name": "GRP1",
            "pin_pairs": [
                {"pin_first": "P1", "pin_second": "P2"},
                {"pin_first": "P1", "pin_second": "P2"},
            ],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03v-") as tmp:
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
            reference = ref_lift_series_pin_group(case["group_name"], case["pin_pairs"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("group_name") != reference["group_name"] or
                    product.get("pin_pair_count") != reference["pin_pair_count"] or
                    product.get("pin_pairs") != reference["pin_pairs"]):
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
