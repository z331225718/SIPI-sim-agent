"""Fail closed on the selected high-loss waveform-only v3 boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/baselines/p3c-selected-highloss-prbs9-waveform-only-contract.v3.yaml"
CORE = ROOT / "docs/baselines/p3c-selected-highloss-prbs9-waveform-only-core.v3.yaml"
CLI = ROOT / "docs/baselines/p3c-selected-highloss-prbs9-waveform-only-cli.v3.yaml"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
CONTRACT_SHA256 = "db0d9a663b311105be329d79060f05a5179f40fd7eccf448faf85d45b73da64a"


class WaveformOnlyError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WaveformOnlyError("document_not_mapping")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_document(document: object, *, root: Path = ROOT) -> dict[str, Any]:
    contract = load(root / CONTRACT.relative_to(ROOT))
    core = load(root / CORE.relative_to(ROOT))
    cli = load(root / CLI.relative_to(ROOT))
    if document != contract or digest(root / CONTRACT.relative_to(ROOT)) != CONTRACT_SHA256:
        raise WaveformOnlyError("contract_v3_drift")
    if contract.get("schema") != "sipi.p3c-selected-highloss-prbs9-waveform-only-contract.v3":
        raise WaveformOnlyError("contract_schema_invalid")
    if contract.get("supersedes", {}).get("content_sha256") != "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5":
        raise WaveformOnlyError("supersedes_binding_invalid")
    compare = contract.get("waveform_compare")
    if not isinstance(compare, dict) or compare != {
        "unit": "volts_differential", "alignment": "prohibited", "resampling": "prohibited",
        "gain_fit": "prohibited", "dc_removal": "prohibited", "polarity_flip": "prohibited",
        "formula": "sqrt(sum((candidate-reference)^2)/sum(reference^2))",
        "zero_reference_norm": "reject", "relative_rms_error_limit": 0.01,
    }:
        raise WaveformOnlyError("waveform_semantics_drift")
    excluded = "excluded_not_evaluated_for_this_selected_closed_eye_profile"
    if contract.get("eye", {}).get("status") != excluded or contract.get("jitter", {}).get("status") != excluded:
        raise WaveformOnlyError("excluded_metric_semantics_drift")
    if core.get("contract_binding") != {"content_sha256": CONTRACT_SHA256, "path": "docs/baselines/p3c-selected-highloss-prbs9-waveform-only-contract.v3.yaml"}:
        raise WaveformOnlyError("core_contract_binding_drift")
    if core.get("implementation") != {"crate": "sipi-compare", "module": "selected_highloss_prbs9_waveform_only_v3", "public_entrypoint": "compare_selected_highloss_prbs9_waveform_only_v3"}:
        raise WaveformOnlyError("core_implementation_drift")
    if core.get("profile", {}).get("sampled_eye") != excluded or core.get("profile", {}).get("crossing_tie") != excluded:
        raise WaveformOnlyError("core_exclusion_drift")
    if any(core.get("admission", {}).get(key) is not False for key in ("external_reference_bound_to_v3_waveform_input", "waveform_nrmse_evaluated", "sampled_eye_evaluated", "crossing_tie_evaluated", "selected_highloss_waveform_only_profile_accepted", "accepted_receiver", "acceptance_ready", "promotion_eligible", "release_ledger_promoted")):
        raise WaveformOnlyError("core_admission_drift")
    if cli.get("command", {}).get("id") != "compare.prbs9-waveform-only.run" or cli["command"].get("contract_v3_content_sha256") != CONTRACT_SHA256:
        raise WaveformOnlyError("cli_command_binding_drift")
    if cli.get("response", {}).get("sampled_eye") != excluded or cli.get("response", {}).get("crossing_tie") != excluded:
        raise WaveformOnlyError("cli_exclusion_drift")
    if any(cli.get("admission", {}).get(key) is not False for key in ("product_waveform_only_cli_invoked", "external_reference_bound_to_v3_waveform_input", "selected_highloss_waveform_only_profile_accepted", "sampled_eye_evaluated", "crossing_tie_evaluated", "accepted_receiver", "acceptance_ready", "promotion_eligible", "release_ledger_promoted")):
        raise WaveformOnlyError("cli_admission_drift")
    source = (root / "crates/sipi-compare/src/selected_highloss_prbs9_waveform_only_v3.rs").read_text(encoding="utf-8")
    required = (CONTRACT_SHA256, "pub fn compare_selected_highloss_prbs9_waveform_only_v3", "SELECTED_HIGHLOSS_PRBS9_WAVEFORM_NRMSE_LIMIT_V3: f64 = 0.01")
    forbidden = ("compare_prbs9_metrics_v2", "eye_metric")
    if any(token not in source for token in required) or any(token in source.split("#[cfg(test)]")[0] for token in forbidden):
        raise WaveformOnlyError("core_source_boundary_drift")
    cli_source = (root / "crates/sipi-cli/src/main.rs").read_text(encoding="utf-8")
    required_cli = ("compare.prbs9-waveform-only.run", "compare_selected_highloss_prbs9_waveform_only_v3", "parse_selected_highloss_prbs9_waveform_only_artifact_v3", excluded)
    if any(token not in cli_source for token in required_cli):
        raise WaveformOnlyError("cli_source_binding_drift")
    inventory = json.loads(
        (root / "crates/sipi-contracts/schemas/schema-inventory.v1.json").read_text(encoding="utf-8")
    )
    expected_schema = {
        "id": "sipi.compare.selected-highloss-prbs9-waveform-only-artifacts-request.v3",
        "path": "crates/sipi-contracts/schemas/sipi.compare.selected-highloss-prbs9-waveform-only-artifacts-request.v3.schema.json",
        "sha256": "5ff8bb55c403b13fd914deb22c441bd0c10b24ae5f189db6f3f876b5da1bda9e",
        "textFileFinalLfNotExported": True,
    }
    if inventory.get("schema") != "sipi.product-schema-inventory.v1" or expected_schema not in inventory.get("entries", []):
        raise WaveformOnlyError("schema_inventory_binding_drift")
    publication = json.loads((root / PUBLICATION.relative_to(ROOT)).read_text(encoding="utf-8"))
    row = next((row for row in publication.get("rows", []) if row.get("id") == "selected-highloss-prbs9-waveform-only-compare"), None)
    if not isinstance(row, dict) or row.get("command_id") != "compare.prbs9-waveform-only.run" or row.get("acceptance_state") != "specified" or row.get("external_oracle") is not False or "selected_profile_acceptance_not_evaluated" not in row.get("blockers", []):
        raise WaveformOnlyError("publication_row_drift")
    return {"schema": contract["schema"], "status": contract["status"], "selected_profile_only": True, "release_promoted": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    arguments = parser.parse_args(argv)
    try:
        print(json.dumps(verify_document(load(arguments.contract)), sort_keys=True))
    except (OSError, ValueError, yaml.YAMLError, WaveformOnlyError) as error:
        print(json.dumps({"schema": "sipi.p3c-selected-highloss-prbs9-waveform-only-contract.v3", "status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
