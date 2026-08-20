# -*- coding: utf-8 -*-
"""P4B-02b22 AMI parameter tree diff summary cross-check (product vs independent ref).

Drives the product parameter tree diff summary runner (p4b_02b22_parameter_tree_diff_summary_runner) over parenthesized
AMI text inputs. An independent Python reference recomputes tree diff summary reports.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b22-parameter-tree-diff-summary-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b22-parameter-tree-diff-summary-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b22.parameter-tree-diff-summary-v1.diff-summary-report"


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


def ref_diff_nodes(path_prefix: str, left: dict[str, Any], right: dict[str, Any], diffs: list[dict[str, Any]]) -> None:
    current_path = f"{path_prefix}.{left['name']}" if path_prefix else left["name"]

    if left["kind"] == "branch" and right["kind"] == "branch":
        l_children = left["children"]
        r_children = right["children"]
        all_keys = sorted(set(l_children.keys()) | set(r_children.keys()))
        for key in all_keys:
            child_path = f"{current_path}.{key}"
            if key in l_children and key in r_children:
                ref_diff_nodes(current_path, l_children[key], r_children[key], diffs)
            elif key in l_children:
                diffs.append({"kind": "missing_node", "path": child_path})
            else:
                diffs.append({"kind": "extra_node", "path": child_path})
    elif left["kind"] == "leaf" and right["kind"] == "leaf":
        if left["value_tokens"] != right["value_tokens"]:
            diffs.append({
                "kind": "value_mismatch",
                "path": current_path,
                "left": left["value_tokens"],
                "right": right["value_tokens"],
            })
    else:
        diffs.append({"kind": "kind_mismatch", "path": current_path})


def ref_summary_report(text_left: str, text_right: str) -> dict[str, Any]:
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
        return {"valid": False, "diff_error": err_l}
    r_root, err_r = parse_trees(text_right)
    if err_r:
        return {"valid": False, "diff_error": err_r}

    if l_root["name"] != r_root["name"]:
        return {
            "valid": False,
            "diff_error": f'RootMismatch {{ expected: "{l_root["name"]}", actual: "{r_root["name"]}" }}',
        }

    diffs: list[dict[str, Any]] = []
    ref_diff_nodes("", l_root, r_root, diffs)

    missing = sum(1 for d in diffs if d["kind"] == "missing_node")
    extra = sum(1 for d in diffs if d["kind"] == "extra_node")
    kind_mm = sum(1 for d in diffs if d["kind"] == "kind_mismatch")
    val_mm = sum(1 for d in diffs if d["kind"] == "value_mismatch")

    lines = [
        "AMI Parameter Tree Diff Summary Report",
        f"Policy: {POLICY}",
    ]
    if not diffs:
        lines.append("Status: Identical (0 differences)")
    else:
        lines.append(f"Status: Modified ({len(diffs)} differences)")
        lines.append(f"  Missing Nodes: {missing}")
        lines.append(f"  Extra Nodes: {extra}")
        lines.append(f"  Kind Mismatches: {kind_mm}")
        lines.append(f"  Value Mismatches: {val_mm}")
        lines.append("Diff Details:")
        for d in diffs:
            if d["kind"] == "missing_node":
                lines.append(f"  - [Missing] {d['path']}")
            elif d["kind"] == "extra_node":
                lines.append(f"  - [Extra] {d['path']}")
            elif d["kind"] == "kind_mismatch":
                lines.append(f"  - [Kind Mismatch] {d['path']}")
            elif d["kind"] == "value_mismatch":
                l_str = " ".join(d["left"])
                r_str = " ".join(d["right"])
                lines.append(f"  - [Value Mismatch] {d['path']}: left=[{l_str}] right=[{r_str}]")

    return {
        "valid": True,
        "total_diffs": len(diffs),
        "is_identical": len(diffs) == 0,
        "summary_text": chr(10).join(lines),
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b22_parameter_tree_diff_summary_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b22_parameter_tree_diff_summary_runner-*.exe"))[-1]

    cases = [
        {
            "label": "identical_trees_summary",
            "text_left": "(Reserved_Parameters (tx_swing Float 0.5))",
            "text_right": "(Reserved_Parameters (tx_swing Float 0.5))",
        },
        {
            "label": "modified_trees_summary",
            "text_left": "(root (node_b 2) (val Float 0.5))",
            "text_right": "(root (node_c 3) (val Float 0.9))",
        },
        {
            "label": "root_mismatch_summary",
            "text_left": "(root_a (a 1))",
            "text_right": "(root_b (a 1))",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b22-") as tmp:
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
            reference = ref_summary_report(case["text_left"], case["text_right"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("total_diffs") != reference["total_diffs"] or
                    product.get("is_identical") != reference["is_identical"] or
                    product.get("summary_text") != reference["summary_text"]):
                    matched = False
            else:
                prod_err = product.get("summary_error") or product.get("diff_error") or product.get("build_error") or product.get("parse_error")
                ref_err = reference.get("summary_error") or reference.get("diff_error") or reference.get("build_error")
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
