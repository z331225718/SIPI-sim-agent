# -*- coding: utf-8 -*-
"""P4B-02b89 parameter tree leaf typed diff cross-check (product vs independent ref).

Drives the product leaf typed diff runner (p4b_02b89_parameter_tree_leaf_typed_diff_runner) over
two parenthesized AMI texts. An independent Python reference replicates the tree builds and the
leaf diff: shared paths with typed-equivalent leaves are matched, typed-inequivalent leaves are
changed (with both token lists and the typed reason), non-typed leaves fall back to raw token
equality, left-only paths are removed and right-only paths are added. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b89-parameter-tree-leaf-typed-diff-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b89-parameter-tree-leaf-typed-diff-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b89.parameter-tree-leaf-typed-diff-v1.typed-leaf-diff"

KNOWN_TYPES = ("Float", "Integer", "Boolean", "String", "List")


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


def ref_parse(text: str) -> dict[str, Any]:
    text_clean = re.sub(r'\|.*', '', text)
    tokens = re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text_clean)
    if not tokens or tokens[0] != '(':
        return {"error": "EmptyDocument"}

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

    ast, _ = parse_list(0)
    node, err = ref_build_node(ast)
    if err:
        return {"error": err}
    return {"node": node}


def ref_collect(node: dict[str, Any], prefix: str, out: dict[str, list[str]]) -> None:
    current = node["name"] if not prefix else prefix + "." + node["name"]
    if node["kind"] == "leaf":
        out[current] = list(node["value_tokens"])
    else:
        for child in node["children"].values():
            ref_collect(child, current, out)


def ref_list_items(value_token: str):
    if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
        return None
    inner = value_token[1:-1]
    if not inner:
        return None
    items = [item.strip() for item in inner.split(",")]
    if any(not item for item in items):
        return None
    return items


def ref_value_valid(type_token: str, value_token: str) -> bool:
    if type_token == "Float":
        try:
            v = float(value_token)
        except ValueError:
            return False
        import math
        return math.isfinite(v)
    if type_token == "Integer":
        try:
            int(value_token)
            return True
        except ValueError:
            return False
    if type_token == "Boolean":
        return value_token in ("True", "False")
    if type_token == "String":
        return bool(value_token)
    if type_token == "List":
        return ref_list_items(value_token) is not None
    return False


def ref_value_equiv_reason(left: dict[str, str], right: dict[str, str]) -> str | None:
    if left["type"] != right["type"]:
        return "TypeMismatch"
    t = left["type"]
    lv, rv = left["value"], right["value"]
    if t == "Float":
        try:
            lf, rf = float(lv), float(rv)
        except ValueError:
            return "MalformedValue"
        return None if lf == rf else "FloatMismatch"
    if t == "Integer":
        try:
            li, ri = int(lv), int(rv)
        except ValueError:
            return "MalformedValue"
        return None if li == ri else "IntegerMismatch"
    if t == "Boolean":
        return None if lv == rv else "BooleanMismatch"
    if t == "String":
        return None if lv == rv else "StringMismatch"
    if t == "List":
        li = ref_list_items(lv)
        ri = ref_list_items(rv)
        if li is None or ri is None:
            return "MalformedValue"
        if len(li) != len(ri):
            return "ListLengthMismatch"
        for a, b in zip(li, ri):
            if a != b:
                return "ListItemMismatch"
        return None
    return "MalformedValue"


def ref_typed_value(name: str, tokens: list[str]) -> dict[str, str] | None:
    if len(tokens) == 2 and tokens[0] in KNOWN_TYPES and ref_value_valid(tokens[0], tokens[1]):
        return {"type": tokens[0], "value": tokens[1]}
    return None


def ref_leaf_diff(left_text: str, right_text: str) -> dict[str, Any]:
    left_parsed = ref_parse(left_text)
    if "error" in left_parsed:
        return {"valid": False, "left_error": left_parsed["error"]}
    right_parsed = ref_parse(right_text)
    if "error" in right_parsed:
        return {"valid": False, "right_error": right_parsed["error"]}

    left_leaves: dict[str, list[str]] = {}
    right_leaves: dict[str, list[str]] = {}
    ref_collect(left_parsed["node"], "", left_leaves)
    ref_collect(right_parsed["node"], "", right_leaves)

    matched = 0
    added = sorted(set(right_leaves) - set(left_leaves))
    removed = sorted(set(left_leaves) - set(right_leaves))
    changed = []
    for path in sorted(set(left_leaves) & set(right_leaves)):
        left_tokens = left_leaves[path]
        right_tokens = right_leaves[path]
        leaf_name = path.rsplit(".", 1)[-1]
        lv = ref_typed_value(leaf_name, left_tokens)
        rv = ref_typed_value(leaf_name, right_tokens)
        reason = None
        if lv is not None and rv is not None:
            reason = ref_value_equiv_reason(lv, rv)
        else:
            if left_tokens == right_tokens:
                matched += 1
                continue
        if reason is None and lv is not None and rv is not None:
            matched += 1
            continue
        changed.append({
            "path": path,
            "old_tokens": list(left_tokens),
            "new_tokens": list(right_tokens),
            "reason": reason,
        })
    return {"valid": True, "matched": matched, "added": added,
            "removed": removed, "changed": changed}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b89_parameter_tree_leaf_typed_diff_runner"

    cases = [
        {"label": "identical_trees",
         "left_text": "(root (gain Float 0.5) (steps Integer 7))",
         "right_text": "(root (gain Float 0.5) (steps Integer 7))"},
        {"label": "spelling_variants",
         "left_text": "(root (gain Float 0.5))",
         "right_text": "(root (gain Float 0.50))"},
        {"label": "added_removed",
         "left_text": "(root (gain Float 0.5) (steps Integer 7))",
         "right_text": "(root (gain Float 0.5) (mode String Linear))"},
        {"label": "typed_changed",
         "left_text": "(root (gain Float 0.5))",
         "right_text": "(root (gain Float 0.5001))"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b89-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / (case["label"] + "_in.json")
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / (case["label"] + "_rep.json")
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_leaf_diff(case["left_text"], case["right_text"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("matched") == reference.get("matched")
                       and product.get("added") == reference.get("added")
                       and product.get("removed") == reference.get("removed")
                       and product.get("changed") == reference.get("changed"))
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
