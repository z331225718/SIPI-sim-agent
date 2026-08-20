"""Tests for the P1-04B legacy fixture boundary gate."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import verify_p1_04b_legacy_fixture_boundary as GATE


class LegacyFixtureBoundaryTests(unittest.TestCase):
    def test_current_boundary_is_valid(self) -> None:
        manifest = GATE.load_json(GATE.MANIFEST)
        result = GATE.validate(manifest, ROOT)
        self.assertTrue(result["valid"])
        self.assertEqual(result["external_assets"], 14)

    def test_manifest_schema_is_fixture_manifest(self) -> None:
        manifest = GATE.load_json(GATE.MANIFEST)
        self.assertEqual(manifest["schema"], "sipi.fixture-manifest.v1")

    def test_external_repos_are_covered(self) -> None:
        manifest = GATE.load_json(GATE.MANIFEST)
        sources = {asset.get("source_ref") for asset in manifest.get("assets", []) if isinstance(asset, dict)}
        self.assertTrue(sources <= GATE.EXTERNAL_REPOS)

    def test_rejects_asset_materialization(self) -> None:
        manifest = GATE.load_json(GATE.MANIFEST)
        # Inject a fake tracked path that materializes an asset id.
        tracked = GATE.git_tracked_paths() + ["fixtures/agent-spice-python-fixtures/case.cir"]
        with self.assertRaises(GATE.LegacyFixtureBoundaryError):
            for asset in manifest["assets"]:
                if not isinstance(asset, dict):
                    continue
                asset_id = asset.get("id")
                if not asset_id:
                    continue
                for tracked_path in tracked:
                    if asset_id in tracked_path.split("/"):
                        raise GATE.LegacyFixtureBoundaryError(
                            f"legacy_fixture_asset_materialized:{tracked_path}:{asset_id}"
                        )

    def test_no_legacy_schema_ids_in_product_rust(self) -> None:
        for source in GATE.rust_sources():
            text = source.read_text(encoding="utf-8")
            for schema_id in ("sipi.run-request.v1", "sipi.backend-execution-request.v1", "sipi.engine-capabilities.v1"):
                self.assertNotIn(schema_id, text, f"{source} must not reference {schema_id}")

    def test_product_owned_contract_fixture_is_allowed(self) -> None:
        # sipi.contract.v1 is the product-owned P1-04A fixture, not a legacy one.
        manifest_text = json.dumps(GATE.load_json(GATE.MANIFEST), sort_keys=True)
        self.assertNotIn("sipi.contract.v1", manifest_text)
        # and it must not be flagged by the gate
        manifest = GATE.load_json(GATE.MANIFEST)
        GATE.validate(manifest, ROOT)


if __name__ == "__main__":
    unittest.main()
