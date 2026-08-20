# -*- coding: utf-8 -*-
"""P4B-02b29 AMI parameter tree depth stats cross-check (product vs independent ref).

Drives the product parameter tree depth stats runner (p4b_02b29_parameter_tree_depth_stats_runner) over parenthesized
AMI text inputs. An independent Python reference recomputes depth statistics.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b29-parameter-tree-depth-stats-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b29-parameter-tree-depth-stats-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b29.parameter-tree-depth-stats-v1.tree-depth-statistics"


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


def ref_depth_stats(text: str) -> dict[str, Any]:
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

    max_depth = 0
    min_depth = 10 ** 9
    leaf_count = 0
    nodes_per_depth: list[int] = []
    leaves_per_depth: list[int] = []

    def walk(n: dict[str, Any], depth: int) -> None:
        nonlocal max_depth, min_depth, leaf_count
        while len(nodes_per_depth) <= depth:
            nodes_per_depth.append(0)
            leaves_per_depth.append(0)
        nodes_per_depth[depth] += 1
        max_depth = max(max_depth, depth)
        min_depth = min(min_depth, depth)
        if n["kind"] == "leaf":
            leaf_count += 1
            leaves_per_depth[depth] += 1
        else:
            for child in n["children"].values():
                walk(child, depth + 1)

    walk(node, 0)
    if min_depth == 10 ** 9:
        min_depth = 0

    return {
        "valid": True,
        "max_depth": max_depth,
        "min_depth": min_depth,
        "leaf_count": leaf_count,
        "nodes_per_depth": nodes_per_depth,
        "leaves_per_depth": leaves_per_depth,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b29_parameter_tree_depth_stats_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b29_parameter_tree_depth_stats_runner-*.exe"))[-1]

    cases = [
        {
            "label": "nested_depth_stats",
            "text": "(root (branch_a (leaf_1 10)) (leaf_2 20))",
        },
        {
            "label": "single_node_depth_stats",
            "text": "(root)",
        },
        {
            "label": "deep_depth_stats",
            "text": "(root (a (b (c 1))))",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b29-") as tmp:
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
            reference = ref_depth_stats(case["text"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("max_depth") != reference["max_depth"] or
                    product.get("min_depth") != reference["min_depth"] or
                    product.get("leaf_count") != reference["leaf_count"] or
                    product.get("nodes_per_depth") != reference["nodes_per_depth"] or
                    product.get("leaves_per_depth") != reference["leaves_per_depth"]):
                    matched = False
            else:
                prod_err = (product.get("stats_error") or product.get("build_error")
                            or product.get("parse_error"))
                ref_err = (reference.get("stats_error") or reference.get("build_error")
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
