# -*- coding: utf-8 -*-
"""P4B-02b191 parameter list pairwise-equal adjacent pairs cross-check (product vs ref).

Drives the product pairwise-equal-adjacent runner over one validated list value.
An independent Python reference replicates the rule: the list trims items and
returns the (item[i], item[i+1]) pairs for every adjacent index with equal
trimmed items, in list order, keeping duplicates (raw byte equality);
non-List values fail closed.  Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b191-parameter-list-pairwise-equal-adjacent-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b191-parameter-list-pairwise-equal-adjacent-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b191.parameter-list-pairwise-equal-adjacent-v1.pairwise-equal-adjacent"


def ref_pairwise_equal_adjacent(type_token: str, value_token: str) -> dict:
    if type_token != "List":
        return {"valid": False, "error": "NotAList"}
    if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
        return {"valid": False, "error": "MalformedList"}
    inner = value_token[1:-1]
    if not inner:
        return {"valid": False, "error": "MalformedList"}
    raw_items = inner.split(",")
    if any(not item_part.strip() for item_part in raw_items):
        return {"valid": False, "error": "MalformedList"}
    items = [item_part.strip() for item_part in raw_items]
    pairs = []
    for i in range(len(items) - 1):
        if items[i] == items[i + 1]:
            pairs.append([items[i], items[i + 1]])
    return {"valid": True, "pairwise_equal_adjacent": pairs}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b191_parameter_list_pairwise_equal_adjacent_runner"

    cases = [
        {"label": "mixed", "name": "channels", "type": "List", "value": "(a, b, b, c, a)"},
        {"label": "runs", "name": "param", "type": "List", "value": "(a, a, b, b, b)"},
        {"label": "all_equal", "name": "param", "type": "List", "value": "(x, x, x)"},
        {"label": "non_list", "name": "gain", "type": "Float", "value": "0.5"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b191-") as tmp:
        work = Path(tmp)
        for case in cases:
            ami = {"name": case["name"], "type": case["type"], "value": case["value"]}
            input_path = work / (case["label"] + "_in.json")
            input_path.write_text(json.dumps(ami), encoding="utf-8")
            report_path = work / (case["label"] + "_rep.json")
            run = subprocess.run([str(runner), "--input", str(input_path),
                                  "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_pairwise_equal_adjacent(case["type"], case["value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("pairwise_equal_adjacent") == reference.get("pairwise_equal_adjacent")
                       and product.get("error") == reference.get("error"))
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
    text = yaml.safe_dump(evidence, sort_keys=False).replace("\n", "\r\n")
    EVIDENCE.write_bytes(text.encode("utf-8"))
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"],
                      "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
