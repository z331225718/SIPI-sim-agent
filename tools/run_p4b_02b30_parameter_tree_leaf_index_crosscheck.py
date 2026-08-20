# -*- coding: utf-8 -*-
"""P4B-02b30 AMI parameter tree leaf index cross-check (product vs independent ref).

Drives the product parameter tree leaf index runner (p4b_02b30_parameter_tree_leaf_index_runner) over parenthesized
AMI text inputs and leaf paths. An independent Python reference recomputes the leaf index and resolution.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b30-parameter-tree-leaf-index-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b30-parameter-tree-leaf-index-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b30.parameter-tree-leaf-index-v1.tree-leaf-index"


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


def ref_leaf_index(text: str, leaf_path: str) -> dict[str, Any]:
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

    leaf_values: dict[str, list[str]] = {}

    def walk(n: dict[str, Any], prefix: str) -> None:
        current = n["name"] if not prefix else f"{prefix}.{n['name']}"
        if n["kind"] == "leaf":
            leaf_values[current] = n["value_tokens"]
        else:
            for child in n["children"].values():
                walk(child, current)

    walk(node, "")
    leaf_paths = sorted(leaf_values.keys())

    trimmed = leaf_path.strip()
    if not trimmed:
        resolve = {"resolved": False, "error": "EmptyLeafPath"}
    else:
        canonical = ".".join([s for s in trimmed.split(".") if s])
        if canonical in leaf_values:
            resolve = {"resolved": True, "value_tokens": leaf_values[canonical]}
        elif any(p.startswith(canonical + ".") for p in leaf_paths):
            resolve = {"resolved": False, "error": f'LeafPathNotLeaf("{canonical}")'}
        else:
            resolve = {"resolved": False, "error": f'MissingLeafPath("{canonical}")'}

    return {"valid": True, "leaf_count": len(leaf_paths), "leaf_paths": leaf_paths, "resolve": resolve}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b30_parameter_tree_leaf_index_runner"

    cases = [
        {
            "label": "leaf_index_resolve",
            "text": "(root (branch_a (leaf_1 10)) (leaf_2 20))",
            "leaf_path": "root.leaf_2",
        },
        {
            "label": "branch_path_rejected",
            "text": "(root (branch_a (leaf_1 10)))",
            "leaf_path": "root.branch_a",
        },
        {
            "label": "missing_leaf_path",
            "text": "(root (a 1))",
            "leaf_path": "root.nope",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b30-") as tmp:
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
            reference = ref_leaf_index(case["text"], case["leaf_path"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("leaf_count") != reference["leaf_count"] or
                    product.get("leaf_paths") != reference["leaf_paths"] or
                    product.get("resolve") != reference["resolve"]):
                    matched = False
            else:
                prod_err = (product.get("index_error") or product.get("build_error")
                            or product.get("parse_error"))
                ref_err = (reference.get("index_error") or reference.get("build_error")
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
