"""Tests for the P7-08 path-scoped replacement map verifier (owner-approved)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p7_08_path_scoped_replacement_map as GATE


def current_map() -> dict:
    return GATE.load_json(GATE.MAP)


def git_count(prefix: str) -> int:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", prefix],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    if completed.returncode != 0:
        raise AssertionError(f"git ls-files failed for {prefix}")
    return len([line for line in completed.stdout.splitlines() if line.strip()])


def entry_template(prefix: str = "apps/sipi-cli") -> dict:
    count = git_count(prefix)
    return {
        "id": f"entry-{prefix.replace('/', '-')}",
        "path_prefix": prefix,
        "tracked_file_count": count,
        "classification": "migration_only",
        "replacement_owner": "crates/sipi-cli" if prefix == "apps/sipi-cli" else None,
        "replacement_status": "replaced_for_product_surface",
        "disposition": "retain_migration_evidence",
        "approval_required": True,
        "required_gates": sorted(GATE.MANDATORY_GATES),
        "notes": "test entry",
    }


class ReplacementMapTests(unittest.TestCase):
    def test_current_map_is_valid_and_deterministic(self) -> None:
        document = current_map()
        GATE.validate(document, ROOT)
        self.assertEqual(GATE.render(document), GATE.render(document))

    def test_current_map_covers_the_p7_08_legacy_surface(self) -> None:
        document = current_map()
        covered = {entry["path_prefix"] for entry in document["entries"]}
        for prefix in (
            "apps/sipi-cli",
            "packages/sipi-contracts",
            "packages/sipi-artifacts",
            "packages/sipi-runtime",
            "packages/sipi-adapters",
            "engines/agent-spice",
            "native/crates/sipi-circuit",
            "native/crates/sipi-ami",
            "fixtures/contracts",
            "tests",
            "docs/baselines/migrations",
            "docs/baselines/m5b-ami-authorized-dll-closure-preflight.v1.json",
            "docs/baselines/m5b-ami-candidate-bundle-preflight.v1.json",
            "docs/baselines/m5b-ami-candidate-bundle-preflight.v1.md",
            "docs/baselines/m5b-ami-vendor-fixture-preflight.v1.json",
            "docs/baselines/m5b-pybert-history-preflight.v1.json",
        ):
            self.assertTrue(
                any(c == prefix or c.startswith(prefix + "/") for c in covered),
                f"missing coverage for {prefix}",
            )

    def test_map_is_owner_approved(self) -> None:
        document = current_map()
        self.assertEqual(document["approval_state"], "owner_approved")

    def test_map_cross_binds_signed_approval_record(self) -> None:
        # The signed approval record must exist and bind this exact map hash.
        GATE.check_approval_record(ROOT)
        record = GATE.load_json(GATE.RECORD)
        self.assertEqual(record["approval_state"], "owner_approved")
        self.assertTrue(isinstance(record["approved_by"], str) and record["approved_by"])
        self.assertTrue(isinstance(record["approved_at_utc"], str) and record["approved_at_utc"])

    def test_map_rejects_reverted_approval_state(self) -> None:
        document = current_map()
        document["approval_state"] = "awaiting_owner_approval"
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_blocker_removal(self) -> None:
        document = current_map()
        document["blocker"] = "release_ready"
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_deletion_disposition_after_approval(self) -> None:
        # Owner approval does NOT grant deletion; delete dispositions stay
        # forbidden even after approval.
        document = current_map()
        document["entries"][0]["disposition"] = "deletion_approved"
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_gate_dropping(self) -> None:
        document = current_map()
        document["entries"][0]["required_gates"] = [
            "per_path_replacement_mapping"
        ]
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_unknown_replacement_owner(self) -> None:
        document = current_map()
        document["entries"][0]["replacement_owner"] = "crates/does-not-exist"
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_glob_path_prefix(self) -> None:
        document = current_map()
        document["entries"][0]["path_prefix"] = "docs/baselines/m5b-*"
        document["entries"][0]["tracked_file_count"] = 5
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_approval_claim_in_free_text(self) -> None:
        # The approval fact lives only in the signed record, never in the map.
        document = current_map()
        document["entries"][0]["notes"] = "owner approved for deletion"
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_approval_claim_in_purpose(self) -> None:
        document = current_map()
        document["purpose"] = "This map is approved and grants full retirement approval."
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_unknown_replacement_status(self) -> None:
        document = current_map()
        document["entries"][0]["replacement_status"] = "owner_retirement_approved_for_deletion"
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_tracked_count_drift(self) -> None:
        document = current_map()
        document["entries"][0]["tracked_file_count"] += 1
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_map_rejects_coverage_gap(self) -> None:
        document = current_map()
        del document["entries"][0]
        with self.assertRaises(GATE.MapError):
            GATE.validate(document, ROOT)

    def test_render_is_stable_and_machine_readable(self) -> None:
        document = current_map()
        rendered = GATE.render(document)
        self.assertTrue(rendered.startswith("# SIPI P7-08 Path-Scoped Replacement Map"))
        self.assertIn(GATE.BLOCKER, rendered)

    def test_real_map_binds_live_git_tracked_counts(self) -> None:
        document = current_map()
        for entry in document["entries"]:
            self.assertEqual(
                git_count(entry["path_prefix"]),
                entry["tracked_file_count"],
                f"count drift for {entry['path_prefix']}",
            )


if __name__ == "__main__":
    unittest.main()
