# -*- coding: utf-8 -*-
"""P4B-02b61 AMI text form heads cross-check (product vs independent ref).

Drives the product form heads runner (p4b_02b61_ami_text_form_heads_runner) over parenthesized
AMI text inputs. An independent Python reference replicates the tokenize and the head counting.
Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b61-ami-text-form-heads-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b61-ami-text-form-heads-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b61.ami-text-form-heads-v1.head-counts"


def ref_heads(text: str) -> dict[str, Any]:
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens:
        return {"valid": False, "parse_error": "EmptyDocument"}

    def parse_list(idx: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        idx += 1
        while idx < len(tokens):
            if tokens[idx] == ')':
                return items, idx + 1
            elif tokens[idx] == '(':
                sub, idx = parse_list(idx)
                items.append(sub)
            else:
                items.append(tokens[idx])
                idx += 1
        return items, idx

    if tokens[0] != '(':
        return {"valid": False, "parse_error": "EmptyDocument"}
    idx = 0
    forms: list[list[Any]] = []
    while idx < len(tokens):
        if tokens[idx] == ')':
            idx += 1
            continue
        form, idx = parse_list(idx)
        forms.append(form)

    heads: dict[str, int] = {}
    for form in forms:
        if not form:
            return {"valid": False, "heads_error": "InvalidFormHead"}
        first = form[0]
        if isinstance(first, list):
            return {"valid": False, "heads_error": "InvalidFormHead"}
        heads[first] = heads.get(first, 0) + 1
    if not heads:
        return {"valid": False, "heads_error": "EmptyDocument"}
    return {"valid": True, "heads": heads}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b61_ami_text_form_heads_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b61_ami_text_form_heads_runner-*.exe"))[-1]

    cases = [
        {"label": "repeated_heads", "text": "(a 1) (b 2) (a 3)"},
        {"label": "single_form", "text": "(root (x 1))"},
        {"label": "nested_list_head", "text": "((a) 1)"},
        {"label": "empty_text", "text": ""},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b61-") as tmp:
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
            reference = ref_heads(case["text"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if product.get("heads") != reference.get("heads"):
                    matched = False
            else:
                prod_err = (product.get("heads_error") or product.get("parse_error"))
                ref_err = (reference.get("heads_error") or reference.get("parse_error"))
                if str(prod_err) != str(ref_err):
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
