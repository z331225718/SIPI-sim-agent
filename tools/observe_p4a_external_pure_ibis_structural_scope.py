"""Observe bounded structural facts from an owner-authorized external IBIS file."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "sipi.p4a.external-pure-ibis-structural-observation.v1"
EXPECTED_SHA256 = "46c53a49a31dea27769f0dddddadea72f03f1f956fb8e60aeaa24f83a7201b95"
EXPECTED_LENGTH = 406532
HEADER = re.compile(r"^\s*\[([^\]]+)\](.*)$")
MODEL_TYPE = re.compile(r"^\s*Model_type\s+([^\s|]+)", re.IGNORECASE)
INDICATORS = {
    "algorithmic_model": "[algorithmic model]",
    "ami_file": ".ami",
    "dynamic_library": ".dll",
    "include": "[include]",
}


class ObservationError(RuntimeError):
    pass


def _digest(values: list[str]) -> str:
    encoded = bytearray()
    for value in values:
        raw = value.encode("ascii")
        encoded.extend(len(raw).to_bytes(4, "big"))
        encoded.extend(raw)
    return hashlib.sha256(encoded).hexdigest()


def _span_digest(spans: list[tuple[int, int]]) -> str:
    return _digest([f"{start}:{end}" for start, end in spans])


def observe_bytes(data: bytes, *, observer_source_sha256: str) -> dict[str, Any]:
    if len(data) != EXPECTED_LENGTH or hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        raise ObservationError("asset_identity_mismatch")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise ObservationError("asset_not_ascii") from error

    facts = {"ibis_header": [], "component": [], "model": [], "model_selector": [], "model_type_input": []}
    identifiers = {"model": [], "model_selector": []}
    indicator_counts = {key: 0 for key in INDICATORS}
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("|", maxsplit=1)[0]
        normalized = line.lower()
        for key, indicator in INDICATORS.items():
            indicator_counts[key] += normalized.count(indicator)
        header = HEADER.match(line)
        if header:
            keyword = header.group(1).strip().lower()
            payload = header.group(2).strip()
            if keyword == "ibis ver":
                facts["ibis_header"].append((number, number))
            elif keyword == "component":
                facts["component"].append((number, number))
            elif keyword == "model":
                facts["model"].append((number, number))
                identifiers["model"].append(payload)
            elif keyword == "model selector":
                facts["model_selector"].append((number, number))
                identifiers["model_selector"].append(payload)
            continue
        model_type = MODEL_TYPE.match(line)
        if model_type and model_type.group(1).lower() == "input":
            facts["model_type_input"].append((number, number))

    if len(facts["ibis_header"]) != 1 or not facts["component"] or not facts["model"]:
        raise ObservationError("required_structural_scope_missing")
    if any(count for count in indicator_counts.values()):
        result = "inconclusive_declared_indicator_observed"
    else:
        result = "structural_scope_pass_for_owner_selection"
    return {
        "schema": SCHEMA,
        "asset_identity": {"content_sha256": EXPECTED_SHA256, "byte_length": EXPECTED_LENGTH},
        "observer": {"source_sha256": observer_source_sha256, "mode": "external_read_only", "product_parser_not_used": True},
        "scan_scope": {
            "allowed": ["line_structure", "bracket_headers", "section_counts", "identifier_digests", "source_span_digests", "fixed_indicator_counts"],
            "forbidden": ["numeric_tables", "curves", "parameter_values", "package_pvt_evaluation", "interpolation", "simulation", "ami_dll_calls"],
        },
        "facts": {
            key: {"count": len(spans), "span_digest": _span_digest(spans), **({"identifier_digest": _digest(identifiers[key])} if key in identifiers else {})}
            for key, spans in facts.items()
        },
        "negative_observations": {"indicator_rule_sha256": _digest([f"{key}:{value}" for key, value in sorted(INDICATORS.items())]), "counts": indicator_counts, "meaning": "not_observed_in_declared_scope_only"},
        "result": result,
        "unexamined": ["model_selector_choice", "model_semantics", "numeric_data", "ami_binary_dependencies", "license", "electrical_behavior"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report = observe_bytes(args.asset.read_bytes(), observer_source_sha256=source_hash)
    except (OSError, ObservationError) as error:
        report = {"schema": SCHEMA, "status": "rejected", "reason": str(error)}
    args.report.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"schema": report["schema"], "status": report.get("result", report.get("status"))}, sort_keys=True, separators=(",", ":")))
    return 0 if report.get("result") == "structural_scope_pass_for_owner_selection" else 2


if __name__ == "__main__":
    raise SystemExit(main())
