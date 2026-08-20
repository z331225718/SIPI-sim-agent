# -*- coding: utf-8 -*-
"""P4B-02b58 typed-form conformance report cross-check (product vs independent ref).

Drives the product conformance report runner (p4b_02b58_parameter_tree_typed_form_report_runner)
over parenthesized AMI text inputs. An independent Python reference replicates the tree build and
the per-leaf conformance classification. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b58-parameter-tree-typed-form-conformance-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b58-parameter-tree-typed-form-conformance-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b58.parameter-tree-typed-form-conformance-v1.full-report"


def is_valid_identifier(name: str) -> bool:
    trimmed = name.strip()
    return bool(trimmed) and trimmed.isascii() and all(c.isalnum() or c in "_-." for c in trimmed)


def ref_build_node(node: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(node, list) or not node:
        return None, "InvalidNodeName"
    head = node[0]
    if not isinstance(head, str) or not is_valid_identifier(head):
        return None, "InvalidNodeName"
    name = head.strip()

    has_sublist = any(isinstance(item, list) for item in node[1:])
    if not has_sublist:
        tokens = []
        for item in node[1:]:
            if not isinstance(item, str) or not is_valid_identifier(item):
                return None, "InvalidNodeName"
            tokens.append(item)
        return {"kind": "leaf", "name": name, "value_tokens": tokens}, None
    else:
        children = {}
        for item in node[1:]:
            if isinstance(item, list):
                child, err = ref_build_node(item)
                if err:
                    return None, err
                cname = child["name"]
                if cname in children:
                    return None, f'DuplicateChild("{cname}")'
                children[cname] = child
        sorted_children = {k: children[k] for k in sorted(children.keys())}
        return {"kind": "branch", "name": name, "children": sorted_children}, None


TYPE_TOKENS = ("Float", "Integer", "Boolean", "String", "List")


def ref_value_rule(name: str, type_token: str, value_token: str) -> str | None:
    """Replicate AmiParameterValueV1::try_new product-owned rules; return None on success."""
    if not name:
        return "EmptyName"
    first, *rest = name
    if not (first.isascii() and (first.isalpha() or first == "_")):
        return "InvalidName"
    if not all(c.isascii() and (c.isalnum() or c == "_") for c in rest):
        return "InvalidName"
    if type_token == "Float":
        try:
            value = float(value_token)
        except ValueError:
            return "InvalidFloat"
        if value != value or value in (float("inf"), float("-inf")):
            return "InvalidFloat"
    elif type_token == "Integer":
        try:
            int(value_token)
        except ValueError:
            return "InvalidInteger"
    elif type_token == "Boolean":
        if value_token not in ("True", "False"):
            return "InvalidBoolean"
    elif type_token == "String":
        if not value_token:
            return "EmptyStringValue"
    elif type_token == "List":
        if not (value_token.startswith("(") and value_token.endswith(")")):
            return "InvalidList"
        inner = value_token[1:-1]
        if not inner or any(not item.strip() for item in inner.split(",")):
            return "InvalidList"
    else:
        return "UnknownTypeToken"
    return None


def ref_classify(name: str, value_tokens: list[str]) -> tuple[bool, dict[str, Any] | None]:
    if not value_tokens:
        return False, {"kind": "EmptyValueTokens"}
    if len(value_tokens) == 1:
        return False, {"kind": "NotTypedForm"}
    if len(value_tokens) > 2:
        return False, {"kind": "MultiTokenForm", "token_count": len(value_tokens)}
    type_token, value_token = value_tokens
    if type_token not in TYPE_TOKENS:
        return False, {"kind": "UnknownTypeToken", "token": type_token}
    rule_error = ref_value_rule(name, type_token, value_token)
    if rule_error == "InvalidName":
        return False, {"kind": "InvalidParameterName"}
    if rule_error is not None:
        return False, {"kind": "InvalidValue", "error": rule_error}
    return True, None


def ref_report(text: str) -> dict[str, Any]:
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
    ast, _ = parse_list(0)
    node, err = ref_build_node(ast)
    if err:
        return {"valid": False, "build_error": err}

    entries_by_name: dict[str, dict[str, Any]] = {}

    def walk(n: dict[str, Any]) -> None:
        if n["kind"] == "leaf":
            conforming, violation = ref_classify(n["name"], n["value_tokens"])
            entries_by_name[n["name"]] = {
                "leaf": n["name"],
                "conforming": conforming,
                "violation": violation,
            }
        else:
            for c in n["children"].values():
                walk(c)

    walk(node)
    entries = [entries_by_name[name] for name in sorted(entries_by_name.keys())]
    conforming_count = sum(1 for e in entries if e["conforming"])
    return {"valid": True, "conforming_count": conforming_count,
            "non_conforming_count": len(entries) - conforming_count,
            "entries": entries}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b58_parameter_tree_typed_form_report_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b58_parameter_tree_typed_form_report_runner-*.exe"))[-1]

    cases = [
        {
            "label": "all_conforming",
            "text": "(root (gain Float 0.5) (steps Integer 7))",
        },
        {
            "label": "mixed_violations",
            "text": "(root (a Real 1) (b 1 2 3) (c 1) (d Float x1))",
        },
        {
            "label": "empty_leaf",
            "text": "(root (a))",
        },
        {
            "label": "nested_conforming",
            "text": "(root (sub (deep Float 1.0)) (gain Float 0.5))",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b58-") as tmp:
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
            reference = ref_report(case["text"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("conforming_count") != reference.get("conforming_count") or
                    product.get("non_conforming_count") != reference.get("non_conforming_count") or
                    product.get("entries") != reference.get("entries")):
                    matched = False
            else:
                prod_err = (product.get("build_error") or product.get("parse_error"))
                ref_err = (reference.get("build_error") or reference.get("parse_error"))
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
