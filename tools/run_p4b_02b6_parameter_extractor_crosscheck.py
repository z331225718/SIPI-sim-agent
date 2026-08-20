# -*- coding: utf-8 -*-
"""P4B-02b6 AMI text document parameter extractor cross-check (product vs independent ref).

Drives the product parameter extractor runner (p4b_02b6_parameter_extractor_runner)
over parenthesized AMI text inputs. An independent Python reference parses the AST
and extracts triples. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b6-parameter-extractor-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b6.parameter-extractor-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b6.parameter-extractor-v1.ast-triples-to-values"
TYPES = {"Float", "Integer", "Boolean", "String", "List"}


def ref_validate_val(ty: str, val: str) -> str | None:
    if ty == "Float":
        try:
            v = float(val)
            if not math.isfinite(v): return "InvalidValue"
        except ValueError:
            return "InvalidValue"
    elif ty == "Integer":
        try:
            int(val)
        except ValueError:
            return "InvalidValue"
    elif ty == "Boolean":
        if val not in ("True", "False"): return "InvalidValue"
    elif ty == "String":
        if not val.strip(): return "InvalidValue"
    elif ty == "List":
        if not (val.startswith("(") and val.endswith(")")): return "InvalidValue"
    return None


import math

def ref_extract_parameters(text: str) -> dict[str, Any]:
    # Simple parenthesized AST scanner for crosscheck
    # Replace comments
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens:
        return {"valid": False, "extract_error": "EmptyDocument"}

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
        return {"valid": False, "extract_error": "NoValidParameters"}
    ast, _ = parse_list(0)
    params: dict[str, Any] = {}

    def scan(node: Any) -> str | None:
        if isinstance(node, list):
            if len(node) == 3 and isinstance(node[0], str) and isinstance(node[1], str) and isinstance(node[2], str):
                name, ty, val = node[0], node[1], node[2]
                if ty in TYPES:
                    err = ref_validate_val(ty, val)
                    if err:
                        return f'InvalidValue({err})'
                    if name in params:
                        return f'DuplicateParameter("{name}")'
                    params[name] = {"type": ty, "value_token": val}
                    return None
            for item in node:
                err = scan(item)
                if err:
                    return err
        return None

    err = scan(ast)
    if err:
        return {"valid": False, "extract_error": err}
    if not params:
        return {"valid": False, "extract_error": "NoValidParameters"}
    # Sort params by name for comparison
    sorted_params = {k: params[k] for k in sorted(params.keys())}
    return {"valid": True, "parameter_count": len(sorted_params), "parameters": sorted_params}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b6_parameter_extractor_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b6_parameter_extractor_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_three_params",
            "text": '(root (swing Float 0.5) (tap Integer 2) (flag Boolean True))',
        },
        {
            "label": "nested_document",
            "text": '(root (sub (alpha Float 1.25) (beta Integer -4)))',
        },
        {
            "label": "duplicate_parameter",
            "text": '(root (swing Float 0.5) (swing Float 0.9))',
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b6-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.txt"
            input_path.write_bytes(case["text"].encode("utf-8"))
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_extract_parameters(case["text"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("parameter_count") != reference.get("parameter_count") or
                    product.get("parameters") != reference.get("parameters")):
                    matched = False
            else:
                if str(product.get("extract_error")) != str(reference.get("extract_error")):
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
