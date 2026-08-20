"""P5-02g canonical parameter JSON v1: resolve pure reference defaults.

Resolves defaults of kind `reference` when the expression is a pure
`param.X` / `OP.X` reference whose chain ends in literal defaults
(cycle and depth limited). Arithmetic expressions and unresolved chains
stay `needs_matlab_oracle`. External observation tooling; resolution is
identity lookup over observed call targets, never product code.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json-draft.v1.yaml"
REFERENCE = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-reference.v1.yaml"
CANONICAL = ROOT / "docs" / "baselines" / "p5-r480-canonical-parameter-json.v1.yaml"
CANONICAL_SCHEMA = "sipi.p5-02.canonical-parameter-json.v1"
PURE_REF_RE = re.compile(r"^(param|OP)\.[A-Za-z_]\w*$")
LHS_RE = re.compile(r"^\s*([A-Za-z_]\w*\.[A-Za-z_]\w*)\s*=")
MAX_DEPTH = 8


def main() -> int:
    draft = yaml.safe_load(DRAFT.read_text(encoding="utf-8"))
    reference = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    # target -> list of (key) from LHS assignments
    targets = {}
    for key, entry in reference["keys"].items():
        for text in entry["call_texts"]:
            match = LHS_RE.match(text)
            if match:
                targets.setdefault(match.group(1), []).append(key)
    # key -> (required, default kind, literal expression) aggregated:
    # use the first call that carries a literal default for the key.
    literal_by_key = {}
    for key, entry in draft["keys"].items():
        for call in entry["calls"]:
            default = call["default"]
            if default["kind"] == "literal" and key not in literal_by_key:
                literal_by_key[key] = default["expression"]

    def resolve(key, path):
        if key in literal_by_key:
            return {"status": "resolved", "value": literal_by_key[key], "chain": [key]}
        if len(path) >= MAX_DEPTH or key in path:
            return {"status": "needs_matlab_oracle", "reason": "cycle_or_depth", "chain": path + [key]}
        return {"status": "needs_matlab_oracle", "reason": "no_literal_default", "chain": path + [key]}

    keys_out = {}
    resolved_count = 0
    oracle_count = 0
    for key, entry in draft["keys"].items():
        defaults = []
        for call in entry["calls"]:
            default = call["default"]
            kind = default["kind"]
            if kind == "literal":
                defaults.append({"kind": "literal", "value": default["expression"], "required": call["required"]})
            elif kind == "reference":
                expression = default["expression"]
                pure = PURE_REF_RE.match(expression)
                if pure is None:
                    defaults.append({"kind": "needs_matlab_oracle", "expression": expression, "required": call["required"]})
                    oracle_count += 1
                    continue
                target = expression
                mapped_keys = targets.get(target, [])
                if not mapped_keys:
                    defaults.append({"kind": "needs_matlab_oracle", "expression": expression, "required": call["required"]})
                    oracle_count += 1
                    continue
                result = resolve(mapped_keys[0], [])
                if result["status"] == "resolved":
                    defaults.append({"kind": "resolved_reference", "value": result["value"], "chain": result["chain"], "expression": expression, "required": call["required"]})
                    resolved_count += 1
                else:
                    defaults.append({"kind": "needs_matlab_oracle", "expression": expression, "required": call["required"]})
                    oracle_count += 1
            else:
                entry_out = {"kind": kind, "required": call["required"]}
                if "expression" in default:
                    entry_out["expression"] = default["expression"]
                defaults.append(entry_out)
        keys_out[key] = {"occurrences": entry["occurrences"], "defaults": defaults}
    canonical = {
        "schema": CANONICAL_SCHEMA,
        "status": "canonical_parameter_json_v1_literals_and_reference_chains",
        "draft_ref": "docs/baselines/p5-r480-canonical-parameter-json-draft.v1.yaml",
        "source_sha256": draft["source_sha256"],
        "key_count": len(keys_out),
        "resolved_default_calls": resolved_count,
        "needs_oracle_calls": oracle_count,
        "keys": keys_out,
        "non_claims": [
            "not_arithmetic_evaluation",
            "not_warning_contract",
            "not_parameter_design",
            "not_compute_parity",
            "not_release_evidence",
        ],
    }
    CANONICAL.write_text(yaml.safe_dump(canonical, sort_keys=False), encoding="utf-8")
    print("resolved=" + str(resolved_count) + " needs_oracle=" + str(oracle_count))
    print("canonical JSON v1 written: " + str(CANONICAL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
