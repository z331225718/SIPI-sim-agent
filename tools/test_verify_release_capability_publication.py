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
    commands = []
    for row in publication["rows"]:
        availability = row["product_surface"]
        commands.append({
            "id": row["command_id"],
            "route": row["command_id"].split("."),
            "availability": availability,
            "transport": "none",
            "request_schema": None,
            "response_schema": None,
            "unavailable_reason": None if availability == "available" else "test_unavailable",
            "nonclaim": "test_nonclaim",
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
