# -*- coding: utf-8 -*-
"""P4B-02b94 parameter tree leaf canonical spelling check cross-check (product vs independent ref).

Drives the product canonical spelling check runner
(p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner) over parenthesized AMI text inputs.
An independent Python reference replicates the tree build and the canonical check: try_new-valid
typed-form leaves compare their raw value token to the canonical spelling (Integer via parsed int
in decimal, List via trimmed items joined with ", ", Float/String/Boolean raw) and report every
non-canonical leaf with path, type, raw value, and canonical value. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b94-parameter-tree-leaf-canonical-spelling-check-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b94-parameter-tree-leaf-canonical-spelling-check-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b94.parameter-tree-leaf-canonical-spelling-check-v1.canonical-leaf-spelling-check"

KNOWN_TYPES = ("Float", "Integer", "Boolean", "String", "List")


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
            if not isinstance(item, str):
                return None, "InvalidNodeName"
            if not (is_valid_identifier(item)
                    or (len(item) >= 2 and item.startswith('"') and item.endswith('"'))):
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


def ref_check(text: str) -> dict[str, Any]:
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

    typed_leaves = 0
    non_canonical = []

    def walk(n: dict[str, Any], prefix: str) -> None:
        nonlocal typed_leaves
        current = n["name"] if not prefix else prefix + "." + n["name"]
        if n["kind"] == "leaf":
            tokens_list = n["value_tokens"]
            if len(tokens_list) == 2 and tokens_list[0] in KNOWN_TYPES:
                if ref_value_valid(tokens_list[0], tokens_list[1]):
                    typed_leaves += 1
                    canonical = ref_canonical(tokens_list[0], tokens_list[1])
                    if canonical != tokens_list[1]:
                        non_canonical.append({
                            "path": current,
                            "type_token": tokens_list[0],
                            "value_token": tokens_list[1],
                            "canonical": canonical,
                        })
            return
        for child in n["children"].values():
            walk(child, current)

    walk(node, "")
    return {"valid": True, "typed_leaves": typed_leaves,
            "canonical": not non_canonical, "non_canonical": non_canonical}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner"

    cases = [
        {"label": "canonical_tree",
         "text": "(root (gain Float 0.5) (steps Integer 7) (on Boolean True))"},
        {"label": "non_canonical_integer",
         "text": "(root (steps Integer 007) (gain Float 0.5))"},
        {"label": "nested",
         "text": "(root (sub (steps Integer 007)) (gain Float 0.5))"},
        {"label": "no_typed",
         "text": "(root (plain 5) (raw x y z))"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b94-") as tmp:
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
            reference = ref_check(case["text"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("typed_leaves") == reference.get("typed_leaves")
                       and product.get("canonical") == reference.get("canonical")
                       and product.get("non_canonical") == reference.get("non_canonical"))
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
