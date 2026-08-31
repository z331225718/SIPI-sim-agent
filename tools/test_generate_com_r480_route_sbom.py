"""Unit tests for the bounded non-distributed COM route SBOM generator."""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.generate_com_r480_route_sbom import build_bom, reachable


def metadata() -> dict:
    return {
        "resolve": {
            "root": "cli",
            "nodes": [
                {"id": "cli", "dependencies": ["direct"]},
                {"id": "direct", "dependencies": []},
            ],
        },
        "packages": [
            {"id": "cli", "name": "sipi-cli", "version": "0.1.0", "license": "MIT", "source": None, "manifest_path": "C:/repo/crates/sipi-cli/Cargo.toml"},
            {"id": "direct", "name": "sipi-agent-com-direct", "version": "0.1.0", "license": "MIT", "source": None, "manifest_path": "C:/repo/crates/sipi-agent-com-direct/Cargo.toml"},
            {"id": "unused", "name": "unused", "version": "1", "license": "MIT", "source": "registry+https://example.invalid", "manifest_path": "C:/cache/unused/Cargo.toml"},
        ],
    }


class SbomTests(unittest.TestCase):
    def test_builds_deterministic_feature_bom(self) -> None:
        result = build_bom(metadata(), Path("C:/repo"))
        self.assertEqual(result["bomFormat"], "CycloneDX")
        self.assertEqual(result["specVersion"], "1.5")
        self.assertEqual(len(result["components"]), 2)
        self.assertEqual(result["metadata"]["component"]["properties"][1]["value"], "non-distributed")

    def test_missing_license_is_rejected(self) -> None:
        value = metadata()
        value["packages"][1]["license"] = None
        with self.assertRaisesRegex(ValueError, "license"):
            build_bom(value, Path("C:/repo"))

    def test_unreachable_package_is_not_emitted(self) -> None:
        packages, _, _ = reachable(metadata())
        self.assertNotIn("unused", packages)

    def test_workspace_escape_is_rejected(self) -> None:
        value = metadata()
        value["packages"][1]["manifest_path"] = "C:/outside/direct/Cargo.toml"
        with self.assertRaisesRegex(ValueError, "escapes root"):
            build_bom(value, Path("C:/repo"))


if __name__ == "__main__":
    unittest.main()
