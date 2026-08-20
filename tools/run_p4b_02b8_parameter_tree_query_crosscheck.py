# -*- coding: utf-8 -*-
"""P4B-02b8 AMI parameter tree query cross-check (product vs independent ref).

Drives the product parameter tree query runner (p4b_02b8_parameter_tree_query_runner) over parenthesized
AMI text inputs and target path segments. An independent Python reference recomputes path queries.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b8-parameter-tree-query-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b8.parameter-tree-query-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b8.parameter-tree-query-v1.path-query-tree"


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
        return {
            "kind": "leaf",
            "name": name,
            "value_tokens": tokens,
        }, None
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
        return {
            "kind": "branch",
            "name": name,
            "children": sorted_children,
        }, None


def ref_query_node(node: dict[str, Any], segments: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    if not segments:
        return {"kind": node["kind"], "target_name": node["name"]}, None
    if node["kind"] != "branch":
        return None, f'PathNotFound("{node["name"]}")'
    next_seg = segments[0]
    children = node.get("children", {})
    if next_seg not in children:
        return None, f'PathNotFound("{next_seg}")'
    return ref_query_node(children[next_seg], segments[1:])


def ref_query_tree(text: str, path: list[str]) -> dict[str, Any]:
    if not path:
        return {"valid": False, "query_error": "EmptyPath"}
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens:
        return {"valid": False, "query_error": "EmptyDocument"}

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
        return {"valid": False, "query_error": "NoValidTrees"}
    ast, _ = parse_list(0)
    root, err = ref_build_node(ast)
    if err:
        return {"valid": False, "query_error": err}
    if path[0] != root["name"]:
        return {"valid": False, "query_error": "RootMismatch"}

    res, err = ref_query_node(root, path[1:])
    if err:
        return {"valid": False, "query_error": err}
    return {"valid": True, "kind": res["kind"], "target_name": res["target_name"]}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b8_parameter_tree_query_runner"

    cases = [
        {
            "label": "query_existing_leaf",
            "text": "(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            "path": ["Reserved_Parameters", "dfe", "tap_1"],
        },
        {
            "label": "query_existing_branch",
            "text": "(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            "path": ["Reserved_Parameters", "dfe"],
        },
        {
            "label": "path_not_found",
            "text": "(Reserved_Parameters (tx_swing Float 0.5))",
            "path": ["Reserved_Parameters", "nonexistent"],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b8-") as tmp:
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
            reference = ref_query_tree(case["text"], case["path"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("kind") != reference["kind"] or
                    product.get("target_name") != reference["target_name"]):
                    matched = False
            else:
                if str(product.get("query_error")) != str(reference.get("query_error")):
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
