# -*- coding: utf-8 -*-
"""P4B-02b87 parameter tree leaf declared-type map cross-check (product vs independent ref).

Drives the product type map runner (p4b_02b87_parameter_tree_leaf_type_map_runner) over
parenthesized AMI text inputs. An independent Python reference replicates the tree build and the
declared-type extraction: two-token leaves whose first token is a known type token are recorded
name -> type; everything else is skipped. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b87-parameter-tree-leaf-type-map-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b87-parameter-tree-leaf-type-map-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b87.parameter-tree-leaf-type-map-v1.declared-type-map"

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


def ref_type_map(text: str) -> dict[str, Any]:
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

    type_map: dict[str, str] = {}
    leaves_total = 0
    typed_leaves = 0
    skipped = 0

    def walk(n: dict[str, Any]) -> None:
        nonlocal leaves_total, typed_leaves, skipped
        if n["kind"] == "leaf":
            leaves_total += 1
            tokens_list = n["value_tokens"]
            if len(tokens_list) == 2 and tokens_list[0] in KNOWN_TYPES:
                type_map[n["name"]] = tokens_list[0]
                typed_leaves += 1
                return
            skipped += 1
            return
        for child in n["children"].values():
            walk(child)

    walk(node)
    return {"valid": True, "type_map": type_map, "leaves_total": leaves_total,
            "typed_leaves": typed_leaves, "skipped": skipped}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b87_parameter_tree_leaf_type_map_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b87_parameter_tree_leaf_type_map_runner-*.exe"))[-1]

    cases = [
        {"label": "typed_forms",
         "text": "(root (gain Float 0.5) (steps Integer 7) (on Boolean True))"},
        {"label": "mixed_skipped",
         "text": "(root (gain Float 0.5) (plain 5) (channels List (a)) (raw x y))"},
        {"label": "nested",
         "text": "(root (sub (steps Integer 007)) (gain Float 0.5))"},
        {"label": "duplicate",
         "text": "(root (gain Float 0.5) (sub (gain Integer 7)))"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b87-") as tmp:
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
            reference = ref_type_map(case["text"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("type_map") != reference.get("type_map") or
                        product.get("leaves_total") != reference.get("leaves_total") or
                        product.get("typed_leaves") != reference.get("typed_leaves") or
                        product.get("skipped") != reference.get("skipped")):
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
