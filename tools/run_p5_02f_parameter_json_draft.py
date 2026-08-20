"""P5-02f external-only canonical parameter JSON draft generator.

Classifies the observed xls_parameter call arguments into required-flag
and default-expression categories (literal / reference / none), and
writes a hash-bound draft of the canonical R480 parameter JSON. Default
expressions are classified, never evaluated; reference defaults stay
unresolved for the MATLAB oracle slice. External observation tooling,
not product code.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-reference.v1.yaml"
DRAFT = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json-draft.v1.yaml"
DRAFT_SCHEMA = "sipi.p5-02.canonical-parameter-json-draft.v1"
CALL_RE = re.compile(r"xls_parameter\s*\(([^)]*)\)")
LITERAL_RE = re.compile(r"^(?:[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?|true|false|\[.*\])$")


def classify_default(expression):
    if expression is None:
        return {"kind": "none", "value": None}
    stripped = expression.strip()
    if LITERAL_RE.match(stripped):
        return {"kind": "literal", "expression": stripped}
    if stripped in ("inf", "+inf", "-inf"):
        return {"kind": "inf_literal", "expression": stripped}
    if stripped.startswith("\'") and stripped.endswith("\'"):
        return {"kind": "string_literal", "expression": stripped}
    words = stripped.split()
    first = words[0] if words else ""
    is_reference = stripped.startswith("param.") or stripped.startswith("OP.") or ("." in first)
    if is_reference:
        return {"kind": "reference", "expression": stripped}
    return {"kind": "unclassified", "expression": stripped}


def classify_required(token):
    if token is None:
        return "absent"
    lowered = token.strip().lower()
    if lowered == "true":
        return "true"
    if lowered == "false":
        return "false"
    return "absent"


def split_arguments(body):
    parts = []
    depth = 0
    current = []
    for character in body:
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
        if character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current:
        parts.append("".join(current).strip())
    return parts


def main() -> int:
    reference = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    keys_out = {}
    total_calls = 0
    literal_defaults = 0
    reference_defaults = 0
    for key, entry in reference["keys"].items():
        calls = []
        for text in entry["call_texts"]:
            match = CALL_RE.search(text)
            if match is None:
                continue
            arguments = split_arguments(match.group(1))
            total_calls += 1
            required_token = arguments[2] if len(arguments) > 2 else None
            default_expr = arguments[3] if len(arguments) > 3 else None
            required = classify_required(required_token)
            if required_token is not None and required_token.strip().lower() not in ("true", "false") and default_expr is None:
                # Bare-default variant: xls_parameter(parameter, KEY, VALUE)
                default_expr = required_token
            default = classify_default(default_expr)
            if default["kind"] == "literal":
                literal_defaults += 1
            elif default["kind"] == "reference":
                reference_defaults += 1
            calls.append({"required": required, "default": default})
        default_kinds = sorted({call["default"]["kind"] for call in calls})
        required_set = sorted({call["required"] for call in calls})
        keys_out[key] = {
            "occurrences": len(calls),
            "required_observed": required_set,
            "default_kinds_observed": default_kinds,
            "calls": calls,
        }
    draft = {
        "schema": DRAFT_SCHEMA,
        "status": "canonical_parameter_json_draft_defaults_classified_not_evaluated",
        "reference_ref": "docs/baselines/p5-r480-canonical-parameter-reference.v1.yaml",
        "source_sha256": reference["source_sha256"],
        "key_count": len(keys_out),
        "call_count": total_calls,
        "literal_default_calls": literal_defaults,
        "reference_default_calls": reference_defaults,
        "keys": keys_out,
        "non_claims": [
            "not_defaults_resolved",
            "not_warning_contract",
            "not_parameter_design",
            "not_compute_parity",
            "not_release_evidence",
        ],
    }
    DRAFT.write_text(yaml.safe_dump(draft, sort_keys=False), encoding="utf-8")
    print("keys=" + str(len(keys_out)) + " calls=" + str(total_calls) + " literal=" + str(literal_defaults) + " reference=" + str(reference_defaults))
    print("draft written: " + str(DRAFT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
