"""Focused mutation tests for the COM R4.80 license observation gate."""

from __future__ import annotations

import copy
import unittest

from tools.verify_com_r480_license_admission_observation import (
    local_closure_from_metadata,
    validate_document,
)


def document() -> dict:
    return {
        "schema": "sipi.com.r480-license-admission-observation.v1",
        "status": "candidate_only_internal_license_observation",
        "candidate": {"commit": "a" * 40, "tree": "b" * 40},
        "route": {"command": "sipi com run", "profile": "r4.80 original-13 workbook execution", "publicly_admitted": False},
        "local_compile_closure": [{"name": "sipi-agent-com-direct", "path": "crates/sipi-agent-com-direct/Cargo.toml", "license": "MIT"}],
        "forbidden_local_packages": ["sipi-agent-com-adapter", "sipi-ieee-com-sparam"],
        "evidence": [{"path": "LICENSE-SCOPE.md", "sha256": "c" * 64}],
        "source_origin": {"agent_com_commit": "5272ffe74702cd585054d975559b06f8afae7b6e", "agent_com_tree": "7094ab6e84989b218730c52432c70da10261f8ea", "agent_com_license": "MIT", "compiled_bsd_3_clause_direct_port": False},
        "boundary": {"distribution_admitted": False, "release": False, "product_boundary_v1_remains_authoritative": True},
        "blockers": ["final distributable archive lacks a route-specific NOTICE and SBOM receipt", "product-boundary.v1 is provisional and MIT-only", "final public CLI candidate requires a fresh immutable MATLAB/Rust replay"],
    }


class LicenseObservationTests(unittest.TestCase):
    def test_valid_document(self) -> None:
        validate_document(document())

    def test_promotion_is_rejected(self) -> None:
        value = document()
        value["boundary"]["distribution_admitted"] = True
        with self.assertRaisesRegex(ValueError, "boundary"):
            validate_document(value)

    def test_unknown_key_is_rejected(self) -> None:
        value = document()
        value["release"] = True
        with self.assertRaisesRegex(ValueError, "keys"):
            validate_document(value)

    def test_ambiguous_license_is_rejected(self) -> None:
        value = document()
        value["local_compile_closure"][0]["license"] = "MIT OR BSD-3-Clause"
        with self.assertRaisesRegex(ValueError, "closure entry"):
            validate_document(value)

    def test_forbidden_closure_entry_is_rejected_by_metadata_projection(self) -> None:
        root = __import__("pathlib").Path("C:/repo")
        metadata = {
            "resolve": {"root": "direct", "nodes": [{"id": "direct", "dependencies": ["ieee"]}, {"id": "ieee", "dependencies": []}]},
            "packages": [
                {"id": "direct", "name": "sipi-agent-com-direct", "license": "MIT", "manifest_path": "C:/repo/crates/sipi-agent-com-direct/Cargo.toml"},
                {"id": "ieee", "name": "sipi-ieee-com-sparam", "license": "BSD-3-Clause", "manifest_path": "C:/repo/crates/sipi-ieee-com-sparam/Cargo.toml"},
            ],
        }
        result = local_closure_from_metadata(metadata, root)
        self.assertEqual([entry["name"] for entry in result], ["sipi-agent-com-direct", "sipi-ieee-com-sparam"])

    def test_duplicate_evidence_is_rejected(self) -> None:
        value = document()
        value["evidence"].append(copy.deepcopy(value["evidence"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate evidence"):
            validate_document(value)


if __name__ == "__main__":
    unittest.main()
