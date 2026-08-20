# -*- coding: utf-8 -*-
"""P4B-02b78 parameter tree leaf canonicalization cross-check (product vs independent ref).

Drives the product leaf canonicalization runner (p4b_02b78_parameter_tree_leaf_canonicalization_runner)
over parenthesized AMI text inputs. An independent Python reference replicates the tree build and
the per-leaf canonical spelling rules: two-token typed forms with valid values get Integer via
parsed int in decimal and List via trimmed items joined with ", "; everything else stays raw.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b78-parameter-tree-leaf-canonicalization-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b78-parameter-tree-leaf-canonicalization-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b78.parameter-tree-leaf-canonicalization-v1.canonical-leaf-spellings"


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


def ref_value_valid(type_token: str, value_token: str) -> bool:
    if type_token == "Float":
        try:
            v = float(value_token)
        except ValueError:
            return False
        import math
        return math.isfinite(v)
    if type_token == "Integer":
        try:
            int(value_token)
            return True
        except ValueError:
            return False
    if type_token == "Boolean":
        return value_token in ("True", "False")
    if type_token == "String":
        return bool(value_token)
    if type_token == "List":
        return ref_list_items(value_token) is not None
    return False


def ref_canonical(type_token: str, value_token: str) -> str:
    if type_token == "Integer":
        return str(int(value_token))
    if type_token == "List":
        items = [item.strip() for item in ref_list_items(value_token)]
        return "(" + ", ".join(items) + ")"
    return value_token


def ref_canonicalize(text: str) -> dict[str, Any]:
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

    leaves = 0
    canonicalized = 0

    def canon_node(n: dict[str, Any]) -> dict[str, Any]:
        nonlocal leaves, canonicalized
        if n["kind"] == "leaf":
            leaves += 1
            tokens_list = list(n["value_tokens"])
            if len(tokens_list) == 2:
                type_token = tokens_list[0]
                value_token = tokens_list[1]
                if type_token in ("Float", "Integer", "Boolean", "String", "List") and ref_value_valid(type_token, value_token):
                    canonical = ref_canonical(type_token, value_token)
                    if canonical != value_token:
                        canonicalized += 1
                        return {"kind": "leaf", "name": n["name"],
                                "value_tokens": [type_token, canonical]}
            return {"kind": "leaf", "name": n["name"], "value_tokens": tokens_list}
        new_children = {}
        for key, child in n["children"].items():
            new_children[key] = canon_node(child)
        return {"kind": "branch", "name": n["name"], "children": new_children}

    new_root = canon_node(node)
    return {"valid": True, "leaves": leaves, "canonicalized": canonicalized,
            "root_name": "root", "tree": ref_node_json(new_root)}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b78_parameter_tree_leaf_canonicalization_runner"

    cases = [
        {
            "label": "integer_and_list",
            "text": "(root (steps Integer 007) (channels List (a,b,c)))",
        },
        {
            "label": "raw_types",
            "text": "(root (gain Float 0.50) (mode String Linear) (on Boolean True))",
        },
        {
            "label": "mixed_nested",
            "text": "(root (sub (steps Integer 007)) (plain 5))",
        },
        {
            "label": "invalid_untouched",
            "text": "(root (bad Integer abc) (raw x y z) (gain Float 0.5))",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b78-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / (case["label"] + "_in.json")
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / (case["label"] + "_rep.json")
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_canonicalize(case["text"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("leaves") != reference.get("leaves") or
                        product.get("canonicalized") != reference.get("canonicalized") or
                        product.get("root_name") != reference.get("root_name") or
                        product.get("tree") != reference.get("tree")):
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
