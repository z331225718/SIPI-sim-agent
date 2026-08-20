# -*- coding: utf-8 -*-
"""P4B-02b13 AMI parameter tree pruning cross-check (product vs independent ref).

Drives the product parameter tree pruning runner (p4b_02b13_parameter_tree_pruning_runner) over parenthesized
AMI text inputs and target path segments. An independent Python reference recomputes tree pruning rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b13-parameter-tree-pruning-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b13-parameter-tree-pruning-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b13.parameter-tree-pruning-v1.tree-structural-pruning"


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


def ref_prune_node(node: dict[str, Any], segments: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    if not segments:
        return None, "EmptyPath"
    target = segments[0]
    if node["kind"] != "branch" or target not in node.get("children", {}):
        return None, f'PathNotFound("{target}")'

    new_node = copy.deepcopy(node)
    if len(segments) == 1:
        del new_node["children"][target]
        return new_node, None
    else:
        pruned_child, err = ref_prune_node(new_node["children"][target], segments[1:])
        if err:
            return None, err
        new_node["children"][target] = pruned_child
        return new_node, None


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


def ref_prune_tree(text: str, path: list[str]) -> dict[str, Any]:
    if not path:
        return {"valid": False, "prune_error": "EmptyPath"}
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens:
        return {"valid": False, "prune_error": "EmptyDocument"}

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
        return {"valid": False, "prune_error": "EmptyDocument"}
    ast, _ = parse_list(0)
    root, err = ref_build_node(ast)
    if err:
        return {"valid": False, "prune_error": err}

    if path[0] != root["name"]:
        return {"valid": False, "prune_error": "RootMismatch"}
    if len(path) == 1:
        return {"valid": False, "prune_error": "CannotPruneRoot"}

    pruned_root, err = ref_prune_node(root, path[1:])
    if err:
        return {"valid": False, "prune_error": err}

    formatted = ref_format_node(pruned_root, 0)
    return {"valid": True, "pruned_formatted_text": formatted}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b13_parameter_tree_pruning_runner"

    cases = [
        {
            "label": "prune_leaf_node",
            "text": "(Reserved_Parameters (tx_swing Float 0.5) (dfe (tap_1 Integer 2)))",
            "path": ["Reserved_Parameters", "tx_swing"],
        },
        {
            "label": "cannot_prune_root",
            "text": "(root (a 1))",
            "path": ["root"],
        },
        {
            "label": "path_not_found",
            "text": "(root (a 1))",
            "path": ["root", "nonexistent"],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b13-") as tmp:
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
            reference = ref_prune_tree(case["text"], case["path"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if product.get("pruned_formatted_text") != reference["pruned_formatted_text"]:
                    matched = False
            else:
                if str(product.get("prune_error")) != str(reference.get("prune_error")):
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
