# -*- coding: utf-8 -*-
"""P4B-02b24 AMI parameter tree node rename cross-check (product vs independent ref).

Drives the product parameter tree rename runner (p4b_02b24_parameter_tree_rename_runner) over parenthesized
AMI text inputs, paths, and new names. An independent Python reference recomputes node rename.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b24-parameter-tree-rename-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b24-parameter-tree-rename-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b24.parameter-tree-rename-v1.tree-node-rename"


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


def ref_rename(text: str, path: str, new_name: str) -> dict[str, Any]:
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
    root_node, err = ref_build_node(ast)
    if err:
        return {"valid": False, "build_error": err}
    root_name = root_node["name"]

    trimmed = path.strip()
    if not trimmed:
        return {"valid": False, "rename_error": "EmptyPath"}
    segments = [s for s in trimmed.split(".") if s]
    if not segments:
        return {"valid": False, "rename_error": "EmptyPath"}
    if len(segments) == 1:
        return {"valid": False, "rename_error": "RootRenameForbidden"}
    if segments[0] != root_name:
        return {"valid": False, "rename_error": f'RootMismatch {{ expected: "{root_name}", actual: "{segments[0]}" }}'}
    trimmed_new = new_name.strip()
    if not trimmed_new:
        return {"valid": False, "rename_error": "EmptyNewName"}
    if not is_valid_identifier(trimmed_new):
        return {"valid": False, "rename_error": "InvalidNewName"}

    def walk(node: dict[str, Any], segs: list[str]) -> dict[str, Any] | None:
        if not segs:
            return node
        head = segs[0]
        if head != node["name"]:
            return None
        if len(segs) == 1:
            return node
        if node["kind"] != "branch":
            return None
        child = node["children"].get(segs[1])
        if child is None:
            return None
        return walk(child, segs[1:])

    if walk(root_node, segments) is None:
        return {"valid": False, "rename_error": f'MissingPath("{ ".".join(segments) }")'}

    def rename(node: dict[str, Any], segs: list[str]) -> dict[str, Any]:
        if not segs:
            out = dict(node)
            out["name"] = trimmed_new
            return out
        head = segs[0]
        rest = segs[1:]
        if node["kind"] != "branch":
            raise RuntimeError("unreachable")
        children = dict(node["children"])
        if not rest:
            child = children.pop(head)
            child = rename(child, [])
            children[trimmed_new] = child
        else:
            children[head] = rename(children[head], rest)
        out = dict(node)
        out["children"] = children
        return out

    renamed = rename(root_node, segments[1:])
    return {"valid": True, "root_name": root_name, "tree": renamed}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b24_parameter_tree_rename_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b24_parameter_tree_rename_runner-*.exe"))[-1]

    cases = [
        {
            "label": "rename_leaf_node",
            "text": "(root (a 1) (b 2))",
            "path": "root.a",
            "new_name": "a_renamed",
        },
        {
            "label": "rename_branch_node",
            "text": "(root (branch_a (leaf_1 10)) (branch_b 20))",
            "path": "root.branch_a",
            "new_name": "branch_x",
        },
        {
            "label": "root_rename_forbidden",
            "text": "(root (a 1))",
            "path": "root",
            "new_name": "other",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b24-") as tmp:
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
            reference = ref_rename(case["text"], case["path"], case["new_name"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("root_name") != reference["root_name"] or
                    product.get("tree") != reference["tree"]):
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
