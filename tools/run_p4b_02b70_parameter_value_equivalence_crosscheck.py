# -*- coding: utf-8 -*-
"""P4B-02b70 parameter value semantic equivalence cross-check (product vs independent ref).

Drives the product equivalence runner (p4b_02b70_parameter_value_equivalence_runner) over
validated (name, type, value) pairs. An independent Python reference replicates the typed
semantic comparison: cross-type never equivalent, Float/Integer on parsed values, Boolean
on exact True/False tokens, String on raw bytes, List on trimmed item sequences. Fail closed
on any mismatch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b70-parameter-value-equivalence-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b70-parameter-value-equivalence-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b70.parameter-value-equivalence-v1.typed-value-semantics"


def ref_list_items(value_token: str):
    if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
        return None
    inner = value_token[1:-1]
    if not inner:
        return None
    items = [item.strip() for item in inner.split(",")]
    if any(not item for item in items):
        return None
    return items


def ref_equivalent(left: dict[str, str], right: dict[str, str]) -> dict[str, Any]:
    """Return {equivalent, reason} under the typed semantic rules."""
    if left["type"] != right["type"]:
        return {"equivalent": False, "reason": "TypeMismatch"}
    t = left["type"]
    lv, rv = left["value"], right["value"]
    if t == "Float":
        try:
            lf, rf = float(lv), float(rv)
        except ValueError:
            return {"equivalent": False, "reason": "MalformedValue"}
        if lf == rf:
            return {"equivalent": True, "reason": None}
        return {"equivalent": False, "reason": "FloatMismatch"}
    if t == "Integer":
        try:
            li, ri = int(lv), int(rv)
        except ValueError:
            return {"equivalent": False, "reason": "MalformedValue"}
        if li == ri:
            return {"equivalent": True, "reason": None}
        return {"equivalent": False, "reason": "IntegerMismatch"}
    if t == "Boolean":
        if lv == rv:
            return {"equivalent": True, "reason": None}
        return {"equivalent": False, "reason": "BooleanMismatch"}
    if t == "String":
        if lv == rv:
            return {"equivalent": True, "reason": None}
        return {"equivalent": False, "reason": "StringMismatch"}
    if t == "List":
        li = ref_list_items(lv)
        ri = ref_list_items(rv)
        if li is None or ri is None:
            return {"equivalent": False, "reason": "MalformedValue"}
        if len(li) != len(ri):
            return {"equivalent": False, "reason": "ListLengthMismatch"}
        for index, (a, b) in enumerate(zip(li, ri)):
            if a != b:
                return {"equivalent": False, "reason": "ListItemMismatch"}
        return {"equivalent": True, "reason": None}
    return {"equivalent": False, "reason": "MalformedValue"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b70_parameter_value_equivalence_runner"

    cases = [
        {
            "label": "float_spelling",
            "left": {"name": "gain", "type": "Float", "value": "0.5"},
            "right": {"name": "gain", "type": "Float", "value": "0.50"},
        },
        {
            "label": "integer_spelling",
            "left": {"name": "steps", "type": "Integer", "value": "007"},
            "right": {"name": "steps", "type": "Integer", "value": "7"},
        },
        {
            "label": "list_spacing",
            "left": {"name": "channels", "type": "List", "value": "(a, b, c)"},
            "right": {"name": "channels", "type": "List", "value": "(a,b,c)"},
        },
        {
            "label": "cross_type",
            "left": {"name": "x", "type": "Float", "value": "1.0"},
            "right": {"name": "x", "type": "Integer", "value": "1"},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b70-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / (case["label"] + "_in.json")
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / (case["label"] + "_rep.json")
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case["label"]}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_equivalent(case["left"], case["right"])

            matched = (product.get("valid") is True
                       and product.get("equivalent") == reference.get("equivalent")
                       and product.get("reason") == reference.get("reason"))
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
        "status": "product_owned_self_crosscheck_unbound" if ok_all else "mis_match",
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
