# -*- coding: utf-8 -*-
"""P4B-02b51 AMI text document statistics cross-check (product vs independent ref).

Drives the product document stats runner (p4b_02b51_ami_text_document_stats_runner) over
parenthesized AMI text inputs. An independent Python reference replicates the tokenize and the
structural counting. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b51-ami-text-document-stats-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b51-ami-text-document-stats-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b51.ami-text-document-stats-v1.ast-structure-stats"


def ref_stats(text: str) -> dict[str, Any]:
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens:
        return {"valid": False, "parse_error": "EmptyDocument"}

    list_count = 0
    atom_count = 0
    quoted_count = 0
    max_depth = 0

    def parse_list(idx: int, depth: int) -> tuple[int, int]:
        nonlocal list_count, atom_count, quoted_count, max_depth
        list_count += 1
        if depth > max_depth:
            max_depth = depth
        idx += 1
        while idx < len(tokens):
            if tokens[idx] == ')':
                return idx, idx + 1
            elif tokens[idx] == '(':
                idx, _ = parse_list(idx, depth + 1)
            else:
                if tokens[idx].startswith('"'):
                    quoted_count += 1
                else:
                    atom_count += 1
                idx += 1
        return idx, idx

    if tokens[0] != '(':
        return {"valid": False, "parse_error": "EmptyDocument"}
    idx = 0
    while idx < len(tokens):
        if tokens[idx] == chr(41):
            idx += 1
            continue
        _, idx = parse_list(idx, 1)
    return {"valid": True, "list_count": list_count, "atom_count": atom_count,
            "quoted_count": quoted_count, "max_depth": max_depth}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b51_ami_text_document_stats_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b51_ami_text_document_stats_runner-*.exe"))[-1]

    cases = [
        {
            "label": "mixed",
            "text": "(a b (c \"d\" e))",
        },
        {
            "label": "two_forms",
            "text": "(x 1) (y 2)",
        },
        {
            "label": "deep_nesting",
            "text": "(a (b (c (d 1))))",
        },
        {
            "label": "empty_text",
            "text": "",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b51-") as tmp:
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
            reference = ref_stats(case["text"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("list_count") != reference.get("list_count") or
                    product.get("atom_count") != reference.get("atom_count") or
                    product.get("quoted_count") != reference.get("quoted_count") or
                    product.get("max_depth") != reference.get("max_depth")):
                    matched = False
            else:
                prod_err = (product.get("stats_error") or product.get("parse_error"))
                ref_err = reference.get("parse_error")
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
