# -*- coding: utf-8 -*-
"""P4B-02b9 AMI parameter tree formatter cross-check (product vs independent ref).

Drives the product parameter tree formatter runner (p4b_02b9_parameter_tree_formatter_runner)
over parenthesized AMI text inputs. An independent Python reference recomputes tree formatting.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b9-parameter-tree-formatter-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b9.parameter-tree-formatter-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b9.parameter-tree-formatter-v1.tree-to-sexpr"


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


def ref_format_trees(text: str) -> dict[str, Any]:
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens:
        return {"valid": False, "format_error": "EmptyDocument"}

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
        return {"valid": False, "format_error": "EmptyTreeList"}
    
    idx = 0
    forms = []
    while idx < len(tokens):
        if tokens[idx] == '(':
            form, idx = parse_list(idx)
            forms.append(form)
        else:
            idx += 1

    if not forms:
        return {"valid": False, "format_error": "EmptyTreeList"}

    formatted_roots = []
    for form in forms:
        node, err = ref_build_node(form)
        if err:
            return {"valid": False, "format_error": err}
        formatted_roots.append(ref_format_node(node, 0))

    return {"valid": True, "formatted_text": "\n".join(formatted_roots)}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b9_parameter_tree_formatter_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b9_parameter_tree_formatter_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_tree_formatting",
            "text": "(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
        },
        {
            "label": "nested_branches_formatting",
            "text": "(root (branch_a (leaf_1 10)) (branch_b (leaf_2 20)))",
        },
        {
            "label": "empty_document",
            "text": "",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b9-") as tmp:
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
            reference = ref_format_trees(case["text"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if product.get("formatted_text") != reference["formatted_text"]:
                    matched = False
            else:
                prod_err = product.get("format_error") or product.get("build_error") or product.get("parse_error")
                ref_err = reference.get("format_error") or reference.get("build_error")
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
