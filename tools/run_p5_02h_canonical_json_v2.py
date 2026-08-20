"""P5-02h canonical parameter JSON v2: bounded static arithmetic.

Evaluates default expressions restricted to the documented grammar:
numbers (including MATLAB leading-dot literals), operators + - * /,
parentheses, and param.X / OP.X references whose canonical value is a
literal or resolved reference. IEEE double semantics; anything outside
the grammar (functions, unknown operands) stays needs_matlab_oracle.
External observation tooling, not product code.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v1.yaml"
REFERENCE = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-reference.v1.yaml"
V2 = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v2.yaml"
V2_SCHEMA = "sipi.p5-02.canonical-parameter-json.v2"
LHS_RE = re.compile(r"^\s*([A-Za-z_]\w*\.[A-Za-z_]\w*)\s*=")
NUMBER_RE = re.compile(r"(?:[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)")
REF_RE = re.compile(r"(?:param|OP)\.[A-Za-z_]\w*")
MAX_DEPTH = 8


def tokenize(expression):
    tokens = []
    index = 0
    while index < len(expression):
        char = expression[index]
        if char.isspace():
            index += 1
            continue
        if char in "+-*/(),":
            tokens.append(char)
            index += 1
            continue
        number = NUMBER_RE.match(expression, index)
        if number is not None:
            tokens.append(("num", float(number.group(0))))
            index = number.end()
            continue
        reference = REF_RE.match(expression, index)
        if reference is not None:
            tokens.append(("ref", reference.group(0)))
            index = reference.end()
            continue
        return None
    return tokens


def evaluate_tokens(tokens, value_of, depth):
    if tokens is None or depth > MAX_DEPTH:
        return None
    # parse sum of products with left-to-right precedence
    index = [0]

    def parse_atom():
        if index[0] >= len(tokens):
            return None
        token = tokens[index[0]]
        if isinstance(token, tuple) and token[0] == "num":
            index[0] += 1
            return token[1]
        if isinstance(token, tuple) and token[0] == "ref":
            index[0] += 1
            return value_of(token[1], depth)
        if token == "(":
            index[0] += 1
            value = parse_sum()
            if value is None or index[0] >= len(tokens) or tokens[index[0]] != ")":
                return None
            index[0] += 1
            return value
        return None

    def parse_product():
        value = parse_atom()
        if value is None:
            return None
        while index[0] < len(tokens) and tokens[index[0]] in ("*", "/"):
            operator = tokens[index[0]]
            index[0] += 1
            right = parse_atom()
            if right is None:
                return None
            if operator == "*":
                value = value * right
            else:
                if right == 0.0:
                    return None
                value = value / right
        return value

    def parse_sum():
        value = parse_product()
        if value is None:
            return None
        while index[0] < len(tokens) and tokens[index[0]] in ("+", "-"):
            operator = tokens[index[0]]
            index[0] += 1
            right = parse_product()
            if right is None:
                return None
            value = value + right if operator == "+" else value - right
        return value

    result = parse_sum()
    if result is None or index[0] != len(tokens):
        return None
    if not (result == result) or result in (float("inf"), float("-inf")):
        return None
    return result


def main() -> int:
    v1 = yaml.safe_load(V1.read_text(encoding="utf-8"))
    reference = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    # target -> keys from LHS; prefer keys with a resolved value.
    targets = {}
    for key, entry in reference["keys"].items():
        for text in entry["call_texts"]:
            match = LHS_RE.match(text)
            if match:
                targets.setdefault(match.group(1), []).append(key)
    # key -> canonical value (float) when literal or resolved_reference
    values = {}
    for key, entry in v1["keys"].items():
        for default in entry["defaults"]:
            value = default.get("value")
            if value is None:
                continue
            try:
                values[key] = float(value)
                break
            except ValueError:
                continue

    def value_of(reference, depth):
        if depth > MAX_DEPTH:
            return None
        key = reference.split(".", 1)[1]
        if key in values:
            return values[key]
        mapped = targets.get(reference, [])
        for candidate in mapped:
            if candidate in values:
                return values[candidate]
        return None

    evaluated = 0
    oracle = 0
    keys_out = {}
    for key, entry in v1["keys"].items():
        defaults = []
        for default in entry["defaults"]:
            kind = default["kind"]
            if kind == "needs_matlab_oracle":
                expression = default.get("expression", "")
                tokens = tokenize(expression)
                result = evaluate_tokens(tokens, value_of, 0) if tokens is not None else None
                if result is not None:
                    defaults.append({"kind": "statically_evaluated", "value": repr(result), "expression": expression, "required": default.get("required")})
                    evaluated += 1
                else:
                    defaults.append({"kind": "needs_matlab_oracle", "expression": expression, "required": default.get("required")})
                    oracle += 1
            else:
                defaults.append(default)
        keys_out[key] = {"occurrences": entry["occurrences"], "defaults": defaults}
    v2 = {
        "schema": V2_SCHEMA,
        "status": "canonical_parameter_json_v2_bounded_static_arithmetic",
        "v1_ref": "docs/baselines/p5-r480-canonical-parameter-json.v1.yaml",
        "source_sha256": v1["source_sha256"],
        "key_count": len(keys_out),
        "statically_evaluated_calls": evaluated,
        "needs_oracle_calls": oracle,
        "grammar": {
            "numbers": "ieee_double_including_leading_dot",
            "operators": ["+", "-", "*", "/"],
            "parentheses": "allowed",
            "references": "param.X_or_OP.X_resolved_by_canonical_value",
            "functions": "forbidden",
        },
        "keys": keys_out,
        "non_claims": [
            "not_matlab_evaluation",
            "not_warning_contract",
            "not_parameter_design",
            "not_compute_parity",
            "not_release_evidence",
        ],
    }
    V2.write_text(yaml.safe_dump(v2, sort_keys=False), encoding="utf-8")
    print("evaluated=" + str(evaluated) + " needs_oracle=" + str(oracle))
    print("canonical JSON v2 written: " + str(V2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
