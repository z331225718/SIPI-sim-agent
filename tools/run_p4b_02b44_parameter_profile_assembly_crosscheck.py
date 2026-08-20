# -*- coding: utf-8 -*-
"""P4B-02b44 AMI parameter profile assembly cross-check (product vs independent ref).

Drives the product profile assembly runner (p4b_02b44_parameter_profile_assembly_runner) over
parenthesized AMI texts, a defaults map, and a reserved-name set. An independent Python reference
replicates the tree build, per-tree typed-form rules, defaults fill, and reserved rejection.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b44-parameter-profile-assembly-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b44-parameter-profile-assembly-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b44.parameter-profile-assembly-v1.strict-profile-assembly"


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


TYPE_TOKENS = ("Float", "Integer", "Boolean", "String", "List")


def ref_value_rule(name: str, type_token: str, value_token: str) -> str | None:
    """Replicate AmiParameterValueV1::try_new product-owned rules; return None on success."""
    if not name:
        return "EmptyName"
    first, *rest = name
    if not (first.isascii() and (first.isalpha() or first == "_")):
        return "InvalidName"
    if not all(c.isascii() and (c.isalnum() or c == "_") for c in rest):
        return "InvalidName"
    if type_token == "Float":
        try:
            value = float(value_token)
        except ValueError:
            return "InvalidFloat"
        if value != value or value in (float("inf"), float("-inf")):
            return "InvalidFloat"
    elif type_token == "Integer":
        try:
            int(value_token)
        except ValueError:
            return "InvalidInteger"
    elif type_token == "Boolean":
        if value_token not in ("True", "False"):
            return "InvalidBoolean"
    elif type_token == "String":
        if not value_token:
            return "EmptyStringValue"
    elif type_token == "List":
        if not (value_token.startswith("(") and value_token.endswith(")")):
            return "InvalidList"
        inner = value_token[1:-1]
        if not inner or any(not item.strip() for item in inner.split(",")):
            return "InvalidList"
    else:
        return "UnknownTypeToken"
    return None


def ref_parse_text(text: str) -> tuple[dict[str, Any] | None, str | None]:
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
    node, err = ref_build_node(ast)
    return node, err


def ref_extract_tree(node: dict[str, Any], out_params: dict[str, dict[str, str]],
                     leaves_consumed: list[int]) -> str | None:
    """Replicate 02b34 typed-form extraction; return error string or None."""
    for child in node["children"].values():
        if child["kind"] == "branch":
            error = ref_extract_tree(child, out_params, leaves_consumed)
            if error:
                return error
            continue
        name = child["name"]
        value_tokens = child["value_tokens"]
        if not value_tokens:
            return f'EmptyValueTokens("{name}")'
        if len(value_tokens) == 1:
            return f'NotTypedForm {{ leaf: "{name}" }}'
        if len(value_tokens) > 2:
            return f'MultiTokenForm {{ leaf: "{name}", token_count: {len(value_tokens)} }}'
        type_token, value_token = value_tokens
        if type_token not in TYPE_TOKENS:
            return f'UnknownTypeToken {{ leaf: "{name}", token: "{type_token}" }}'
        rule_error = ref_value_rule(name, type_token, value_token)
        if rule_error == "InvalidName":
            return f'InvalidParameterName("{name}")'
        if rule_error is not None:
            return f'InvalidValue {{ leaf: "{name}", error: {rule_error} }}'
        if name in out_params:
            return f'DuplicateParameter("{name}")'
        out_params[name] = {"name": name, "type": type_token, "value": value_token}
        leaves_consumed[0] += 1
    return None


def ref_assemble(texts: list[str], defaults: dict[str, list[str]],
                 reserved: list[str]) -> dict[str, Any]:
    reserved_set = set(reserved)
    if not reserved_set:
        return {"valid": False, "assembly_error": "EmptyReservedSet"}
    parameters: dict[str, dict[str, str]] = {}
    leaves_consumed = [0]
    for index, text in enumerate(texts):
        node, err = ref_parse_text(text)
        if err:
            return {"valid": False, "parse_error": err}
        tree_params: dict[str, dict[str, str]] = {}
        tree_consumed = [0]
        error = ref_extract_tree(node, tree_params, tree_consumed)
        if error:
            return {"valid": False,
                    "assembly_error": f'Extraction(TreeError({index}, {error}))'}
        for name, parameter in tree_params.items():
            if name in parameters:
                return {"valid": False,
                        "assembly_error": f'Extraction(DuplicateAcrossTrees("{name}"))'}
            parameters[name] = parameter
        leaves_consumed[0] += tree_consumed[0]

    defaults_applied = 0
    defaults_skipped = 0
    for name in sorted(defaults.keys()):
        if name in parameters:
            defaults_skipped += 1
            continue
        tokens = defaults[name]
        if len(tokens) != 2:
            return {"valid": False,
                    "assembly_error": f'DefaultNotTypedForm {{ name: "{name}", token_count: {len(tokens)} }}'}
        type_token, value_token = tokens
        if type_token not in TYPE_TOKENS:
            return {"valid": False,
                    "assembly_error": f'InvalidDefaultValue {{ name: "{name}", error: UnknownTypeToken }}'}
        rule_error = ref_value_rule(name, type_token, value_token)
        if rule_error is not None:
            return {"valid": False,
                    "assembly_error": f'InvalidDefaultValue {{ name: "{name}", error: {rule_error} }}'}
        parameters[name] = {"name": name, "type": type_token, "value": value_token}
        defaults_applied += 1

    for name in sorted(parameters.keys()):
        if name in reserved_set:
            return {"valid": False, "assembly_error": f'ReservedNameUsed("{name}")'}

    return {"valid": True, "leaves_consumed": leaves_consumed[0],
            "defaults_applied": defaults_applied, "defaults_skipped": defaults_skipped,
            "parameters": parameters}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b44_parameter_profile_assembly_runner"

    cases = [
        {
            "label": "assemble_full",
            "texts": ["(root (gain Float 0.5))", "(root (enabled Boolean True))"],
            "defaults": {"steps": ["Integer", "7"]},
            "reserved": ["Reserved_Parameters"],
        },
        {
            "label": "reserved_used",
            "texts": ["(root (gain Float 0.5) (Reserved_Parameters Integer 1))"],
            "defaults": {},
            "reserved": ["Reserved_Parameters"],
        },
        {
            "label": "malformed_default",
            "texts": ["(root (gain Float 0.5))"],
            "defaults": {"steps": ["Integer"]},
            "reserved": ["Reserved_Parameters"],
        },
        {
            "label": "empty_reserved",
            "texts": ["(root (gain Float 0.5))"],
            "defaults": {},
            "reserved": [],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b44-") as tmp:
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
            reference = ref_assemble(case["texts"], case["defaults"], case["reserved"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("leaves_consumed") != reference.get("leaves_consumed") or
                    product.get("defaults_applied") != reference.get("defaults_applied") or
                    product.get("defaults_skipped") != reference.get("defaults_skipped") or
                    product.get("parameters") != reference.get("parameters")):
                    matched = False
            else:
                prod_err = (product.get("assembly_error") or product.get("parse_error"))
                ref_err = (reference.get("assembly_error") or reference.get("parse_error"))
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
