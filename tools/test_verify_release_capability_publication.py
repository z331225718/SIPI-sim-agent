"""Tests for the P7-05a provisional capability publication verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
from shutil import which
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location("p7_publication", ROOT / "tools" / "verify_release_capability_publication.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def manifest_for(publication: dict) -> list[dict]:
    unavailable = {
        "project.validate": ("project_execution_not_implemented", "no_project_execution"),
        "report.show": ("artifact_payload_preview_not_implemented", "no_payload_or_external_provenance_viewer"),
    }
    receiver_diagnostic = {
        "route": ["link", "receiver", "run"],
        "availability": "available",
        "transport": "stdin_json_v1",
        "request_schema": "sipi.receiver.diagnostic-run-request.v1",
        "response_schema": "sipi.receiver.diagnostic-run-result.v1",
        "unavailable_reason": None,
        "nonclaim": "product_owned_diagnostic_not_rfm_parity_or_clock_lock",
    }
    aligned_array_compare = {
        "route": ["compare", "run"],
        "availability": "available",
        "transport": "stdin_json_v1",
        "request_schema": "sipi.compare.aligned-arrays-request.v1",
        "response_schema": "sipi.compare.aligned-arrays-run-result.v1",
        "unavailable_reason": None,
        "nonclaim": "caller_aligned_arrays_only",
    }
    fixed_project_run = {
        "route": ["project", "run"],
        "availability": "available",
        "transport": "stdin_json_v1",
        "request_schema": "sipi.project.fixed-tran-causal-fir-run-request.v1",
        "response_schema": "sipi.project.fixed-tran-causal-fir-run-result.v1",
        "unavailable_reason": None,
        "nonclaim": "one_fixed_composite_project_route_only",
    }
    causal_fir_link = {
        "route": ["link", "run"],
        "availability": "available",
        "transport": "stdin_json_v1",
        "request_schema": "sipi.link.causal-fir-request.v1",
        "response_schema": "sipi.link.run-result.v1",
        "unavailable_reason": None,
        "nonclaim": "causal_fir_direct_launch_only",
    }
    artifact_report_inspect = {
        "route": ["report", "inspect"],
        "availability": "available",
        "transport": "stdin_json_v1",
        "request_schema": "sipi.artifact-report-request.v1",
        "response_schema": "sipi.artifact-report.v1",
        "unavailable_reason": None,
        "nonclaim": "verified_integrity_metadata_only",
    }
    commands = []
    for row in publication["rows"]:
        if row["command_id"] == "link.receiver.run":
            commands.append({"id": row["command_id"], **receiver_diagnostic})
            continue
        if row["command_id"] == "compare.run":
            commands.append({"id": row["command_id"], **aligned_array_compare})
            continue
        if row["command_id"] == "project.run":
            commands.append({"id": row["command_id"], **fixed_project_run})
            continue
        if row["command_id"] == "link.run":
            commands.append({"id": row["command_id"], **causal_fir_link})
            continue
        if row["command_id"] == "report.inspect":
            commands.append({"id": row["command_id"], **artifact_report_inspect})
            continue
        availability = row["product_surface"]
        reason, nonclaim = unavailable.get(
            row["command_id"],
            (None if availability == "available" else "test_unavailable", "test_nonclaim"),
        )
        commands.append({
            "id": row["command_id"],
            "route": row["command_id"].split("."),
            "availability": availability,
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": reason,
            "nonclaim": nonclaim,
        })
    return commands


def product_manifest() -> list[dict]:
    cargo = os.environ.get("CARGO") or which("cargo")
    if cargo is None:
        suffix = ".exe" if os.name == "nt" else ""
        candidate = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "bin" / f"cargo{suffix}"
        if candidate.is_file():
            cargo = str(candidate)
    if cargo is None:
        raise AssertionError("cargo executable is unavailable")
    completed = subprocess.run(
        [cargo, "run", "--locked", "-p", "sipi-cli", "--", "commands", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=120,
    )
    if completed.returncode != 0:
        raise AssertionError(f"product command manifest failed: {completed.stderr}")
    return GATE.command_manifest(json.loads(completed.stdout))


class PublicationTests(unittest.TestCase):
    def publication(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml").read_text(encoding="utf-8"))

    def test_current_publication_is_valid_and_deterministic(self) -> None:
        publication = self.publication()
        GATE.validate(publication, manifest_for(publication), ROOT)
        self.assertEqual(GATE.render(publication), GATE.render(publication))

    def test_current_publication_binds_the_actual_product_command_manifest(self) -> None:
        publication = self.publication()
        GATE.validate(publication, product_manifest(), ROOT)

    def test_accepts_only_the_expected_command_response_wrapper(self) -> None:
        publication = self.publication()
        body = {"schema": GATE.COMMAND_SCHEMA, "commands": manifest_for(publication)}
        wrapper = {
            "schema": "sipi.cli.response.v1",
            "protocol": 1,
            "command": "commands",
            "request_id": None,
            "status": "ok",
            "result": body,
            "diagnostic_count": 0,
        }
        self.assertEqual(GATE.command_manifest(wrapper), body["commands"])
        wrapper["diagnostic_count"] = 1
        with self.assertRaises(GATE.PublicationError):
            GATE.command_manifest(wrapper)

    def test_rejects_command_drift_and_missing_coverage(self) -> None:
        publication = self.publication()
        manifest = manifest_for(publication)
        manifest[0]["availability"] = "unavailable"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest, ROOT)
        publication = self.publication()
        publication["rows"].pop()
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(self.publication()), ROOT)

    def test_unavailable_routes_must_stay_blocked(self) -> None:
        unavailable_ids = ("ami", "com", "project-validate", "report-show")
        for row_id in unavailable_ids:
            for state in ("accepted", "specified", "not_evaluated"):
                with self.subTest(row_id=row_id, state=state):
                    publication = self.publication()
                    row = next(item for item in publication["rows"] if item["id"] == row_id)
                    self.assertEqual(row["product_surface"], "unavailable")
                    row["acceptance_state"] = state
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_surface_state_invalid"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

    def test_accepted_routes_require_explicit_evidence_authority(self) -> None:
        specialized_rejections = {
            "tran-rc-pulse": "publication_tran_acceptance_binding_invalid",
            "channel": "publication_channel_acceptance_binding_invalid",
            "project-run": "publication_fixed_project_run_route_binding_invalid",
            "link-causal-fir": "publication_causal_fir_link_route_binding_invalid",
            "report-inspect": "publication_artifact_report_inspect_route_binding_invalid",
            "compare": "publication_aligned_array_compare_route_binding_invalid",
            "prbs9-metric-artifact-compare": "publication_prbs9_artifact_metric_binding_invalid",
            "selected-highloss-prbs9-waveform-only-compare": "publication_selected_highloss_waveform_only_binding_invalid",
            "link-receiver-diagnostic": "publication_receiver_diagnostic_route_binding_invalid",
        }
        publication = self.publication()
        available_ids = [row["id"] for row in publication["rows"] if row["product_surface"] == "available"]
        self.assertEqual(len(available_ids), 23)
        for row_id in available_ids:
            with self.subTest(row_id=row_id):
                mutated = self.publication()
                row = next(item for item in mutated["rows"] if item["id"] == row_id)
                row["acceptance_state"] = "accepted"
                row["external_oracle"] = True
                expected = specialized_rejections.get(row_id, "publication_acceptance_authority_missing")
                with self.assertRaisesRegex(GATE.PublicationError, expected):
                    GATE.validate(mutated, manifest_for(mutated), ROOT)

        publication = self.publication()
        row = next(item for item in publication["rows"] if item["id"] == "version")
        row["acceptance_state"] = "accepted"
        row["external_oracle"] = True
        row["evidence_ids"].append("tran-rc-pulse-current-external-compare-v2")
        with self.assertRaisesRegex(GATE.PublicationError, "publication_acceptance_authority_missing"):
            GATE.validate(publication, manifest_for(publication), ROOT)

    def test_rejects_promotion_and_unsafe_evidence(self) -> None:
        publication = self.publication()
        publication["promotion_status"] = "approved"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(self.publication()), ROOT)
        publication = self.publication()
        publication["report_index"][0]["path"] = "C:/private/report.md"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)

    def test_tran_historical_evidence_requires_exact_source_drift_state(self) -> None:
        publication = self.publication()
        tran = next(row for row in publication["rows"] if row["id"] == "tran-rc-pulse")
        tran["blockers"].remove("current_external_compare_evidence_source_drift")
        with self.assertRaisesRegex(GATE.PublicationError, "publication_tran_evidence_state_drift"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        tran = next(row for row in publication["rows"] if row["id"] == "tran-rc-pulse")
        tran["evidence_ids"].append("tran-rc-pulse-current-external-compare-v2")
        with self.assertRaisesRegex(GATE.PublicationError, "publication_tran_evidence_state_drift"):
            GATE.validate(publication, manifest_for(publication), ROOT)

    def test_prbs9_artifact_metric_route_stays_identity_only_and_non_acceptance(self) -> None:
        publication = self.publication()
        row = next(item for item in publication["rows"] if item["id"] == "prbs9-metric-artifact-compare")
        row["external_oracle"] = True
        with self.assertRaisesRegex(GATE.PublicationError, "publication_prbs9_artifact_metric_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        row = next(item for item in publication["rows"] if item["id"] == "prbs9-metric-artifact-compare")
        row["acceptance_state"] = "accepted"
        with self.assertRaisesRegex(GATE.PublicationError, "publication_prbs9_artifact_metric_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        row = next(item for item in publication["rows"] if item["id"] == "prbs9-metric-artifact-compare")
        row["blockers"].remove("external_reference_binding_not_implemented")
        with self.assertRaisesRegex(GATE.PublicationError, "publication_prbs9_artifact_metric_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        tran = next(row for row in publication["rows"] if row["id"] == "tran-rc-pulse")
        tran["acceptance_state"] = "accepted"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)

    def test_selected_highloss_waveform_only_route_stays_specified_and_non_acceptance(self) -> None:
        def selected_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "selected-highloss-prbs9-waveform-only-compare")

        publication = self.publication()
        selected_row(publication)["acceptance_state"] = "accepted"
        with self.assertRaisesRegex(GATE.PublicationError, "publication_selected_highloss_waveform_only_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        selected_row(publication)["external_oracle"] = True
        with self.assertRaisesRegex(GATE.PublicationError, "publication_selected_highloss_waveform_only_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        required_blockers = [
            "caller_supplied_artifact_identity_only",
            "external_reference_binding_not_implemented",
            "selected_profile_acceptance_not_evaluated",
            "accepted_receiver_stage_missing",
            "statistical_eye_contour_semantics_missing",
        ]
        for blocker in required_blockers:
            with self.subTest(blocker=blocker):
                publication = self.publication()
                selected_row(publication)["blockers"].remove(blocker)
                with self.assertRaisesRegex(GATE.PublicationError, "publication_selected_highloss_waveform_only_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        selected_row(publication)["evidence_ids"] = ["p3c-prbs9-metric-artifact-cli"]
        with self.assertRaisesRegex(GATE.PublicationError, "publication_selected_highloss_waveform_only_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        index_mutations = {
            "kind": "external_compare_evidence",
            "path": "docs/baselines/p3c-prbs9-metric-artifact-cli.v1.yaml",
            "subject": "receiver",
            "evidence_state": "observed",
        }
        for field, value in index_mutations.items():
            with self.subTest(index_field=field):
                publication = self.publication()
                evidence = next(item for item in publication["report_index"] if item["id"] == "p3c-selected-highloss-prbs9-waveform-only-cli")
                evidence[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_selected_highloss_waveform_only_evidence_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

    def test_ami_route_stays_blocked_with_static_only_evidence(self) -> None:
        def ami_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "ami")

        publication = self.publication()
        ami_row(publication)["acceptance_state"] = "accepted"
        with self.assertRaisesRegex(GATE.PublicationError, "publication_surface_state_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        ami_row(publication)["external_oracle"] = False
        with self.assertRaisesRegex(GATE.PublicationError, "publication_ami_blocked_route_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        ami_row(publication)["blockers"] = ["bogus"]
        with self.assertRaisesRegex(GATE.PublicationError, "publication_ami_blocked_route_binding_invalid"):
            GATE.validate(publication, manifest_for(publication), ROOT)

        for evidence_id in ("p4b-dual-ami-asset-preflight", "p4b-dual-ami-pe-loader-declarations"):
            with self.subTest(evidence_id=evidence_id):
                publication = self.publication()
                ami_row(publication)["evidence_ids"].remove(evidence_id)
                with self.assertRaisesRegex(GATE.PublicationError, "publication_ami_blocked_route_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        index_mutations = {
            "kind": "capability_contract",
            "path": "docs/baselines/p4a-ibis-input-typ-static-acceptance.v1.yaml",
            "subject": "ibis",
            "evidence_state": "specified",
        }
        for field, value in index_mutations.items():
            with self.subTest(index_field=field):
                publication = self.publication()
                evidence = next(item for item in publication["report_index"] if item["id"] == "p4b-dual-ami-asset-preflight")
                evidence[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_ami_blocked_evidence_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "verify_ami_preflight", return_value={"worker_admitted": True, "runtime_evidence": False, "release_input": False}):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_ami_blocked_evidence_promoted"):
                GATE.validate(publication, manifest_for(publication), ROOT)

    def test_com_route_stays_bound_to_missing_authoritative_reference(self) -> None:
        def com_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "com")

        for field, value in {
            "external_oracle": False,
            "blockers": ["bogus"],
            "non_claims": ["bogus"],
            "evidence_ids": ["p6-command-manifest"],
        }.items():
            with self.subTest(row_field=field):
                publication = self.publication()
                com_row(publication)[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_com_blocked_route_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        for field, value in {
            "kind": "capability_contract",
            "path": "docs/baselines/audits/2026-08-11-p6-command-manifest.md",
            "subject": "foundation",
            "evidence_state": "specified",
        }.items():
            with self.subTest(index_field=field):
                publication = self.publication()
                evidence = next(item for item in publication["report_index"] if item["id"] == "com-r480-acceptance")
                evidence[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_com_blocked_evidence_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "COM_R480_ACCEPTANCE_SHA256", "0" * 64):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_com_blocked_evidence_invalid"):
                GATE.validate(publication, manifest_for(publication), ROOT)

        document = GATE.load_yaml(ROOT / "docs/baselines/com-r480-acceptance.v1.yaml")
        original_load_yaml = GATE.load_yaml
        for section, field, value in (
            ("authoritative_reference", "status", "available"),
            ("comparison", "status", "ready"),
            ("comparison", "result_status", "run"),
            ("comparison", "product_self_comparison", "allowed"),
            ("external_materials", "product_material", "allowed"),
        ):
            with self.subTest(section=section, field=field):
                mutated = copy.deepcopy(document)
                mutated[section][field] = value
                publication = self.publication()
                def load_yaml_for_com(path: Path) -> dict:
                    if path == ROOT / "docs/baselines/com-r480-acceptance.v1.yaml":
                        return mutated
                    return original_load_yaml(path)
                with patch.object(GATE, "load_yaml", side_effect=load_yaml_for_com):
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_com_blocked_evidence_promoted"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "verify_ami_loader_declarations", return_value={"worker_admitted": False, "runtime_invoked": True, "dynamic_closure": "blocked_not_assessed"}):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_ami_blocked_evidence_promoted"):
                GATE.validate(publication, manifest_for(publication), ROOT)

    def test_product_owned_unavailable_catalog_routes_stay_bound_to_live_descriptors(self) -> None:
        expected = {
            "project-validate": ("project.validate", ["project", "validate"], "project_execution_not_implemented", "no_project_execution"),
            "report-show": ("report.show", ["report", "show"], "artifact_payload_preview_not_implemented", "no_payload_or_external_provenance_viewer"),
        }
        for row_id, (command_id, route, reason, nonclaim) in expected.items():
            with self.subTest(row_id=row_id):
                for field, value in {
                    "external_oracle": True,
                    "blockers": ["bogus"],
                    "non_claims": ["bogus"],
                    "evidence_ids": ["p7-isolated-install"],
                }.items():
                    publication = self.publication()
                    row = next(item for item in publication["rows"] if item["id"] == row_id)
                    row[field] = value
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_product_unavailable_catalog_binding_invalid"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

                descriptor_mutations = {
                    "route": (["wrong", "route"], "publication_product_unavailable_catalog_binding_invalid"),
                    "availability": ("available", "command_manifest_invalid"),
                    "transport": ("stdin_json_v1", "publication_product_unavailable_catalog_binding_invalid"),
                    "request_schema": ("sipi.test.request.v1", "publication_product_unavailable_catalog_binding_invalid"),
                    "response_schema": ("sipi.test.response.v1", "publication_product_unavailable_catalog_binding_invalid"),
                    "unavailable_reason": ("wrong_reason", "publication_product_unavailable_catalog_binding_invalid"),
                    "nonclaim": ("wrong_nonclaim", "publication_product_unavailable_catalog_binding_invalid"),
                }
                for field, (value, error) in descriptor_mutations.items():
                    publication = self.publication()
                    manifest = manifest_for(publication)
                    descriptor = next(item for item in manifest if item["id"] == command_id)
                    descriptor[field] = value
                    with self.assertRaisesRegex(GATE.PublicationError, error):
                        GATE.validate(publication, manifest, ROOT)

        for field, value in {
            "kind": "install_observation",
            "path": "docs/baselines/audits/2026-08-11-p7-isolated-install.md",
            "subject": "project",
            "evidence_state": "observed",
        }.items():
            with self.subTest(index_field=field):
                publication = self.publication()
                evidence = next(item for item in publication["report_index"] if item["id"] == "p6-command-manifest")
                evidence[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_product_unavailable_catalog_evidence_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

    def test_receiver_diagnostic_route_stays_product_owned_and_profile_blocked(self) -> None:
        def receiver_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "link-receiver-diagnostic")

        for field, value in {
            "external_oracle": True,
            "blockers": ["bogus"],
            "non_claims": ["bogus"],
            "evidence_ids": ["p7-isolated-install"],
        }.items():
            with self.subTest(row_field=field):
                publication = self.publication()
                receiver_row(publication)[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_receiver_diagnostic_route_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        for field, value in {
            "route": ["receiver", "diagnostic", "run"],
            "availability": "unavailable",
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": "wrong_reason",
            "nonclaim": "wrong_nonclaim",
        }.items():
            with self.subTest(descriptor_field=field):
                publication = self.publication()
                manifest = manifest_for(publication)
                descriptor = next(item for item in manifest if item["id"] == "link.receiver.run")
                descriptor[field] = value
                expected = "command_manifest_invalid" if field in {"availability", "unavailable_reason"} else "publication_receiver_diagnostic_route_binding_invalid"
                with self.assertRaisesRegex(GATE.PublicationError, expected):
                    GATE.validate(publication, manifest, ROOT)

        for evidence_id, mutations in {
            "link-stage-ledger": {
                "kind": "capability_contract",
                "path": "docs/baselines/audits/2026-08-11-p3b-receiver-diagnostic-cli.md",
                "subject": "receiver",
                "evidence_state": "observed",
            },
            "p3b-receiver-diagnostic-cli": {
                "kind": "capability_ledger",
                "path": "docs/baselines/p3b-link-stage-capability-ledger.v1.yaml",
                "subject": "link",
                "evidence_state": "observed",
            },
        }.items():
            for field, value in mutations.items():
                with self.subTest(evidence_id=evidence_id, index_field=field):
                    publication = self.publication()
                    evidence = next(item for item in publication["report_index"] if item["id"] == evidence_id)
                    evidence[field] = value
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_receiver_diagnostic_evidence_invalid"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "P3B_RECEIVER_DIAGNOSTIC_AUDIT_SHA256", "0" * 64):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_receiver_diagnostic_evidence_invalid"):
                GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "verify_link_stage_capabilities", return_value={"valid": False, "entry_count": 13}):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_receiver_diagnostic_ledger_invalid"):
                GATE.validate(publication, manifest_for(publication), ROOT)

    def test_aligned_array_compare_route_stays_caller_owned_and_non_oracle(self) -> None:
        def compare_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "compare")

        for field, value in {
            "external_oracle": True,
            "blockers": ["bogus"],
            "non_claims": ["bogus"],
            "evidence_ids": ["p7-isolated-install"],
        }.items():
            with self.subTest(row_field=field):
                publication = self.publication()
                compare_row(publication)[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_aligned_array_compare_route_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        for field, value in {
            "route": ["compare", "arrays"],
            "availability": "unavailable",
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": "wrong_reason",
            "nonclaim": "wrong_nonclaim",
        }.items():
            with self.subTest(descriptor_field=field):
                publication = self.publication()
                manifest = manifest_for(publication)
                descriptor = next(item for item in manifest if item["id"] == "compare.run")
                descriptor[field] = value
                expected = "command_manifest_invalid" if field in {"availability", "unavailable_reason"} else "publication_aligned_array_compare_route_binding_invalid"
                with self.assertRaisesRegex(GATE.PublicationError, expected):
                    GATE.validate(publication, manifest, ROOT)

        for evidence_id, mutations in {
            "p3c-array-compare": {
                "kind": "capability_contract",
                "path": "docs/baselines/audits/2026-08-11-p3c-aligned-array-compare-cli.md",
                "subject": "receiver",
                "evidence_state": "observed",
            },
            "p3c-aligned-array-compare-cli": {
                "kind": "product_contract",
                "path": "docs/baselines/audits/2026-08-11-p3c-array-compare.md",
                "subject": "receiver",
                "evidence_state": "observed",
            },
        }.items():
            for field, value in mutations.items():
                with self.subTest(evidence_id=evidence_id, index_field=field):
                    publication = self.publication()
                    evidence = next(item for item in publication["report_index"] if item["id"] == evidence_id)
                    evidence[field] = value
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_aligned_array_compare_evidence_invalid"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

        for constant in ("P3C_ARRAY_COMPARE_AUDIT_SHA256", "P3C_ALIGNED_ARRAY_COMPARE_CLI_AUDIT_SHA256"):
            with self.subTest(constant=constant):
                publication = self.publication()
                with patch.object(GATE, constant, "0" * 64):
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_aligned_array_compare_evidence_invalid"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

    def test_fixed_project_run_route_stays_single_topology_and_non_oracle(self) -> None:
        def project_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "project-run")

        for field, value in {
            "domain": "compare",
            "acceptance_state": "not_evaluated",
            "external_oracle": True,
            "blockers": ["bogus"],
            "non_claims": ["bogus"],
            "evidence_ids": ["p7-isolated-install"],
        }.items():
            with self.subTest(row_field=field):
                publication = self.publication()
                project_row(publication)[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_fixed_project_run_route_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        for field, value in {
            "route": ["project", "fixed"],
            "availability": "unavailable",
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": "wrong_reason",
            "nonclaim": "wrong_nonclaim",
        }.items():
            with self.subTest(descriptor_field=field):
                publication = self.publication()
                manifest = manifest_for(publication)
                descriptor = next(item for item in manifest if item["id"] == "project.run")
                descriptor[field] = value
                expected = "command_manifest_invalid" if field in {"availability", "unavailable_reason"} else "publication_fixed_project_run_route_binding_invalid"
                with self.assertRaisesRegex(GATE.PublicationError, expected):
                    GATE.validate(publication, manifest, ROOT)

        for field, value in {
            "kind": "product_contract",
            "path": "docs/baselines/audits/2026-08-11-p3c-array-compare.md",
            "subject": "compare",
            "evidence_state": "observed",
        }.items():
            with self.subTest(index_field=field):
                publication = self.publication()
                evidence = next(item for item in publication["report_index"] if item["id"] == "p6-fixed-project-cli-run")
                evidence[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_fixed_project_run_evidence_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "P6_FIXED_PROJECT_CLI_AUDIT_SHA256", "0" * 64):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_fixed_project_run_evidence_invalid"):
                GATE.validate(publication, manifest_for(publication), ROOT)

    def test_causal_fir_link_route_stays_profile_blocked_and_non_oracle(self) -> None:
        def link_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "link-causal-fir")

        for field, value in {
            "domain": "channel",
            "acceptance_state": "not_evaluated",
            "external_oracle": True,
            "blockers": ["bogus"],
            "non_claims": ["bogus"],
            "evidence_ids": ["p7-isolated-install"],
        }.items():
            with self.subTest(row_field=field):
                publication = self.publication()
                link_row(publication)[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_causal_fir_link_route_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        for field, value in {
            "route": ["link", "causal-fir"],
            "availability": "unavailable",
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": "wrong_reason",
            "nonclaim": "wrong_nonclaim",
        }.items():
            with self.subTest(descriptor_field=field):
                publication = self.publication()
                manifest = manifest_for(publication)
                descriptor = next(item for item in manifest if item["id"] == "link.run")
                descriptor[field] = value
                expected = "command_manifest_invalid" if field in {"availability", "unavailable_reason"} else "publication_causal_fir_link_route_binding_invalid"
                with self.assertRaisesRegex(GATE.PublicationError, expected):
                    GATE.validate(publication, manifest, ROOT)

        for field, value in {
            "kind": "capability_contract",
            "path": "docs/baselines/audits/2026-08-11-p3b-receiver-diagnostic-cli.md",
            "subject": "receiver",
            "evidence_state": "observed",
        }.items():
            with self.subTest(index_field=field):
                publication = self.publication()
                evidence = next(item for item in publication["report_index"] if item["id"] == "link-stage-ledger")
                evidence[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_receiver_diagnostic_evidence_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "P3B_LINK_STAGE_LEDGER_SHA256", "0" * 64):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_causal_fir_link_evidence_invalid"):
                GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(GATE, "verify_link_stage_capabilities", return_value={"valid": False, "entry_count": 13}):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_receiver_diagnostic_ledger_invalid"):
                GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        manifest = manifest_for(publication)
        index_by_id = {item["id"]: item for item in publication["report_index"]}
        rows = publication["rows"]
        with patch.object(GATE, "verify_link_stage_capabilities", return_value={"valid": False, "entry_count": 13}):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_causal_fir_link_ledger_invalid"):
                GATE._validate_causal_fir_link_route(
                    rows, {item["id"]: item for item in manifest}, index_by_id, ROOT
                )

    def test_artifact_report_inspect_route_stays_metadata_only_and_non_oracle(self) -> None:
        def report_row(publication: dict) -> dict:
            return next(item for item in publication["rows"] if item["id"] == "report-inspect")

        for field, value in {
            "domain": "project",
            "acceptance_state": "not_evaluated",
            "external_oracle": True,
            "blockers": ["bogus"],
            "non_claims": ["bogus"],
            "evidence_ids": ["p6-command-manifest"],
        }.items():
            with self.subTest(row_field=field):
                publication = self.publication()
                report_row(publication)[field] = value
                with self.assertRaisesRegex(GATE.PublicationError, "publication_artifact_report_inspect_route_binding_invalid"):
                    GATE.validate(publication, manifest_for(publication), ROOT)

        for field, value in {
            "route": ["report", "show"],
            "availability": "unavailable",
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": "wrong_reason",
            "nonclaim": "wrong_nonclaim",
        }.items():
            with self.subTest(descriptor_field=field):
                publication = self.publication()
                manifest = manifest_for(publication)
                descriptor = next(item for item in manifest if item["id"] == "report.inspect")
                descriptor[field] = value
                expected = "command_manifest_invalid" if field in {"route", "availability", "unavailable_reason"} else "publication_artifact_report_inspect_route_binding_invalid"
                with self.assertRaisesRegex(GATE.PublicationError, expected):
                    GATE.validate(publication, manifest, ROOT)

        for evidence_id, mutations in {
            "p7-isolated-install": {
                "kind": "capability_contract",
                "path": "docs/baselines/audits/2026-08-11-p6-command-manifest.md",
                "subject": "report",
                "evidence_state": "specified",
            },
            "p6-artifact-report": {
                "kind": "install_observation",
                "path": "docs/baselines/audits/2026-08-11-p7-isolated-install.md",
                "subject": "foundation",
                "evidence_state": "observed",
            },
        }.items():
            for field, value in mutations.items():
                with self.subTest(evidence_id=evidence_id, index_field=field):
                    publication = self.publication()
                    evidence = next(item for item in publication["report_index"] if item["id"] == evidence_id)
                    evidence[field] = value
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_artifact_report_inspect_evidence_invalid"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

        for constant in ("P6_ARTIFACT_REPORT_AUDIT_SHA256", "P7_ISOLATED_INSTALL_AUDIT_SHA256"):
            with self.subTest(constant=constant):
                publication = self.publication()
                with patch.object(GATE, constant, "0" * 64):
                    with self.assertRaisesRegex(GATE.PublicationError, "publication_artifact_report_inspect_evidence_invalid"):
                        GATE.validate(publication, manifest_for(publication), ROOT)

    def test_channel_cli_requires_current_evidence_without_claiming_general_support(self) -> None:
        publication = self.publication()
        channel = next(row for row in publication["rows"] if row["id"] == "channel")
        channel["blockers"].remove("current_external_compare_evidence_source_drift")
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        channel = next(row for row in publication["rows"] if row["id"] == "channel")
        channel["evidence_ids"].append("channel-s2p-cli-current-external-compare-v4")
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)
        publication = self.publication()
        evidence = next(entry for entry in publication["report_index"] if entry["id"] == "channel-s2p-cli-current-external-compare-v4")
        evidence["evidence_state"] = "specified"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        channel = next(row for row in publication["rows"] if row["id"] == "channel")
        channel["external_oracle"] = True
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        channel = next(row for row in publication["rows"] if row["id"] == "channel")
        channel["acceptance_state"] = "accepted"
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(
            GATE,
            "verify_current_channel_cli_evidence",
            side_effect=GATE.CurrentChannelEvidenceError("evidence_product_invalid"),
        ):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_channel_historical_evidence_invalid"):
                GATE.validate(publication, manifest_for(publication), ROOT)

        publication = self.publication()
        with patch.object(
            GATE,
            "verify_current_channel_cli_evidence",
            return_value={"valid": True},
        ):
            with self.assertRaisesRegex(GATE.PublicationError, "publication_channel_historical_evidence_not_drifted"):
                GATE.validate(publication, manifest_for(publication), ROOT)

    def test_rejects_malformed_command_descriptors(self) -> None:
        cases = [
            ("missing_route", lambda command: command.pop("route")),
            ("unknown_field", lambda command: command.update({"extra": True})),
            ("bad_transport", lambda command: command.update({"transport": "file"})),
            ("available_reason", lambda command: command.update({"unavailable_reason": "wrong"})),
            ("non_string_schema", lambda command: command.update({"request_schema": 1})),
            ("empty_nonclaim", lambda command: command.update({"nonclaim": ""})),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                publication = self.publication()
                manifest = manifest_for(publication)
                mutate(manifest[0])
                with self.assertRaises(GATE.PublicationError):
                    GATE.validate(publication, manifest, ROOT)

        publication = self.publication()
        manifest = manifest_for(publication)
        manifest[1]["route"] = manifest[0]["route"]
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest, ROOT)

        publication = self.publication()
        manifest = manifest_for(publication)
        unavailable = next(command for command in manifest if command["availability"] == "unavailable")
        unavailable["unavailable_reason"] = None
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest, ROOT)


if __name__ == "__main__":
    unittest.main()
