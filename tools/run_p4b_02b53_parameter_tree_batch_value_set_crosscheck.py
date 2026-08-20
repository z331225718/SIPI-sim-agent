# -*- coding: utf-8 -*-
"""P4B-02b53 AMI parameter tree batch value set cross-check (product vs independent ref).

Drives the product batch value set runner (p4b_02b53_parameter_tree_batch_value_set_runner) over
parenthesized AMI text inputs, a type map, and an updates map. An independent Python reference
replicates the tree build, occurrence counting, typed validation, and application.
Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b53-parameter-tree-batch-value-set-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b53-parameter-tree-batch-value-set-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b53.parameter-tree-batch-value-set-v1.name-addressed-batch-set"


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


def ref_node_json(n: dict[str, Any]) -> dict[str, Any]:
    if n["kind"] == "leaf":
        return {"kind": "leaf", "name": n["name"], "value_tokens": list(n["value_tokens"])}
    return {
        "kind": "branch",
        "name": n["name"],
        "children": [ref_node_json(c) for c in n["children"].values()],
    }


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


def ref_batch(text: str, types: dict[str, str], updates: dict[str, str]) -> dict[str, Any]:
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

    if not updates:
        return {"valid": False, "batch_error": "EmptyUpdates"}

    counts: dict[str, int] = {}

    def count_node(n: dict[str, Any]) -> None:
        if n["kind"] == "leaf":
            counts[n["name"]] = counts.get(n["name"], 0) + 1
        else:
            for c in n["children"].values():
                count_node(c)

    count_node(node)
    for name in updates:
        if name not in counts:
            return {"valid": False, "batch_error": f'MissingLeaf("{name}")'}
        if counts[name] > 1:
            return {"valid": False, "batch_error": f'AmbiguousName("{name}")'}
        if name not in types:
            return {"valid": False, "batch_error": f'MissingType("{name}")'}
        rule_error = ref_value_rule(name, types[name], updates[name])
        if rule_error == "InvalidName":
            return {"valid": False, "batch_error": f'InvalidLeafName("{name}")'}
        if rule_error is not None:
            return {"valid": False,
                    "batch_error": f'InvalidValue {{ leaf: "{name}", error: {rule_error} }}'}

    updated = 0

    def apply_node(n: dict[str, Any]) -> dict[str, Any]:
        nonlocal updated
        if n["kind"] == "leaf":
            if n["name"] in updates:
                updated += 1
                return {"kind": "leaf", "name": n["name"], "value_tokens": [updates[n["name"]]]}
            return dict(n)
        new_children = {}
        for key, child in n["children"].items():
            new_children[key] = apply_node(child)
        return {"kind": "branch", "name": n["name"], "children": new_children}

    new_root = apply_node(node)
    return {"valid": True, "updated": updated, "root_name": "root",
            "tree": ref_node_json(new_root)}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b53_parameter_tree_batch_value_set_runner"

    cases = [
        {
            "label": "batch_update",
            "text": "(root (gain Float 0.5) (steps Integer 7))",
            "types": {"gain": "Float", "steps": "Integer"},
            "updates": {"gain": "1.25", "steps": "8"},
        },
        {
            "label": "ambiguous_name",
            "text": "(root (sub (gain Float 1.0)) (gain Float 2.0))",
            "types": {"gain": "Float"},
            "updates": {"gain": "3.0"},
        },
        {
            "label": "missing_leaf",
            "text": "(root (gain Float 0.5))",
            "types": {"gain": "Float"},
            "updates": {"nope": "1.0"},
        },
        {
            "label": "invalid_value",
            "text": "(root (gain Float 0.5))",
            "types": {"gain": "Float"},
            "updates": {"gain": "x1"},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b53-") as tmp:
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
            reference = ref_batch(case["text"], case["types"], case["updates"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("updated") != reference.get("updated") or
                    product.get("root_name") != reference.get("root_name") or
                    product.get("tree") != reference.get("tree")):
                    matched = False
            else:
                prod_err = (product.get("batch_error") or product.get("build_error")
                            or product.get("parse_error"))
                ref_err = (reference.get("batch_error") or reference.get("build_error")
                           or reference.get("parse_error"))
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
