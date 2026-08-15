"""Verify and render the provisional P7-05a capability/evidence publication."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from verify_tran_rc_pulse_acceptance import _load as load_yaml
from verify_tran_rc_pulse_current_external_compare_evidence_v2 import EvidenceError, verify_document as verify_tran_evidence
from verify_channel_s2p_matched_cli_current_external_compare_evidence_v3 import (
    EvidenceError as ChannelEvidenceError,
    verify_document as verify_channel_cli_evidence,
)
from verify_channel_s2p_matched_cli_current_external_compare_evidence_v4 import (
    EvidenceError as CurrentChannelEvidenceError,
    verify_document as verify_current_channel_cli_evidence,
)
from verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight import (
    PreflightError as AmiPreflightError,
    verify_manifest as verify_ami_preflight,
)
from verify_p4b_dual_ami_pe_loader_declarations import (
    GateError as AmiLoaderDeclarationError,
    verify as verify_ami_loader_declarations,
)
from verify_p3b_link_stage_capabilities import verify as verify_link_stage_capabilities


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.release-capability-publication.v1"
COMMAND_SCHEMA = "sipi.command-manifest.v1"
PUBLICATION = ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml"
FORBIDDEN_TOKENS = ("certified", "release-ready", "release_ready", "legal approved", "legally approved")
SAFE_REPORT_ROOT = Path("docs/baselines")
COMMAND_DESCRIPTOR_FIELDS = {
    "id", "route", "availability", "transport", "request_schema",
    "response_schema", "unavailable_reason", "nonclaim",
}
COMMAND_ID = re.compile(r"[a-z0-9][a-z0-9.-]*")
ROUTE_TOKEN = re.compile(r"[a-z][a-z0-9-]*")
ACCEPTANCE_AUTHORITY_ROWS_V1 = frozenset({"tran-rc-pulse"})
COM_R480_ACCEPTANCE_SHA256 = "e90fca0d14968a04e09df90cd8bd4fcc7f749abfa07ad2b4b29dc297351ef03b"
P3B_RECEIVER_DIAGNOSTIC_AUDIT_SHA256 = "ff59135f5339798c86d908fef388d3b3c873af32ec23d984a0f6cfdf963105e8"
P3C_ARRAY_COMPARE_AUDIT_SHA256 = "25e7bcb2bb06c1c6978a3c6f0466cb18634d9ff72beb28e610f5831f0ac3cfce"
P3C_ALIGNED_ARRAY_COMPARE_CLI_AUDIT_SHA256 = "0d2dada97845e901f95ec164aec3794bf0a8f827a4602d28d08e2f1a35877f64"
P6_FIXED_PROJECT_CLI_AUDIT_SHA256 = "ff51578cf1ec1ee24fe0d126d3d3d0770f22e997a7befd1739c0061e48af3975"
P3B_LINK_STAGE_LEDGER_SHA256 = "0055a9fcdfd875f447a4e6ffe978f99d11ab6c03068c6748a358ea81fbfe3751"
P6_ARTIFACT_REPORT_AUDIT_SHA256 = "4574bf42788a087e9947f6017194a0cb75a5bdc7f1238143e79c110f18ba3226"
P7_ISOLATED_INSTALL_AUDIT_SHA256 = "8682cd4718c4a9dbaf57635fe0386d159f2c54cc11a361c90566967bc6a3fb66"
P2_ONE_NODE_RC_PULSE_CLI_AUDIT_SHA256 = "3fe3222b08b4b8e0026357b690db3daa5e190b230b92d6cac4baf6d2e8606738"
PRODUCT_OWNED_UNAVAILABLE_CATALOG_ROUTES_V1 = {
    "project-validate": {
        "domain": "project",
        "command_id": "project.validate",
        "route": ["project", "validate"],
        "reason": "project_execution_not_implemented",
        "nonclaim": "no_project_execution",
    },
    "report-show": {
        "domain": "report",
        "command_id": "report.show",
        "route": ["report", "show"],
        "reason": "artifact_payload_preview_not_implemented",
        "nonclaim": "no_payload_or_external_provenance_viewer",
    },
}


class PublicationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicationError("invalid_json") from error
    if not isinstance(value, dict):
        raise PublicationError("document_not_object")
    return value


def command_manifest(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema") == "sipi.cli.response.v1":
        expected = {"schema", "protocol", "command", "request_id", "status", "result", "diagnostic_count"}
        if (
            set(document) != expected
            or document["protocol"] != 1
            or document["command"] != "commands"
            or document["request_id"] is not None
            or document["status"] != "ok"
            or document["diagnostic_count"] != 0
        ):
            raise PublicationError("command_manifest_invalid")
        result = document["result"]
    else:
        result = document
    if not isinstance(result, dict) or result.get("schema") != COMMAND_SCHEMA:
        raise PublicationError("command_manifest_invalid")
    if set(result) != {"schema", "commands"}:
        raise PublicationError("command_manifest_invalid")
    commands = result.get("commands")
    if not isinstance(commands, list) or not commands:
        raise PublicationError("command_manifest_invalid")
    validate_command_descriptors(commands)
    return commands


def validate_command_descriptors(commands: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    seen_routes: set[tuple[str, ...]] = set()
    for command in commands:
        if not isinstance(command, dict) or set(command) != COMMAND_DESCRIPTOR_FIELDS:
            raise PublicationError("command_manifest_invalid")
        command_id = command["id"]
        route = command["route"]
        availability = command["availability"]
        transport = command["transport"]
        schemas = (command["request_schema"], command["response_schema"])
        reason = command["unavailable_reason"]
        nonclaim = command["nonclaim"]
        if (
            not isinstance(command_id, str)
            or not COMMAND_ID.fullmatch(command_id)
            or command_id in seen_ids
            or not isinstance(route, list)
            or not route
            or any(not isinstance(token, str) or not ROUTE_TOKEN.fullmatch(token) for token in route)
            or tuple(route) in seen_routes
            or availability not in {"available", "unavailable"}
            or transport not in {"none", "stdin_json_v1"}
            or any(value is not None and (not isinstance(value, str) or not value) for value in schemas)
            or not isinstance(nonclaim, str)
            or not nonclaim
            or (availability == "available" and reason is not None)
            or (availability == "unavailable" and (not isinstance(reason, str) or not reason))
        ):
            raise PublicationError("command_manifest_invalid")
        seen_ids.add(command_id)
        seen_routes.add(tuple(route))


def safe_report_path(relative: str) -> bool:
    path = Path(relative)
    return (
        path.is_relative_to(SAFE_REPORT_ROOT)
        and not path.is_absolute()
        and ".." not in path.parts
        and path.suffix in {".md", ".yaml", ".json"}
    )


def has_forbidden_token(value: object) -> bool:
    if isinstance(value, str):
        text = value.lower()
        return any(re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", text) for token in FORBIDDEN_TOKENS)
    if isinstance(value, list):
        return any(has_forbidden_token(item) for item in value)
    if isinstance(value, dict):
        return any(has_forbidden_token(item) for item in value.values())
    return False


def validate(publication: dict[str, Any], manifest: list[dict[str, Any]], root: Path) -> None:
    required = {
        "schema", "publication_scope", "release_ready", "promotion_status",
        "global_blockers", "non_claims", "rows", "report_index",
    }
    if set(publication) != required or publication["schema"] != SCHEMA:
        raise PublicationError("publication_schema_invalid")
    if publication["publication_scope"] != "pre_release_evidence" or publication["release_ready"] is not False:
        raise PublicationError("publication_promotion_invalid")
    if publication["promotion_status"] != "blocked" or has_forbidden_token(publication):
        raise PublicationError("publication_promotion_invalid")
    for key in ("global_blockers", "non_claims"):
        value = publication[key]
        if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
            raise PublicationError("publication_global_fields_invalid")

    validate_command_descriptors(manifest)
    manifest_by_id = {item.get("id"): item for item in manifest}
    if len(manifest_by_id) != len(manifest) or None in manifest_by_id:
        raise PublicationError("command_manifest_duplicate")
    rows = publication["rows"]
    if not isinstance(rows, list) or not rows:
        raise PublicationError("publication_rows_invalid")
    row_ids: set[str] = set()
    command_rows: dict[str, dict[str, Any]] = {}
    allowed_states = {"accepted", "blocked", "specified", "not_evaluated"}
    for row in rows:
        expected = {
            "id", "domain", "product_surface", "command_id", "acceptance_state", "platform",
            "evidence_ids", "external_oracle", "blockers", "non_claims",
        }
        if not isinstance(row, dict) or set(row) != expected:
            raise PublicationError("publication_row_schema_invalid")
        row_id = row["id"]
        if not isinstance(row_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", row_id) or row_id in row_ids:
            raise PublicationError("publication_row_id_invalid")
        row_ids.add(row_id)
        command_id = row["command_id"]
        command = manifest_by_id.get(command_id)
        if command is None or command_id in command_rows:
            raise PublicationError("publication_command_binding_invalid")
        command_rows[command_id] = row
        expected_surface = command.get("availability")
        if row["product_surface"] != expected_surface or expected_surface not in {"available", "unavailable"}:
            raise PublicationError("publication_command_status_drift")
        if row["acceptance_state"] not in allowed_states or row["platform"] != "windows_x86_64":
            raise PublicationError("publication_state_invalid")
        if not isinstance(row["external_oracle"], bool):
            raise PublicationError("publication_oracle_invalid")
        for key in ("evidence_ids", "blockers", "non_claims"):
            values = row[key]
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                raise PublicationError("publication_row_lists_invalid")
        if row["acceptance_state"] == "blocked" and not row["blockers"]:
            raise PublicationError("publication_blocker_missing")
        if (
            (row["product_surface"] == "available" and row["acceptance_state"] == "blocked")
            or (row["product_surface"] == "unavailable" and row["acceptance_state"] != "blocked")
        ):
            raise PublicationError("publication_surface_state_invalid")
    if set(command_rows) != set(manifest_by_id):
        raise PublicationError("publication_command_coverage_missing")

    index = publication["report_index"]
    if not isinstance(index, list) or not index:
        raise PublicationError("publication_index_invalid")
    index_by_id: dict[str, dict[str, Any]] = {}
    for entry in index:
        expected = {"id", "kind", "path", "subject", "evidence_state"}
        if not isinstance(entry, dict) or set(entry) != expected:
            raise PublicationError("publication_index_schema_invalid")
        entry_id = entry["id"]
        if not isinstance(entry_id, str) or entry_id in index_by_id or not safe_report_path(entry["path"]):
            raise PublicationError("publication_index_path_invalid")
        if not (root / entry["path"]).is_file():
            raise PublicationError("publication_index_missing_file")
        if entry["evidence_state"] not in {"specified", "observed", "blocked"}:
            raise PublicationError("publication_index_state_invalid")
        index_by_id[entry_id] = entry
    if any(evidence not in index_by_id for row in rows for evidence in row["evidence_ids"]):
        raise PublicationError("publication_evidence_reference_invalid")
    _validate_profile_scoped_external_acceptance(rows, index_by_id)
    _validate_prbs9_artifact_metric_route(rows, index_by_id)
    _validate_selected_highloss_waveform_only_route(rows, index_by_id)
    _validate_ami_blocked_route(rows, index_by_id)
    _validate_com_blocked_route(rows, index_by_id, root)
    _validate_product_owned_unavailable_catalog_routes(rows, manifest_by_id, index_by_id)
    _validate_receiver_diagnostic_route(rows, manifest_by_id, index_by_id, root)
    _validate_aligned_array_compare_route(rows, manifest_by_id, index_by_id, root)
    _validate_fixed_project_run_route(rows, manifest_by_id, index_by_id, root)
    _validate_causal_fir_link_route(rows, manifest_by_id, index_by_id, root)
    _validate_artifact_report_inspect_route(rows, manifest_by_id, index_by_id, root)
    _validate_one_node_rc_pulse_route(rows, manifest_by_id, index_by_id, root)
    _validate_accepted_evidence_authority(rows)


def _validate_accepted_evidence_authority(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if row["acceptance_state"] == "accepted" and row["id"] not in ACCEPTANCE_AUTHORITY_ROWS_V1:
            raise PublicationError("publication_acceptance_authority_missing")


def _validate_prbs9_artifact_metric_route(
    rows: list[dict[str, Any]], index_by_id: dict[str, dict[str, Any]]
) -> None:
    row = next((item for item in rows if item["id"] == "prbs9-metric-artifact-compare"), None)
    evidence_id = "p3c-prbs9-metric-artifact-cli"
    expected_blockers = {
        "caller_supplied_artifact_identity_only",
        "external_reference_binding_not_implemented",
        "candidate_profile_acceptance_not_evaluated",
        "accepted_receiver_stage_missing",
    }
    if (
        row is None
        or row["command_id"] != "compare.prbs9-metrics.run"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or evidence_id not in row["evidence_ids"]
        or not expected_blockers.issubset(row["blockers"])
    ):
        raise PublicationError("publication_prbs9_artifact_metric_binding_invalid")
    evidence = index_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence["kind"] != "capability_contract"
        or evidence["subject"] != "compare"
        or evidence["evidence_state"] != "specified"
    ):
        raise PublicationError("publication_prbs9_artifact_metric_evidence_invalid")


def _validate_selected_highloss_waveform_only_route(
    rows: list[dict[str, Any]], index_by_id: dict[str, dict[str, Any]]
) -> None:
    row = next((item for item in rows if item["id"] == "selected-highloss-prbs9-waveform-only-compare"), None)
    evidence_id = "p3c-selected-highloss-prbs9-waveform-only-cli"
    expected_blockers = {
        "caller_supplied_artifact_identity_only",
        "external_reference_binding_not_implemented",
        "selected_profile_acceptance_not_evaluated",
        "accepted_receiver_stage_missing",
        "statistical_eye_contour_semantics_missing",
    }
    expected_nonclaim = "not_general_closed_eye_fallback_or_receiver_or_release_acceptance"
    if (
        row is None
        or row["command_id"] != "compare.prbs9-waveform-only.run"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or evidence_id not in row["evidence_ids"]
        or not expected_blockers.issubset(row["blockers"])
        or expected_nonclaim not in row["non_claims"]
    ):
        raise PublicationError("publication_selected_highloss_waveform_only_binding_invalid")
    evidence = index_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence["kind"] != "capability_contract"
        or evidence["path"] != "docs/baselines/p3c-selected-highloss-prbs9-waveform-only-cli.v3.yaml"
        or evidence["subject"] != "compare"
        or evidence["evidence_state"] != "specified"
    ):
        raise PublicationError("publication_selected_highloss_waveform_only_evidence_invalid")


def _validate_ami_blocked_route(rows: list[dict[str, Any]], index_by_id: dict[str, dict[str, Any]]) -> None:
    row = next((item for item in rows if item["id"] == "ami"), None)
    preflight_id = "p4b-dual-ami-asset-preflight"
    declarations_id = "p4b-dual-ami-pe-loader-declarations"
    expected_blocker = "external_ami_asset_not_admitted"
    expected_nonclaim = "no_vendor_dll_or_ami_workflow"
    if (
        row is None
        or row["command_id"] != "ami.run"
        or row["product_surface"] != "unavailable"
        or row["acceptance_state"] != "blocked"
        or row["external_oracle"] is not True
        or expected_blocker not in row["blockers"]
        or expected_nonclaim not in row["non_claims"]
        or preflight_id not in row["evidence_ids"]
        or declarations_id not in row["evidence_ids"]
    ):
        raise PublicationError("publication_ami_blocked_route_binding_invalid")

    expected_entries = {
        preflight_id: "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml",
        declarations_id: "docs/baselines/p4b-dual-ami-pe-loader-declarations.v1.yaml",
    }
    for evidence_id, path in expected_entries.items():
        evidence = index_by_id.get(evidence_id)
        if (
            evidence is None
            or evidence["kind"] != "blocked_evidence"
            or evidence["path"] != path
            or evidence["subject"] != "ami"
            or evidence["evidence_state"] != "observed"
        ):
            raise PublicationError("publication_ami_blocked_evidence_invalid")

    try:
        preflight = verify_ami_preflight(ROOT, load_yaml(ROOT / expected_entries[preflight_id]))
        declarations = verify_ami_loader_declarations(
            load_yaml(ROOT / expected_entries[declarations_id]), root=ROOT
        )
    except (AmiPreflightError, AmiLoaderDeclarationError, OSError, RuntimeError, ValueError):
        raise PublicationError("publication_ami_blocked_evidence_invalid") from None
    if (
        preflight.get("worker_admitted") is not False
        or preflight.get("runtime_evidence") is not False
        or preflight.get("release_input") is not False
        or declarations.get("worker_admitted") is not False
        or declarations.get("runtime_invoked") is not False
        or declarations.get("dynamic_closure") != "blocked_not_assessed"
    ):
        raise PublicationError("publication_ami_blocked_evidence_promoted")


def _validate_com_blocked_route(
    rows: list[dict[str, Any]], index_by_id: dict[str, dict[str, Any]], root: Path
) -> None:
    row = next((item for item in rows if item["id"] == "com"), None)
    evidence_id = "com-r480-acceptance"
    path = "docs/baselines/com-r480-acceptance.v1.yaml"
    if (
        row is None
        or row["command_id"] != "com.run"
        or row["product_surface"] != "unavailable"
        or row["acceptance_state"] != "blocked"
        or row["external_oracle"] is not True
        or "authoritative_reference_missing" not in row["blockers"]
        or "no_com_solver_or_oracle_workflow" not in row["non_claims"]
        or evidence_id not in row["evidence_ids"]
    ):
        raise PublicationError("publication_com_blocked_route_binding_invalid")
    evidence = index_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence["kind"] != "acceptance_contract"
        or evidence["path"] != path
        or evidence["subject"] != "com"
        or evidence["evidence_state"] != "blocked"
    ):
        raise PublicationError("publication_com_blocked_evidence_invalid")
    document_path = root / path
    try:
        if hashlib.sha256(document_path.read_bytes()).hexdigest() != COM_R480_ACCEPTANCE_SHA256:
            raise PublicationError("publication_com_blocked_evidence_invalid")
        document = load_yaml(document_path)
    except (OSError, RuntimeError, ValueError):
        raise PublicationError("publication_com_blocked_evidence_invalid") from None
    if (
        document.get("schema") != "sipi.com.r480.acceptance.v1"
        or document.get("authoritative_reference", {}).get("status") != "missing"
        or document.get("authoritative_reference", {}).get("external_custody") != "required"
        or document.get("comparison", {}).get("status") != "blocked_missing_authoritative_reference"
        or document.get("comparison", {}).get("result_status") != "not_run"
        or document.get("comparison", {}).get("product_self_comparison") != "forbidden"
        or document.get("product_contract", {}).get("status") != "independent_clean_room_spec_required"
        or document.get("external_materials", {}).get("product_material") != "prohibited"
    ):
        raise PublicationError("publication_com_blocked_evidence_promoted")


def _validate_product_owned_unavailable_catalog_routes(
    rows: list[dict[str, Any]], manifest_by_id: dict[str, dict[str, Any]], index_by_id: dict[str, dict[str, Any]]
) -> None:
    evidence_id = "p6-command-manifest"
    evidence = index_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence["kind"] != "capability_contract"
        or evidence["path"] != "docs/baselines/audits/2026-08-11-p6-command-manifest.md"
        or evidence["subject"] != "foundation"
        or evidence["evidence_state"] != "specified"
    ):
        raise PublicationError("publication_product_unavailable_catalog_evidence_invalid")

    rows_by_id = {row["id"]: row for row in rows}
    for row_id, expected in PRODUCT_OWNED_UNAVAILABLE_CATALOG_ROUTES_V1.items():
        row = rows_by_id.get(row_id)
        command = manifest_by_id.get(expected["command_id"])
        if (
            row is None
            or row["domain"] != expected["domain"]
            or row["command_id"] != expected["command_id"]
            or row["product_surface"] != "unavailable"
            or row["acceptance_state"] != "blocked"
            or row["external_oracle"] is not False
            or row["evidence_ids"] != [evidence_id]
            or row["blockers"] != [expected["reason"]]
            or row["non_claims"] != [expected["nonclaim"]]
            or command is None
            or command["route"] != expected["route"]
            or command["availability"] != "unavailable"
            or command["transport"] != "none"
            or command["request_schema"] is not None
            or command["response_schema"] is not None
            or command["unavailable_reason"] != expected["reason"]
            or command["nonclaim"] != expected["nonclaim"]
        ):
            raise PublicationError("publication_product_unavailable_catalog_binding_invalid")


def _validate_receiver_diagnostic_route(
    rows: list[dict[str, Any]], manifest_by_id: dict[str, dict[str, Any]],
    index_by_id: dict[str, dict[str, Any]], root: Path,
) -> None:
    ledger_id = "link-stage-ledger"
    audit_id = "p3b-receiver-diagnostic-cli"
    ledger_path = "docs/baselines/p3b-link-stage-capability-ledger.v1.yaml"
    audit_path = "docs/baselines/audits/2026-08-11-p3b-receiver-diagnostic-cli.md"
    row = next((item for item in rows if item["id"] == "link-receiver-diagnostic"), None)
    command = manifest_by_id.get("link.receiver.run")
    if (
        row is None
        or row["domain"] != "receiver"
        or row["command_id"] != "link.receiver.run"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or row["evidence_ids"] != [ledger_id, audit_id]
        or row["blockers"] != [
            "caller_supplied_input_only",
            "policy_selected_not_locked",
            "required_rfm_profile_not_accepted",
        ]
        or row["non_claims"] != ["not_rfm_receiver_parity_or_clock_recovery"]
        or command is None
        or command["route"] != ["link", "receiver", "run"]
        or command["availability"] != "available"
        or command["transport"] != "stdin_json_v1"
        or command["request_schema"] != "sipi.receiver.diagnostic-run-request.v1"
        or command["response_schema"] != "sipi.receiver.diagnostic-run-result.v1"
        or command["unavailable_reason"] is not None
        or command["nonclaim"] != "product_owned_diagnostic_not_rfm_parity_or_clock_lock"
    ):
        raise PublicationError("publication_receiver_diagnostic_route_binding_invalid")

    expected_index = {
        ledger_id: ("capability_ledger", ledger_path, "link", "specified"),
        audit_id: ("capability_contract", audit_path, "receiver", "specified"),
    }
    for evidence_id, (kind, path, subject, evidence_state) in expected_index.items():
        evidence = index_by_id.get(evidence_id)
        if (
            evidence is None
            or evidence["kind"] != kind
            or evidence["path"] != path
            or evidence["subject"] != subject
            or evidence["evidence_state"] != evidence_state
        ):
            raise PublicationError("publication_receiver_diagnostic_evidence_invalid")

    try:
        audit_sha256 = hashlib.sha256((root / audit_path).read_bytes()).hexdigest()
        ledger = load_yaml(root / ledger_path)
        result = verify_link_stage_capabilities(ledger)
    except (OSError, RuntimeError, ValueError):
        raise PublicationError("publication_receiver_diagnostic_ledger_invalid") from None
    if audit_sha256 != P3B_RECEIVER_DIAGNOSTIC_AUDIT_SHA256:
        raise PublicationError("publication_receiver_diagnostic_evidence_invalid")
    entries = {
        entry.get("id"): entry
        for entry in ledger.get("entries", [])
        if isinstance(entry, dict)
    } if isinstance(ledger, dict) else {}
    if (
        result.get("valid") is not True
        or result.get("entry_count") != 13
        or entries.get("fixed_receiver_library", {}).get("disposition") != "library_only_profile_blocked"
        or entries.get("fixed_receiver_diagnostic_cli", {}).get("disposition") != "product_owned_diagnostic"
        or entries.get("fixed_receiver_diagnostic_cli", {}).get("non_claim") != "not_rfm_parity_or_clock_lock"
    ):
        raise PublicationError("publication_receiver_diagnostic_ledger_invalid")


def _validate_aligned_array_compare_route(
    rows: list[dict[str, Any]], manifest_by_id: dict[str, dict[str, Any]],
    index_by_id: dict[str, dict[str, Any]], root: Path,
) -> None:
    substrate_id = "p3c-array-compare"
    cli_id = "p3c-aligned-array-compare-cli"
    substrate_path = "docs/baselines/audits/2026-08-11-p3c-array-compare.md"
    cli_path = "docs/baselines/audits/2026-08-11-p3c-aligned-array-compare-cli.md"
    row = next((item for item in rows if item["id"] == "compare"), None)
    command = manifest_by_id.get("compare.run")
    if (
        row is None
        or row["domain"] != "compare"
        or row["command_id"] != "compare.run"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or row["evidence_ids"] != [substrate_id, cli_id]
        or row["blockers"] != [
            "caller_supplied_alignment_and_semantic_binding",
            "metric_profile_semantics_not_implemented",
        ]
        or row["non_claims"] != ["not_eye_jitter_bathtub_ber_or_external_oracle_workflow"]
        or command is None
        or command["route"] != ["compare", "run"]
        or command["availability"] != "available"
        or command["transport"] != "stdin_json_v1"
        or command["request_schema"] != "sipi.compare.aligned-arrays-request.v1"
        or command["response_schema"] != "sipi.compare.aligned-arrays-run-result.v1"
        or command["unavailable_reason"] is not None
        or command["nonclaim"] != "caller_aligned_arrays_only"
    ):
        raise PublicationError("publication_aligned_array_compare_route_binding_invalid")

    expected_index = {
        substrate_id: ("product_contract", substrate_path, "compare", "specified", P3C_ARRAY_COMPARE_AUDIT_SHA256),
        cli_id: ("capability_contract", cli_path, "compare", "specified", P3C_ALIGNED_ARRAY_COMPARE_CLI_AUDIT_SHA256),
    }
    for evidence_id, (kind, path, subject, evidence_state, expected_sha256) in expected_index.items():
        evidence = index_by_id.get(evidence_id)
        if (
            evidence is None
            or evidence["kind"] != kind
            or evidence["path"] != path
            or evidence["subject"] != subject
            or evidence["evidence_state"] != evidence_state
        ):
            raise PublicationError("publication_aligned_array_compare_evidence_invalid")
        try:
            actual_sha256 = hashlib.sha256((root / path).read_bytes()).hexdigest()
        except OSError:
            raise PublicationError("publication_aligned_array_compare_evidence_invalid") from None
        if actual_sha256 != expected_sha256:
            raise PublicationError("publication_aligned_array_compare_evidence_invalid")


def _validate_fixed_project_run_route(
    rows: list[dict[str, Any]], manifest_by_id: dict[str, dict[str, Any]],
    index_by_id: dict[str, dict[str, Any]], root: Path,
) -> None:
    evidence_id = "p6-fixed-project-cli-run"
    path = "docs/baselines/audits/2026-08-11-p6-fixed-project-cli-run.md"
    row = next((item for item in rows if item["id"] == "project-run"), None)
    command = manifest_by_id.get("project.run")
    if (
        row is None
        or row["domain"] != "project"
        or row["command_id"] != "project.run"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or row["evidence_ids"] != [evidence_id]
        or row["blockers"] != ["single_fixed_project_topology_only"]
        or row["non_claims"] != ["not_a_generic_project_executor"]
        or command is None
        or command["route"] != ["project", "run"]
        or command["availability"] != "available"
        or command["transport"] != "stdin_json_v1"
        or command["request_schema"] != "sipi.project.fixed-tran-causal-fir-run-request.v1"
        or command["response_schema"] != "sipi.project.fixed-tran-causal-fir-run-result.v1"
        or command["unavailable_reason"] is not None
        or command["nonclaim"] != "one_fixed_composite_project_route_only"
    ):
        raise PublicationError("publication_fixed_project_run_route_binding_invalid")
    evidence = index_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence["kind"] != "capability_contract"
        or evidence["path"] != path
        or evidence["subject"] != "project"
        or evidence["evidence_state"] != "specified"
    ):
        raise PublicationError("publication_fixed_project_run_evidence_invalid")
    try:
        actual_sha256 = hashlib.sha256((root / path).read_bytes()).hexdigest()
    except OSError:
        raise PublicationError("publication_fixed_project_run_evidence_invalid") from None
    if actual_sha256 != P6_FIXED_PROJECT_CLI_AUDIT_SHA256:
        raise PublicationError("publication_fixed_project_run_evidence_invalid")


def _validate_causal_fir_link_route(
    rows: list[dict[str, Any]], manifest_by_id: dict[str, dict[str, Any]],
    index_by_id: dict[str, dict[str, Any]], root: Path,
) -> None:
    evidence_id = "link-stage-ledger"
    path = "docs/baselines/p3b-link-stage-capability-ledger.v1.yaml"
    row = next((item for item in rows if item["id"] == "link-causal-fir"), None)
    command = manifest_by_id.get("link.run")
    if (
        row is None
        or row["domain"] != "link"
        or row["command_id"] != "link.run"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or row["evidence_ids"] != [evidence_id]
        or row["blockers"] != ["no_required_link_profile_accepted"]
        or row["non_claims"] != ["not_s2p_or_receiver_parity"]
        or command is None
        or command["route"] != ["link", "run"]
        or command["availability"] != "available"
        or command["transport"] != "stdin_json_v1"
        or command["request_schema"] != "sipi.link.causal-fir-request.v1"
        or command["response_schema"] != "sipi.link.run-result.v1"
        or command["unavailable_reason"] is not None
        or command["nonclaim"] != "causal_fir_direct_launch_only"
    ):
        raise PublicationError("publication_causal_fir_link_route_binding_invalid")
    evidence = index_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence["kind"] != "capability_ledger"
        or evidence["path"] != path
        or evidence["subject"] != "link"
        or evidence["evidence_state"] != "specified"
    ):
        raise PublicationError("publication_causal_fir_link_evidence_invalid")
    try:
        actual_sha256 = hashlib.sha256((root / path).read_bytes()).hexdigest()
        ledger = load_yaml(root / path)
        result = verify_link_stage_capabilities(ledger)
    except (OSError, RuntimeError, ValueError):
        raise PublicationError("publication_causal_fir_link_ledger_invalid") from None
    if actual_sha256 != P3B_LINK_STAGE_LEDGER_SHA256:
        raise PublicationError("publication_causal_fir_link_evidence_invalid")
    if result.get("valid") is not True or result.get("entry_count") != 13:
        raise PublicationError("publication_causal_fir_link_ledger_invalid")


def _validate_artifact_report_inspect_route(
    rows: list[dict[str, Any]], manifest_by_id: dict[str, dict[str, Any]],
    index_by_id: dict[str, dict[str, Any]], root: Path,
) -> None:
    install_id = "p7-isolated-install"
    contract_id = "p6-artifact-report"
    row = next((item for item in rows if item["id"] == "report-inspect"), None)
    command = manifest_by_id.get("report.inspect")
    if (
        row is None
        or row["domain"] != "report"
        or row["command_id"] != "report.inspect"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or row["evidence_ids"] != [install_id, contract_id]
        or row["blockers"] != ["integrity_metadata_only"]
        or row["non_claims"] != ["not_payload_or_external_provenance_viewer"]
        or command is None
        or command["route"] != ["report", "inspect"]
        or command["availability"] != "available"
        or command["transport"] != "stdin_json_v1"
        or command["request_schema"] != "sipi.artifact-report-request.v1"
        or command["response_schema"] != "sipi.artifact-report.v1"
        or command["unavailable_reason"] is not None
        or command["nonclaim"] != "verified_integrity_metadata_only"
    ):
        raise PublicationError("publication_artifact_report_inspect_route_binding_invalid")
    expected_index = {
        install_id: (
            "install_observation", "docs/baselines/audits/2026-08-11-p7-isolated-install.md",
            "foundation", "observed", P7_ISOLATED_INSTALL_AUDIT_SHA256,
        ),
        contract_id: (
            "capability_contract", "docs/baselines/audits/2026-08-11-p6-artifact-report.md",
            "report", "specified", P6_ARTIFACT_REPORT_AUDIT_SHA256,
        ),
    }
    for evidence_id, (kind, path, subject, evidence_state, expected_sha256) in expected_index.items():
        evidence = index_by_id.get(evidence_id)
        if (
            evidence is None
            or evidence["kind"] != kind
            or evidence["path"] != path
            or evidence["subject"] != subject
            or evidence["evidence_state"] != evidence_state
        ):
            raise PublicationError("publication_artifact_report_inspect_evidence_invalid")
        try:
            actual_sha256 = hashlib.sha256((root / path).read_bytes()).hexdigest()
        except OSError:
            raise PublicationError("publication_artifact_report_inspect_evidence_invalid") from None
        if actual_sha256 != expected_sha256:
            raise PublicationError("publication_artifact_report_inspect_evidence_invalid")


def _validate_one_node_rc_pulse_route(
    rows: list[dict[str, Any]], manifest_by_id: dict[str, dict[str, Any]],
    index_by_id: dict[str, dict[str, Any]], root: Path,
) -> None:
    evidence_id = "p2-one-node-rc-pulse-cli"
    path = "docs/baselines/audits/2026-08-11-p2-one-node-rc-pulse-cli.md"
    row = next((item for item in rows if item["id"] == "tran-one-node-rc-pulse"), None)
    command = manifest_by_id.get("tran.one-node-rc-pulse")
    if (
        row is None
        or row["domain"] != "tran"
        or row["command_id"] != "tran.one-node-rc-pulse"
        or row["product_surface"] != "available"
        or row["acceptance_state"] != "specified"
        or row["external_oracle"] is not False
        or row["evidence_ids"] != [evidence_id]
        or row["blockers"] != ["product_owned_no_external_profile_compare"]
        or row["non_claims"] != ["not_general_tran_netlist_or_spice_parity"]
        or command is None
        or command["route"] != ["tran", "one-node-rc-pulse"]
        or command["availability"] != "available"
        or command["transport"] != "stdin_json_v1"
        or command["request_schema"] != "sipi.tran.one-node-rc-pulse-request.v1"
        or command["response_schema"] != "sipi.tran.one-node-rc-pulse-run-result.v1"
        or command["unavailable_reason"] is not None
        or command["nonclaim"] != "bounded_product_owned_one_node_rc_pulse_only"
    ):
        raise PublicationError("publication_one_node_rc_pulse_route_binding_invalid")
    evidence = index_by_id.get(evidence_id)
    if (
        evidence is None
        or evidence["kind"] != "capability_contract"
        or evidence["path"] != path
        or evidence["subject"] != "tran-one-node-rc-pulse"
        or evidence["evidence_state"] != "specified"
    ):
        raise PublicationError("publication_one_node_rc_pulse_evidence_invalid")
    try:
        actual_sha256 = hashlib.sha256((root / path).read_bytes()).hexdigest()
    except OSError:
        raise PublicationError("publication_one_node_rc_pulse_evidence_invalid") from None
    if actual_sha256 != P2_ONE_NODE_RC_PULSE_CLI_AUDIT_SHA256:
        raise PublicationError("publication_one_node_rc_pulse_evidence_invalid")


def _validate_profile_scoped_external_acceptance(rows: list[dict[str, Any]], index_by_id: dict[str, dict[str, Any]]) -> None:
    tran = next((row for row in rows if row["id"] == "tran-rc-pulse"), None)
    if tran is None:
        raise PublicationError("publication_tran_row_missing")
    compare_id = "tran-rc-pulse-current-external-compare-v2"
    tran_source_drift_blocker = "current_external_compare_evidence_source_drift"
    if tran["acceptance_state"] == "accepted":
        if (
            tran["external_oracle"] is not True
            or compare_id not in tran["evidence_ids"]
            or "external_compare_not_executed" in tran["blockers"]
        ):
            raise PublicationError("publication_tran_acceptance_binding_invalid")
        entry = index_by_id.get(compare_id)
        if entry is None or entry["kind"] != "external_compare_evidence" or entry["subject"] != "tran-rc-pulse" or entry["evidence_state"] != "observed":
            raise PublicationError("publication_tran_acceptance_binding_invalid")
        try:
            verify_tran_evidence(load_yaml(ROOT / entry["path"]))
        except (EvidenceError, OSError, RuntimeError):
            raise PublicationError("publication_tran_external_evidence_invalid") from None
    elif (
        tran["acceptance_state"] != "specified"
        or tran["external_oracle"] is not False
        or compare_id in tran["evidence_ids"]
        or tran_source_drift_blocker not in tran["blockers"]
    ):
        raise PublicationError("publication_tran_evidence_state_drift")
    else:
        entry = index_by_id.get(compare_id)
        if (
            entry is None
            or entry["kind"] != "external_compare_evidence"
            or entry["subject"] != "tran-rc-pulse"
            or entry["evidence_state"] != "observed"
        ):
            raise PublicationError("publication_tran_evidence_state_drift")
        try:
            verify_tran_evidence(load_yaml(ROOT / entry["path"]))
        except EvidenceError as error:
            if str(error) != "evidence_product_source_drift":
                raise PublicationError("publication_tran_historical_evidence_invalid") from None
        except (OSError, RuntimeError):
            raise PublicationError("publication_tran_historical_evidence_invalid") from None
        else:
            raise PublicationError("publication_tran_historical_evidence_not_drifted")

    channel = next((row for row in rows if row["id"] == "channel"), None)
    compare_id = "channel-s2p-cli-current-external-compare-v4"
    source_drift_blocker = "current_external_compare_evidence_source_drift"
    if channel is None:
        raise PublicationError("publication_channel_row_missing")
    if (
        channel["acceptance_state"] != "specified"
        or channel["external_oracle"] is not False
        or compare_id in channel["evidence_ids"]
        or "caller_input_unattested" not in channel["blockers"]
        or "periodic_kernel_not_link_simulation" not in channel["blockers"]
        or source_drift_blocker not in channel["blockers"]
    ):
        raise PublicationError("publication_channel_acceptance_binding_invalid")
    entry = index_by_id.get(compare_id)
    if (
        entry is None
        or entry["kind"] != "external_compare_evidence"
        or entry["subject"] != "channel"
        or entry["evidence_state"] != "observed"
    ):
        raise PublicationError("publication_channel_acceptance_binding_invalid")
    try:
        verify_current_channel_cli_evidence(load_yaml(ROOT / entry["path"]))
    except CurrentChannelEvidenceError as error:
        if str(error) == "evidence_product_source_drift":
            return
        raise PublicationError("publication_channel_historical_evidence_invalid") from None
    except (OSError, RuntimeError):
        raise PublicationError("publication_channel_historical_evidence_invalid") from None
    raise PublicationError("publication_channel_historical_evidence_not_drifted")


def render(publication: dict[str, Any]) -> str:
    rows = sorted(publication["rows"], key=lambda row: row["id"])
    lines = [
        "# SIPI Pre-Release Capability Publication",
        "",
        "Status: provisional evidence only. Promotion remains blocked; this is not a release declaration.",
        "",
        "| Capability | Surface | Acceptance | Platform | Blockers |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['product_surface']} | {row['acceptance_state']} | "
            f"{row['platform']} | {', '.join(sorted(row['blockers']))} |"
        )
    lines.extend(["", "## Evidence Index", ""])
    for entry in sorted(publication["report_index"], key=lambda entry: entry["id"]):
        lines.append(f"- `{entry['id']}`: `{entry['evidence_state']}` ({entry['path']})")
    lines.extend(["", "## Non-Claims", ""])
    lines.extend(f"- `{value}`" for value in sorted(publication["non_claims"]))
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publication", type=Path, default=PUBLICATION)
    parser.add_argument("--command-manifest", type=Path, required=True)
    parser.add_argument("--render", type=Path)
    arguments = parser.parse_args()
    try:
        publication = load_json(arguments.publication)
        manifest = command_manifest(load_json(arguments.command_manifest))
        validate(publication, manifest, ROOT)
        rendered = render(publication)
        if arguments.render is not None:
            arguments.render.write_text(rendered, encoding="utf-8", newline="\n")
        print(json.dumps({"schema": SCHEMA, "valid": True, "render_sha256": hashlib.sha256(rendered.encode()).hexdigest()}, sort_keys=True))
        return 0
    except PublicationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
