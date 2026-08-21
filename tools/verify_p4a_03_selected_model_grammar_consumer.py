"""Verify the bounded P4A-03 selected-model grammar/consumer gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/baselines/p4a-03-selected-model-grammar-consumer.v1.yaml"
IMPLEMENTATION = ROOT / "crates/sipi-ibis/src/selected_model_v1.rs"
RUNNER = ROOT / "crates/sipi-ibis/tests/p4a_03bk_selected_model_runner.rs"
SPEC = ROOT / "docs/clean-room/specs/p4a-ibis-selected-model-grammar-consumer.v1.md"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p4a-03-selected-model-grammar-consumer.md"
EVIDENCE = ROOT / "docs/baselines/p4a-03bk-selected-model-crosscheck-evidence.v1.json"
DEFAULT_EXTERNAL = Path(
    r"C:\Users\z3312\code\.sipi-p4a-official-asset-20260821\as4c512m16md4v-053bin.ibs"
)
SCHEMA = "sipi.p4a-03.selected-model-grammar-consumer.v1"
POLICY = "sipi.p4a-03.selected-model-consumer.v1.explicit-profile-only"


class SelectedModelGrammarError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SelectedModelGrammarError("manifest_not_mapping")
    return value


def observe_complete_external(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise SelectedModelGrammarError("external_not_ascii") from error
    lines = []
    models = set()
    selectors = set()
    pins = []
    section = None
    for raw in text.splitlines():
        line = raw.split("|", 1)[0].strip()
        if not line:
            continue
        header = re.match(r"^\[([^\]]+)\]\s*(.*)$", line)
        if header:
            section, payload = header.group(1).strip(), header.group(2).strip()
            lines.append((section, payload))
            if section == "Model":
                models.add(payload)
            elif section == "Model Selector":
                selectors.add(payload)
            continue
        lines.append(("data", line))
        fields = line.split()
        if section == "Pin" and len(fields) >= 3:
            pins.append(fields[2])
    ends = [index for index, record in enumerate(lines) if record == ("End", "")]
    if ends != [len(lines) - 1]:
        raise SelectedModelGrammarError("external_complete_document_boundary_drift")
    return {
        "byte_length": len(data),
        "sha256": sha256(data),
        "complete_document": True,
        "model_count": len(models),
        "selector_count": len(selectors),
        "pin_count": len(pins),
    }


def validate(root: Path = ROOT, official_source: Path = DEFAULT_EXTERNAL) -> dict[str, Any]:
    manifest = load_yaml(root / MANIFEST.relative_to(ROOT))
    if manifest.get("schema") != SCHEMA:
        raise SelectedModelGrammarError("manifest_schema_drift")
    if manifest.get("status") != "bounded_explicit_grammar_consumer_closed_external_profile_missing":
        raise SelectedModelGrammarError("manifest_status_drift")
    if manifest.get("policy") != POLICY:
        raise SelectedModelGrammarError("policy_drift")
    grammar = manifest.get("grammar", {})
    for field in (
        "signal_or_pin_role_required",
        "direct_model_or_selector_branch_required",
        "corner_required",
        "voltage_v_required",
        "temperature_c_required",
        "table_family_required",
    ):
        if grammar.get(field) is not True:
            raise SelectedModelGrammarError(f"grammar_drift:{field}")
    if grammar.get("defaults") != "forbidden" or grammar.get("selector_branch_position_fallback") != "forbidden":
        raise SelectedModelGrammarError("grammar_drift:defaults_or_position_fallback")
    consumer = manifest.get("consumer", {})
    for field in ("complete_document_required", "final_end_payload_free_required", "unique_role_required", "unique_target_required", "unique_table_family_required"):
        if consumer.get(field) is not True:
            raise SelectedModelGrammarError(f"consumer_drift:{field}")
    for field in ("table_values_evaluated", "transient", "ami_runtime"):
        if consumer.get(field) is not False:
            raise SelectedModelGrammarError(f"consumer_boundary_drift:{field}")

    implementation_spec = manifest.get("implementation", {})
    if implementation_spec.get("path") != IMPLEMENTATION.relative_to(ROOT).as_posix():
        raise SelectedModelGrammarError("implementation_path_drift")
    implementation = root / IMPLEMENTATION.relative_to(ROOT)
    if sha256(implementation.read_bytes()) != implementation_spec.get("sha256"):
        raise SelectedModelGrammarError("implementation_hash_drift")
    for token in (
        "pub struct SelectedModelConsumerV1",
        "IbisTypedInventoryServiceV1::inspect",
        "SignalPinRoleV1",
        "SelectedModelTargetV1",
        "CornerPvtV1",
        "TableFamilyV1",
        "RoleAmbiguous",
        "SelectorBranchAmbiguous",
        "TableFamilyAmbiguous",
        "TableFamilyEmpty",
        "SELECTED_MODEL_POLICY_V1",
    ):
        if token not in implementation.read_text(encoding="utf-8"):
            raise SelectedModelGrammarError(f"implementation_token_missing:{token}")

    runner_spec = manifest.get("runner", {})
    if runner_spec.get("path") != RUNNER.relative_to(ROOT).as_posix():
        raise SelectedModelGrammarError("runner_path_drift")
    runner = root / RUNNER.relative_to(ROOT)
    if sha256(runner.read_bytes()) != runner_spec.get("sha256"):
        raise SelectedModelGrammarError("runner_hash_drift")
    runner_text = runner.read_text(encoding="utf-8")
    for token in (
        "--request",
        "--marker",
        "missing_required_selected_profile",
        "IbisTypedInventoryServiceV1::inspect",
        '"selector_branch"',
        'reject_unknown_keys(target, &["kind", "model"])',
        'reject_unknown_keys(target, &["kind", "selector", "branch"])',
    ):
        if token not in runner_text:
            raise SelectedModelGrammarError(f"runner_token_missing:{token}")

    for field, path in (("spec", SPEC), ("audit", AUDIT)):
        if manifest.get(field, {}).get("path") != path.relative_to(ROOT).as_posix():
            raise SelectedModelGrammarError(f"{field}_path_drift")
        if not (root / path.relative_to(ROOT)).is_file():
            raise SelectedModelGrammarError(f"{field}_missing")
    spec_text = (root / SPEC.relative_to(ROOT)).read_text(encoding="utf-8")
    for token in ("signal", "pin", "corner", "PVT", "table family", "no defaults", "[End]"):
        if token.lower() not in spec_text.lower():
            raise SelectedModelGrammarError(f"spec_token_missing:{token}")

    evidence_spec = manifest.get("evidence", {})
    if evidence_spec.get("path") != EVIDENCE.relative_to(ROOT).as_posix():
        raise SelectedModelGrammarError("evidence_path_drift")
    evidence_path = root / EVIDENCE.relative_to(ROOT)
    if sha256(evidence_path.read_bytes()) != evidence_spec.get("sha256"):
        raise SelectedModelGrammarError("evidence_hash_drift")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("schema") != "sipi.p4a-03bk.selected-model-crosscheck-evidence.v1":
        raise SelectedModelGrammarError("evidence_schema_drift")
    if evidence.get("status") != "matched_synthetic_and_external_missing_profile":
        raise SelectedModelGrammarError("evidence_status_drift")
    if evidence.get("policy") != POLICY or evidence.get("promotion_eligible") is not False:
        raise SelectedModelGrammarError("evidence_boundary_drift")
    synthetic = evidence.get("synthetic", {})
    if synthetic.get("case_count") != synthetic.get("matched_count") or synthetic.get("case_count", 0) < 4:
        raise SelectedModelGrammarError("synthetic_evidence_drift")
    external = evidence.get("external_official", {})
    if external.get("matched") is not True or external.get("selection_status") != "missing_required_selected_profile":
        raise SelectedModelGrammarError("external_evidence_drift")

    if not official_source.is_file():
        raise SelectedModelGrammarError("external_source_missing")
    observed = observe_complete_external(official_source.read_bytes())
    for field in ("byte_length", "sha256", "complete_document", "model_count", "selector_count", "pin_count"):
        if external.get(field) != observed[field]:
            raise SelectedModelGrammarError(f"external_identity_drift:{field}")
    if manifest.get("external_official_observation", {}).get("selected_profile_status") != "missing_required_selected_profile":
        raise SelectedModelGrammarError("manifest_external_profile_drift")
    if manifest.get("disposition", {}).get("p4a_03_external_profile_oracle") != "blocked_external_asset_oracle":
        raise SelectedModelGrammarError("disposition_drift")
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": manifest["status"],
        "synthetic_cases": synthetic["case_count"],
        "external_model_count": observed["model_count"],
        "external_selection_status": external["selection_status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--official-source", type=Path, default=DEFAULT_EXTERNAL)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.official_source)
    except (OSError, ValueError, yaml.YAMLError, SelectedModelGrammarError) as error:
        result = {"schema": SCHEMA, "valid": False, "reason": str(error)}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
