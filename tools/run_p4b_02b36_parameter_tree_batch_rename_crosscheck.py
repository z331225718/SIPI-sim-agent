# -*- coding: utf-8 -*-
"""P4B-02b36 AMI parameter tree batch rename cross-check (product vs independent ref).

Drives the product parameter tree batch rename runner (p4b_02b36_parameter_tree_batch_rename_runner)
over parenthesized AMI text inputs plus an old-name -> new-name map. An independent Python
reference replicates the tree build and the two-phase batch rename rules. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b36-parameter-tree-batch-rename-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b36-parameter-tree-batch-rename-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b36.parameter-tree-batch-rename-v1.leaf-map-rename"


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


def ref_rename(text: str, renames: dict[str, str]) -> dict[str, Any]:
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

    if not renames:
        return {"valid": False, "rename_error": "EmptyRenameMap"}

    leaf_names: set[str] = set()

    def collect(n: dict[str, Any]) -> None:
        if n["kind"] == "leaf":
            leaf_names.add(n["name"])
        else:
            for c in n["children"].values():
                collect(c)

    collect(node)
    for old_name in renames:
        if old_name not in leaf_names:
            return {"valid": False, "rename_error": f'MissingLeaf("{old_name}")'}
        new_name = renames[old_name]
        if not is_valid_identifier(new_name):
            return {"valid": False, "rename_error": f'InvalidNewName("{new_name}")'}

    def rename_node(n: dict[str, Any]) -> dict[str, Any] | str:
        if n["kind"] == "leaf":
            new_name = renames.get(n["name"], n["name"])
            return {"kind": "leaf", "name": new_name, "value_tokens": list(n["value_tokens"])}
        new_children: dict[str, dict[str, Any]] = {}
        renamed_entries: list[tuple[str, dict[str, Any]]] = []
        for key, child in n["children"].items():
            renamed_child = rename_node(child)
            if isinstance(renamed_child, str):
                return renamed_child
            if child["kind"] == "leaf" and child["name"] in renames:
                renamed_entries.append((renamed_child["name"], renamed_child))
            else:
                new_children[key] = renamed_child
        for new_key, renamed_child in renamed_entries:
            if new_key in new_children:
                return f'SiblingNameCollision("{new_key}")'
            new_children[new_key] = renamed_child
        sorted_children = {k: new_children[k] for k in sorted(new_children.keys())}
        return {"kind": "branch", "name": n["name"], "children": sorted_children}

    renamed_root = rename_node(node)
    if isinstance(renamed_root, str):
        return {"valid": False, "rename_error": renamed_root}
    return {"valid": True, "root_name": "root", "tree": ref_node_json(renamed_root)}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b36_parameter_tree_batch_rename_runner"

    cases = [
        {
            "label": "simple_rename",
            "text": "(root (gain Float 0.5) (steps Integer 7))",
            "renames": {"gain": "amplitude"},
        },
        {
            "label": "sibling_collision",
            "text": "(root (gain Float 0.5) (steps Integer 7))",
            "renames": {"gain": "steps"},
        },
        {
            "label": "missing_leaf",
            "text": "(root (gain Float 0.5))",
            "renames": {"nope": "x"},
        },
        {
            "label": "swap_siblings",
            "text": "(root (a Float 0.5) (b Integer 7))",
            "renames": {"a": "b", "b": "a"},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b36-") as tmp:
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
            reference = ref_rename(case["text"], case["renames"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("root_name") != reference.get("root_name") or
                    product.get("tree") != reference.get("tree")):
                    matched = False
            else:
                prod_err = (product.get("rename_error") or product.get("build_error")
                            or product.get("parse_error"))
                ref_err = (reference.get("rename_error") or reference.get("build_error")
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
