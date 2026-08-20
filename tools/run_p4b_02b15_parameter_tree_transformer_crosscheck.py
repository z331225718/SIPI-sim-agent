# -*- coding: utf-8 -*-
"""P4B-02b15 AMI parameter tree transformer cross-check (product vs independent ref).

Drives the product parameter tree transformer runner (p4b_02b15_parameter_tree_transformer_runner) over parenthesized
AMI text inputs and target transformations. An independent Python reference recomputes tree transformations.
Fail closed on any mismatch.
"""

from __future__ import annotations

import copy
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b15-parameter-tree-transformer-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b15-parameter-tree-transformer-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b15.parameter-tree-transformer-v1.tree-structural-transform"


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


def ref_transform_node(node: dict[str, Any], path_prefix: str, target_path: str, new_leaf_tokens: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    current_path = f"{path_prefix}.{node['name']}" if path_prefix else node["name"]
    if current_path == target_path:
        return {
            "kind": "leaf",
            "name": node["name"],
            "value_tokens": new_leaf_tokens,
        }, None

    if node["kind"] == "branch":
        new_children = {}
        for k, child in node["children"].items():
            t_child, err = ref_transform_node(child, current_path, target_path, new_leaf_tokens)
            if err:
                return None, err
            new_children[k] = t_child
        return {
            "kind": "branch",
            "name": node["name"],
            "children": new_children,
        }, None
    else:
        return copy.deepcopy(node), None


def ref_format_node(node: dict[str, Any], indent: int) -> str:
    pad = " " * indent
    if node["kind"] == "branch":
        lines = [f'{pad}({node["name"]}']
        for child_name in sorted(node["children"].keys()):
            lines.append(ref_format_node(node["children"][child_name], indent + 2))
        lines_str = "\n".join(lines)
        return f"{lines_str})"
    else:
        if not node["value_tokens"]:
            return f'{pad}({node["name"]})'
        vals = " ".join(node["value_tokens"])
        return f'{pad}({node["name"]} {vals})'


def ref_transform_tree(text: str, target_path: str, new_leaf_tokens: list[str]) -> dict[str, Any]:
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens:
        return {"valid": False, "transformer_error": "EmptyDocument"}

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
        return {"valid": False, "transformer_error": "EmptyDocument"}
    ast, _ = parse_list(0)
    root, err = ref_build_node(ast)
    if err:
        return {"valid": False, "transformer_error": err}

    transformed_root, err = ref_transform_node(root, "", target_path, new_leaf_tokens)
    if err:
        return {"valid": False, "transformer_error": err}

    formatted = ref_format_node(transformed_root, 0)
    return {"valid": True, "transformed_formatted_text": formatted}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b15_parameter_tree_transformer_runner"

    cases = [
        {
            "label": "transform_tx_swing_leaf",
            "text": "(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            "target_path": "Reserved_Parameters.tx_swing",
            "new_leaf_tokens": ["Float", "1.0"],
        },
        {
            "label": "transform_tap_1_leaf",
            "text": "(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            "target_path": "Reserved_Parameters.dfe.tap_1",
            "new_leaf_tokens": ["Integer", "4"],
        },
        {
            "label": "empty_document",
            "text": "",
            "target_path": "Reserved_Parameters.tx_swing",
            "new_leaf_tokens": ["Float", "1.0"],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b15-") as tmp:
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
            reference = ref_transform_tree(case["text"], case["target_path"], case["new_leaf_tokens"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if product.get("transformed_formatted_text") != reference["transformed_formatted_text"]:
                    matched = False
            else:
                prod_err = product.get("transformer_error") or product.get("build_error") or product.get("parse_error")
                ref_err = reference.get("transformer_error") or reference.get("build_error")
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
