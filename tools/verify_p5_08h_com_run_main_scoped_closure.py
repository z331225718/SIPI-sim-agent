"""Verify the additive P5-08h main scoped replacement.

P5-08h closes the main checklist item only for the owner-selected public
``com.run-artifact`` specified/non-oracle route.  The historical P5-08g
record is immutable and remains bound as the prior ``main open`` disposition.
This gate deliberately executes the product command manifest and the
publication verifier instead of treating source text alone as a live route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

try:
    from tools import verify_p5_08g_com_run_specified_scoped_closure as historical_gate
    from tools import verify_release_capability_publication as publication_gate
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import verify_p5_08g_com_run_specified_scoped_closure as historical_gate
    import verify_release_capability_publication as publication_gate


EVIDENCE = ROOT / "docs/baselines/p5-08h-com-run-main-scoped-closure.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-08h-com-run-main-scoped-closure.md"
HISTORICAL = ROOT / "docs/baselines/p5-08g-com-run-specified-scoped-closure.v1.yaml"
HISTORICAL_AUDIT = ROOT / "docs/baselines/audits/2026-08-21-p5-08g-com-run-specified-scoped-closure.md"
PUBLICATION = ROOT / "docs/baselines/release-capability-publication.v1.yaml"
COMMAND_SOURCE = ROOT / "crates/sipi-cli/src/main.rs"
SCHEMA = "sipi.p5-08h.com-run-main-scoped-closure.v1"
STATUS = "p5_08_main_scoped_replacement_closed"
POLICY = "sipi.p5-08h.com-run-artifact-specified-non-oracle-main-scope-v1"


class P508hError(RuntimeError):
    """Raised when the current scoped replacement drifts or is promoted."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise P508hError(reason)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise P508hError(f"load_failed:{path}") from error
    _require(isinstance(value, dict), f"document_not_mapping:{path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise P508hError(f"read_failed:{path}") from error


def _read_plan_and_ledger(root: Path) -> tuple[str, dict[str, Any]]:
    try:
        plan = (root / "PLAN.md").read_text(encoding="utf-8")
        ledger = yaml.safe_load((root / "docs/baselines/plan-remaining-items-ledger.v1.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise P508hError("plan_or_ledger_read_failed") from error
    _require(isinstance(ledger, dict), "ledger_not_mapping")
    return plan, ledger


def _cargo(root: Path) -> str:
    cargo = os.environ.get("CARGO") or shutil.which("cargo")
    if cargo:
        return cargo
    suffix = ".exe" if os.name == "nt" else ""
    candidate = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "bin" / f"cargo{suffix}"
    _require(candidate.is_file(), "cargo_unavailable")
    return str(candidate)


@lru_cache(maxsize=4)
def _run_command_manifest(root: Path = ROOT) -> list[dict[str, Any]]:
    """Execute the product command manifest once per root and parse its JSON."""

    completed = subprocess.run(
        [_cargo(root), "run", "--locked", "-p", "sipi-cli", "--", "commands", "--json"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=120,
    )
    _require(completed.returncode == 0, f"command_manifest_invocation_failed:{completed.stderr.strip()}")
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise P508hError("command_manifest_json_invalid") from error
    try:
        return publication_gate.command_manifest(document)
    except (publication_gate.PublicationError, TypeError, ValueError) as error:
        raise P508hError("command_manifest_invalid") from error


def _validate_live_route(document: dict[str, Any], root: Path) -> None:
    commands = _run_command_manifest(root)
    by_id = {item.get("id"): item for item in commands}
    _require(len(by_id) == len(commands), "command_manifest_duplicate")
    _require(
        by_id.get("com.run-artifact")
        == {
            "id": "com.run-artifact",
            "route": ["com", "run-artifact"],
            "availability": "available",
            "transport": "stdin_json_v1",
            "request_schema": "sipi.com.run-artifact-request.v1",
            "response_schema": "sipi.com.run-artifact-specified-result.v1",
            "unavailable_reason": None,
            "nonclaim": "product_owned_bounded_artifact_execution_non_oracle_only",
        },
        "command_manifest_com_artifact_route_invalid",
    )
    _require(
        by_id.get("com.run")
        == {
            "id": "com.run",
            "route": ["com", "run"],
            "availability": "unavailable",
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": "com_profile_not_admitted",
            "nonclaim": "no_com_solver_or_oracle_workflow",
        },
        "command_manifest_legacy_com_promoted",
    )

    publication = _load(PUBLICATION)
    _require(_sha256(PUBLICATION) == document["publication"]["sha256"], "publication_hash_drift")
    try:
        publication_gate.validate(publication, commands, root)
    except (publication_gate.PublicationError, OSError, RuntimeError, ValueError) as error:
        raise P508hError("publication_verification_failed") from error
    rows = {row.get("id"): row for row in publication.get("rows", []) if isinstance(row, dict)}
    _require(
        rows.get("com-run-artifact")
        == {
            "id": "com-run-artifact",
            "domain": "com",
            "product_surface": "available",
            "command_id": "com.run-artifact",
            "acceptance_state": "specified",
            "platform": "windows_x86_64",
            "evidence_ids": ["p5-08f-specified-com-artifact-route"],
            "external_oracle": False,
            "blockers": ["caller_supplied_parameter_partition_only", "authoritative_com_profile_not_accepted"],
            "non_claims": ["not_agent_com_parity_or_external_acceptance"],
        },
        "publication_com_artifact_route_invalid",
    )
    _require(
        rows.get("com")
        == {
            "id": "com",
            "domain": "com",
            "product_surface": "unavailable",
            "command_id": "com.run",
            "acceptance_state": "blocked",
            "platform": "windows_x86_64",
            "evidence_ids": ["com-r480-acceptance"],
            "external_oracle": True,
            "blockers": ["authoritative_reference_missing"],
            "non_claims": ["no_com_solver_or_oracle_workflow"],
        },
        "publication_legacy_com_route_promoted",
    )

    live = document["live_route"]
    _require(live["command_manifest_source"] == {
        "path": "crates/sipi-cli/src/main.rs",
        "sha256": _sha256(COMMAND_SOURCE),
    }, "command_manifest_source_binding_invalid")


def _validate_blockers(document: dict[str, Any], root: Path) -> None:
    plan, ledger = _read_plan_and_ledger(root)
    _require("- [x] **P5-08**" in plan, "plan_p5_08_not_checked")
    _require("- [x] **P5-08h**" in plan, "plan_p5_08h_missing")
    _require("- [ ] **P5-02**" in plan, "p5_02_promoted")
    _require("- [ ] **P5-06**" in plan, "p5_06_promoted")
    for item_id in ("P7-01", "P7-02", "P7-03", "P7-04", "P7-05", "P7-06", "P7-07", "P7-08", "P7-09"):
        _require(f"- [ ] **{item_id}**" in plan, f"{item_id.lower()}_promoted")
    rows = {row.get("id"): row for row in ledger.get("items", []) if isinstance(row, dict)}
    _require(ledger.get("total_open") == 19, "ledger_total_open_invalid")
    _require("P5-08" not in rows, "ledger_p5_08_remains_open")
    _require(rows.get("P5-02", {}).get("blocker") == "external_asset_oracle", "p5_02_blocker_promoted")
    _require(rows.get("P5-06", {}).get("blocker") == "external_asset_oracle", "p5_06_blocker_promoted")
    for item_id in ("P7-01", "P7-02", "P7-03", "P7-04", "P7-05", "P7-06", "P7-07", "P7-08", "P7-09"):
        _require(rows.get(item_id, {}).get("blocker") == "release_gate", f"{item_id.lower()}_blocker_promoted")
    _require(document["remaining_blockers"] == {
        "P5-02": "external_asset_oracle",
        "P5-06": "external_asset_oracle",
        "P7": "release_gate",
    }, "remaining_blockers_drift")


def validate(document: dict[str, Any] | None = None, root: Path = ROOT) -> dict[str, Any]:
    document = _load(EVIDENCE) if document is None else document
    _require(
        set(document)
        == {
            "schema", "status", "policy", "decision", "historical", "live_route", "publication",
            "contract", "threat_model", "scope", "non_claims", "remaining_blockers", "tests", "audit",
        },
        "evidence_shape_invalid",
    )
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == STATUS, "status_invalid")
    _require(document.get("policy") == POLICY, "policy_invalid")
    _require(document.get("decision") == {
        "d6": "A",
        "route": ["com", "run-artifact"],
        "resolution": "specified_non_oracle_exact_artifact_scoped_replacement",
        "closure_kind": "additive_scoped_replacement",
        "p5_08_scoped_close": True,
        "p5_08_main_item_closed": True,
        "current_disposition_superseded": True,
        "rationale": "full_general_com_conformance_is_not_required_for_the_selected_public_bounded_route",
    }, "decision_invalid")

    historical = _load(HISTORICAL)
    _require(document.get("historical") == {
        "prior_scoped_closure": {
            "id": "p5-08g",
            "path": "docs/baselines/p5-08g-com-run-specified-scoped-closure.v1.yaml",
            "sha256": _sha256(HISTORICAL),
            "status": "scoped_specified_non_oracle_closed_p5_08_main_open",
            "p5_08_main_item_closed": False,
            "historical_record_retained": True,
        },
        "prior_audit": {
            "path": "docs/baselines/audits/2026-08-21-p5-08g-com-run-specified-scoped-closure.md",
            "sha256": _sha256(HISTORICAL_AUDIT),
            "historical_record_retained": True,
        },
    }, "historical_binding_invalid")
    try:
        prior = historical_gate.validate(root=root)
    except (historical_gate.P508gError, OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError) as error:
        raise P508hError("historical_p5_08g_invalid") from error
    _require(prior.get("valid") is True and prior.get("p5_08_main_item_closed") is False, "historical_p5_08g_promoted")
    for field in ("contract", "threat_model", "scope", "non_claims"):
        _require(document[field] == historical[field], f"{field}_drift")

    _require(document.get("live_route") == {
        "command_manifest_source": {
            "path": "crates/sipi-cli/src/main.rs",
            "sha256": _sha256(COMMAND_SOURCE),
        },
        "command_id": "com.run-artifact",
        "route": ["com", "run-artifact"],
        "availability": "available",
        "transport": "stdin_json_v1",
        "request_schema": "sipi.com.run-artifact-request.v1",
        "response_schema": "sipi.com.run-artifact-specified-result.v1",
        "unavailable_reason": None,
        "nonclaim": "product_owned_bounded_artifact_execution_non_oracle_only",
        "legacy_command_id": "com.run",
        "legacy_route": ["com", "run"],
        "legacy_availability": "unavailable",
        "legacy_unavailable_reason": "com_profile_not_admitted",
        "legacy_nonclaim": "no_com_solver_or_oracle_workflow",
    }, "live_route_binding_invalid")
    _require(document.get("publication") == {
        "path": "docs/baselines/release-capability-publication.v1.yaml",
        "sha256": _sha256(PUBLICATION),
        "route_row_id": "com-run-artifact",
        "product_surface": "available",
        "acceptance_state": "specified",
        "external_oracle": False,
        "evidence_id": "p5-08f-specified-com-artifact-route",
        "legacy_row_id": "com",
        "legacy_product_surface": "unavailable",
        "legacy_acceptance_state": "blocked",
        "legacy_external_oracle": True,
    }, "publication_binding_invalid")
    _require(document.get("audit") == {
        "path": "docs/baselines/audits/2026-08-21-p5-08h-com-run-main-scoped-closure.md",
        "sha256": _sha256(AUDIT),
    }, "audit_binding_invalid")
    _require(document.get("tests") == {
        "command_manifest_invocation": "cargo_run_sipi_cli_commands_json",
        "required_cases": [
            "invokes_and_binds_current_command_manifest",
            "binds_current_publication_route_state",
            "binds_historical_p5_08g_without_rewriting_it",
            "rejects_main_item_reopen",
            "rejects_com_run_promotion",
            "rejects_budget_schema_threat_and_nonclaim_drift",
            "preserves_p5_02_p5_06_p7_blocked_state",
        ],
    }, "test_binding_invalid")
    _validate_live_route(document, root)
    _validate_blockers(document, root)
    return {
        "schema": SCHEMA,
        "valid": True,
        "status": STATUS,
        "p5_08_main_item_closed": True,
        "route": "com.run-artifact",
        "legacy_com_run": "unavailable",
        "p5_02_p5_06": "external_asset_oracle_blocked",
        "p7": "release_gate_blocked",
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
        return 0
    except (OSError, UnicodeError, yaml.YAMLError, json.JSONDecodeError, P508hError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
