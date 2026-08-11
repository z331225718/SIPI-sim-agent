"""Tests for the P7-05a provisional capability publication verifier."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


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


class PublicationTests(unittest.TestCase):
    def publication(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "release-capability-publication.v1.yaml").read_text(encoding="utf-8"))

    def test_current_publication_is_valid_and_deterministic(self) -> None:
        publication = self.publication()
        GATE.validate(publication, manifest_for(publication), ROOT)
        self.assertEqual(GATE.render(publication), GATE.render(publication))

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

    def test_accepted_tran_requires_the_verified_external_evidence(self) -> None:
        publication = self.publication()
        tran = next(row for row in publication["rows"] if row["id"] == "tran-rc-pulse")
        tran["evidence_ids"].remove("tran-rc-pulse-current-external-compare")
        with self.assertRaises(GATE.PublicationError):
            GATE.validate(publication, manifest_for(publication), ROOT)
        publication = self.publication()
        evidence = next(entry for entry in publication["report_index"] if entry["id"] == "tran-rc-pulse-current-external-compare")
        evidence["evidence_state"] = "specified"
        with self.assertRaises(GATE.PublicationError):
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
