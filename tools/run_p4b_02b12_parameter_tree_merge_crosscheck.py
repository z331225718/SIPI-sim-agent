# -*- coding: utf-8 -*-
"""P4B-02b12 AMI parameter tree merge cross-check (product vs independent ref).

Drives the product parameter tree merge runner (p4b_02b12_parameter_tree_merge_runner) over parenthesized
AMI text inputs. An independent Python reference recomputes tree structural merge rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b12-parameter-tree-merge-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b12-parameter-tree-merge-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b12.parameter-tree-merge-v1.tree-structural-merge"


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


def ref_merge_nodes(left: dict[str, Any], right: dict[str, Any], path_prefix: str) -> tuple[dict[str, Any] | None, str | None]:
    current_path = f"{path_prefix}.{left['name']}" if path_prefix else left["name"]

    if left["kind"] == "branch" and right["kind"] == "branch":
        l_children = left["children"]
        r_children = right["children"]
        merged_children = {}

        for k, l_child in l_children.items():
            if k in r_children:
                m_child, err = ref_merge_nodes(l_child, r_children[k], current_path)
                if err:
                    return None, err
                merged_children[k] = m_child
            else:
                merged_children[k] = l_child

        for k, r_child in r_children.items():
            if k not in l_children:
                merged_children[k] = r_child

        sorted_children = {k: merged_children[k] for k in sorted(merged_children.keys())}
        return {
            "kind": "branch",
            "name": left["name"],
            "children": sorted_children,
        }, None
    elif left["kind"] == "leaf" and right["kind"] == "leaf":
        return right, None
    else:
        return None, f'KindConflict {{ path: "{current_path}" }}'


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


def ref_merge_trees(text_left: str, text_right: str) -> dict[str, Any]:
    def parse_trees(text: str) -> tuple[dict[str, Any] | None, str | None]:
        text_clean = re.sub(r'\|.*', '', text)
        tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
        if not tokens:
            return None, "EmptyDocument"

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
            return None, "EmptyDocument"
        ast, _ = parse_list(0)
        return ref_build_node(ast)

    l_root, err_l = parse_trees(text_left)
    if err_l:
        return {"valid": False, "merge_error": err_l}
    r_root, err_r = parse_trees(text_right)
    if err_r:
        return {"valid": False, "merge_error": err_r}

    if l_root["name"] != r_root["name"]:
        return {
            "valid": False,
            "merge_error": f'RootMismatch {{ expected: "{l_root["name"]}", actual: "{r_root["name"]}" }}',
        }

    merged_root, err = ref_merge_nodes(l_root, r_root, "")
    if err:
        return {"valid": False, "merge_error": err}

    formatted = ref_format_node(merged_root, 0)
    return {"valid": True, "merged_formatted_text": formatted}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b12_parameter_tree_merge_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b12_parameter_tree_merge_runner-*.exe"))[-1]

    cases = [
        {
            "label": "complementary_and_override",
            "text_left": "(root (node_a 1) (val Float 0.5))",
            "text_right": "(root (node_b 2) (val Float 0.9))",
        },
        {
            "label": "kind_conflict",
            "text_left": "(root (node 1))",
            "text_right": "(root (node (sub 2)))",
        },
        {
            "label": "root_mismatch",
            "text_left": "(root_a (a 1))",
            "text_right": "(root_b (a 1))",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b12-") as tmp:
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
            reference = ref_merge_trees(case["text_left"], case["text_right"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if product.get("merged_formatted_text") != reference["merged_formatted_text"]:
                    matched = False
            else:
                if str(product.get("merge_error")) != str(reference.get("merge_error")):
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
