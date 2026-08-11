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
from verify_tran_rc_pulse_current_external_compare_evidence import EvidenceError, verify_document as verify_tran_evidence


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
ROUTE_TOKEN = re.compile(r"[a-z][a-z-]*")


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
        if row["product_surface"] == "available" and row["acceptance_state"] == "blocked":
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


def _validate_profile_scoped_external_acceptance(rows: list[dict[str, Any]], index_by_id: dict[str, dict[str, Any]]) -> None:
    tran = next((row for row in rows if row["id"] == "tran-rc-pulse"), None)
    if tran is None:
        raise PublicationError("publication_tran_row_missing")
    compare_id = "tran-rc-pulse-current-external-compare"
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
    elif compare_id in tran["evidence_ids"]:
        raise PublicationError("publication_tran_evidence_state_drift")


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
