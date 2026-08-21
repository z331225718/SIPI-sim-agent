from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import verify_p7_current_candidate_build_license_material_observation as GATE


class CurrentP7LicenseMaterialEvidenceTests(unittest.TestCase):
    def _synthetic_packages(self) -> list[dict]:
        packages = []
        for index in range(73):
            checksum = f"{index + 1:064x}"
            packages.append({
                "identity": f"registry:synthetic-registry-{index}@1.0.0#{checksum}",
                "kind": "registry", "name": f"synthetic-registry-{index}", "version": "1.0.0",
                "cargo_lock_checksum": checksum, "manifest_sha256": "1" * 64,
                "literal_license": None, "literal_license_file": None, "license_materials": [],
                "license_concluded": "NOASSERTION", "notice_requirement": "not_evaluated",
            })
        for index in range(13):
            digest = f"{index + 1:064x}"
            packages.append({
                "identity": f"workspace:synthetic-workspace-{index}@0.1.0#{digest}",
                "kind": "workspace", "name": f"synthetic-workspace-{index}", "version": "0.1.0",
                "version_source": "manifest", "manifest_path": f"crates/synthetic-{index}/Cargo.toml",
                "manifest_sha256": digest, "literal_license": None, "literal_license_file": None,
                "boundary_class": {"rule": "test", "class": "quarantine", "license": "pending", "provenance": "test", "distribution": "non-distributed"},
                "license_materials": [], "license_concluded": "NOASSERTION", "notice_requirement": "not_evaluated",
            })
        return packages

    def _report(self, document: dict) -> dict:
        packages = self._synthetic_packages()
        canonical = json.dumps(packages, sort_keys=True, separators=(",", ":")).encode("utf-8")
        document["result"]["package_set_sha256"] = GATE.sha256(canonical)
        return {
            "schema": GATE.REPORT_SCHEMA, "status": document["result"]["status"], "candidate": document["candidate"],
            "build": {"cargo_version_sha256": "a" * 64, "target": "x86_64-pc-windows-msvc", "release": True, "locked": True, "offline": True, "fresh_builds": 2},
            "package_set": {"sha256": document["result"]["package_set_sha256"], "counts": {"total": 86, "registry": 73, "workspace": 13}, "build_a_stderr_sha256": "b" * 64, "build_b_stderr_sha256": "c" * 64, "packages": packages},
            "gates": GATE.EXPECTED_GATES, "non_claims": GATE.EXPECTED_NON_CLAIMS,
        }

    def test_document_is_current_and_valid(self) -> None:
        document = GATE._load_document()
        GATE.validate(document)
        self.assertEqual(document["candidate"]["commit"], "97b0f271abcb7df02a3a9b259c4dafee86f3a783")

    def test_external_report_is_hash_bound(self) -> None:
        document = GATE._load_document()
        GATE.validate(document)
        report = self._report(document)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            document["external_report"] = {"sha256": GATE.sha256(path.read_bytes()), "bytes": path.stat().st_size}
            GATE.verify_external_report(document, path)

            report["package_set"]["counts"]["registry"] = 72
            path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(GATE.EvidenceError):
                GATE.verify_external_report(document, path)

    def test_package_schema_rejects_synthetic_extra_field(self) -> None:
        document = GATE._load_document(); GATE.validate(document); report = self._report(document)
        report["package_set"]["packages"][0]["synthetic"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"; raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n"; path.write_bytes(raw)
            document["external_report"] = {"sha256": GATE.sha256(raw), "bytes": len(raw)}
            with self.assertRaisesRegex(GATE.EvidenceError, "registry_package_schema_invalid"):
                GATE.verify_external_report(document, path)

    def test_package_identity_kind_count_and_digest_are_bound(self) -> None:
        for mutation, expected in (
            ("duplicate", "package_identity_duplicate"),
            ("kind", "package_kind_invalid"),
            ("digest", "package_set_digest_invalid"),
        ):
            document = GATE._load_document(); GATE.validate(document); report = self._report(document)
            packages = report["package_set"]["packages"]
            if mutation == "duplicate":
                packages[1] = copy.deepcopy(packages[0])
            elif mutation == "kind":
                packages[0]["kind"] = "synthetic"
            else:
                report["package_set"]["sha256"] = "d" * 64
                document["result"]["package_set_sha256"] = "d" * 64
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "report.json"; raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode() + b"\n"; path.write_bytes(raw)
                document["external_report"] = {"sha256": GATE.sha256(raw), "bytes": len(raw)}
                with self.assertRaisesRegex(GATE.EvidenceError, expected):
                    GATE.verify_external_report(document, path)

    def test_mutated_report_is_rejected(self) -> None:
        document = GATE._load_document()
        payload = {"schema": GATE.REPORT_SCHEMA}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            document["external_report"] = {"sha256": GATE.sha256(path.read_bytes()), "bytes": path.stat().st_size}
            with self.assertRaises(GATE.EvidenceError):
                GATE.verify_external_report(document, path)


if __name__ == "__main__":
    unittest.main()
