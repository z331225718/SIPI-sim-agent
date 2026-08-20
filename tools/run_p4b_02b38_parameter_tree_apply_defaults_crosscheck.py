# -*- coding: utf-8 -*-
"""P4B-02b38 AMI parameter tree defaults application cross-check (product vs independent ref).

Drives the product parameter tree apply-defaults runner (p4b_02b38_parameter_tree_apply_defaults_runner)
over parenthesized AMI text inputs plus a defaults map. An independent Python reference replicates
the tree build and the fill-missing defaults rules. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b38-parameter-tree-apply-defaults-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b38-parameter-tree-apply-defaults-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b38.parameter-tree-apply-defaults-v1.default-fill-missing"


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


def ref_apply_defaults(text: str, defaults: dict[str, list[str]]) -> dict[str, Any]:
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

    if not defaults:
        return {"valid": False, "defaults_error": "EmptyDefaults"}

    leaf_names: set[str] = set()

    def collect(n: dict[str, Any]) -> None:
        if n["kind"] == "leaf":
            leaf_names.add(n["name"])
        else:
            for c in n["children"].values():
                collect(c)

    collect(node)

    added = 0
    skipped = 0
    extra_children: dict[str, dict[str, Any]] = {}
    for name in sorted(defaults.keys()):
        if name in leaf_names:
            skipped += 1
            continue
        token_list = defaults[name]
        if not token_list:
            return {"valid": False, "defaults_error": f'EmptyDefaultTokens("{name}")'}
        extra_children[name] = {"kind": "leaf", "name": name, "value_tokens": list(token_list)}
        added += 1

    if node["kind"] != "branch":
        return {"valid": False, "defaults_error": "RootNotBranch"}
    new_children = dict(node["children"])
    for key, child in extra_children.items():
        new_children[key] = child
    sorted_children = {k: new_children[k] for k in sorted(new_children.keys())}
    new_root = {"kind": "branch", "name": node["name"], "children": sorted_children}
    return {
        "valid": True,
        "added": added,
        "skipped": skipped,
        "root_name": "root",
        "tree": ref_node_json(new_root),
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b38_parameter_tree_apply_defaults_runner"

    cases = [
        {
            "label": "fill_missing",
            "text": "(root (gain Float 0.5))",
            "defaults": {"steps": ["Integer", "7"]},
        },
        {
            "label": "skip_existing",
            "text": "(root (gain Float 0.5))",
            "defaults": {"gain": ["Float", "9.9"]},
        },
        {
            "label": "empty_defaults",
            "text": "(root (gain Float 0.5))",
            "defaults": {},
        },
        {
            "label": "empty_default_tokens",
            "text": "(root (gain Float 0.5))",
            "defaults": {"steps": []},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b38-") as tmp:
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
            reference = ref_apply_defaults(case["text"], case["defaults"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("added") != reference.get("added") or
                    product.get("skipped") != reference.get("skipped") or
                    product.get("root_name") != reference.get("root_name") or
                    product.get("tree") != reference.get("tree")):
                    matched = False
            else:
                prod_err = (product.get("defaults_error") or product.get("build_error")
                            or product.get("parse_error"))
                ref_err = (reference.get("defaults_error") or reference.get("build_error")
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
