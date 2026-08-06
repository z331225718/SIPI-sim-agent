from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_m2_external_gate.py"


def run_checker(repos: dict, *, license_text: str, fixtures: dict) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        license_path = tmp / "license-manifest.v1.yaml"
        license_path.write_text(license_text, encoding="utf-8")
        fixtures_path = tmp / "fixtures-manifest.json"
        fixtures_path.write_text(json.dumps(fixtures), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(CHECKER),
                "--repos",
                json.dumps(repos),
                "--license-manifest",
                str(license_path),
                "--fixtures",
                str(fixtures_path),
            ],
            capture_output=True,
            text=True,
        )


def make_tagged_repo(root: Path, name: str) -> Path:
    repo = root / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@local"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    (repo / "file.txt").write_text("content", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "-a", f"sipi-baseline/{name}/20260807.1", "-m", "baseline"], cwd=repo, check=True)
    return repo


class ExternalGateTests(unittest.TestCase):
    def test_missing_tags_are_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repos = {"agent-spice": str(root / "missing")}
            result = run_checker(repos, license_text="subjects: []\n", fixtures={"assets": []})
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertFalse(report["ready"])
            self.assertIn("no sipi-baseline tag", report["engines"][0]["blockers"])

    def test_blocked_license_and_missing_fixture_are_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = make_tagged_repo(root, "agent-spice")
            license_text = (
                "subjects:\n"
                "  - id: agent-spice-source\n"
                "    scope: {root_ref: agent-spice}\n"
                "    distribution_status: blocked_unknown\n"
            )
            fixtures = {
                "assets": [
                    {
                        "id": "agent-spice-required",
                        "source_ref": "agent-spice",
                        "availability": "missing",
                        "required_by": [{"gate": "G4", "requirement": "required"}],
                    }
                ]
            }
            result = run_checker({"agent-spice": str(repo)}, license_text=license_text, fixtures=fixtures)
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            blockers = report["engines"][0]["blockers"]
            self.assertIn("license blocked_unknown", blockers)
            self.assertTrue(any("required fixture" in item for item in blockers))

    def test_fully_ready_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = make_tagged_repo(root, "agent-spice")
            license_text = (
                "subjects:\n"
                "  - id: agent-spice-source\n"
                "    scope: {root_ref: agent-spice}\n"
                "    distribution_status: authorized_public\n"
            )
            fixtures = {
                "assets": [
                    {
                        "id": "agent-spice-required",
                        "source_ref": "agent-spice",
                        "availability": "present",
                        "required_by": [{"gate": "G4", "requirement": "required"}],
                    }
                ]
            }
            result = run_checker({"agent-spice": str(repo)}, license_text=license_text, fixtures=fixtures)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["ready"])
            self.assertEqual(report["engines"][0]["tag"], "sipi-baseline/agent-spice/20260807.1")

    def test_any_blocked_subject_for_engine_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = make_tagged_repo(root, "agent-spice")
            license_text = (
                "subjects:\n"
                "  - id: agent-spice-authorized\n"
                "    scope: {root_ref: agent-spice}\n"
                "    distribution_status: authorized_public\n"
                "  - id: agent-spice-blocked\n"
                "    scope: {root_ref: agent-spice}\n"
                "    distribution_status: blocked_unknown\n"
            )
            result = run_checker({"agent-spice": str(repo)}, license_text=license_text, fixtures={"assets": []})
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertIn("license blocked_unknown: agent-spice-blocked", report["engines"][0]["blockers"])

    def test_unparsable_license_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = make_tagged_repo(root, "agent-spice")
            result = run_checker({"agent-spice": str(repo)}, license_text="{not: [valid", fixtures={"assets": []})
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(any("unparsable" in item for item in report["engines"][0]["blockers"]))

    def test_missing_license_manifest_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            license_path = tmp / "missing.yaml"
            fixtures_path = tmp / "fixtures.json"
            fixtures_path.write_text('{"assets": []}', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(CHECKER),
                    "--repos",
                    json.dumps({"agent-spice": str(tmp)}),
                    "--license-manifest",
                    str(license_path),
                    "--fixtures",
                    str(fixtures_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
