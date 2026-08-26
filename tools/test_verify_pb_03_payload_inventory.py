"""Mutation tests for the PB-03 payload inventory integrity gate."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

import yaml

from tools import verify_pb_03_payload_inventory as subject


ROOT = Path(__file__).resolve().parents[1]
FORMAL_PATHS = (
    Path(subject.MANIFEST_PATH),
    Path(subject.MEMBER_MAP_PATH),
    Path("docs/baselines/audits/2026-08-27-pb-03-payload-inventory.md"),
)
UPSTREAM = os.environ.get("PB03_UPSTREAM_REPO")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git(repo: Path, *args: str, raw: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "-m", message)
    return str(git(repo, "rev-parse", "HEAD"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8", newline="\n")


def clone_candidate(destination: Path) -> Path:
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--no-local", str(ROOT), str(destination)],
        check=True,
    )
    git(destination, "config", "user.name", "PB03 test")
    git(destination, "config", "user.email", "pb03@example.invalid")
    git(destination, "switch", "--quiet", "--detach", subject.CANDIDATE_COMMIT)
    return destination


def install_gate_tools(repo: Path) -> tuple[str, dict[str, Any]]:
    for name in ("verify_pb_03_payload_inventory.py", "test_verify_pb_03_payload_inventory.py"):
        target = repo / "tools" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "tools" / name, target)
    gate_commit = commit(repo, "pb03 evidence gate")
    gate_tree = str(git(repo, "rev-parse", "HEAD^{tree}"))
    files: dict[str, Any] = {}
    for label, path in (
        ("verifier", "tools/verify_pb_03_payload_inventory.py"),
        ("mutation_test", "tools/test_verify_pb_03_payload_inventory.py"),
    ):
        payload = git(repo, "show", f"{gate_commit}:{path}", raw=True)
        assert isinstance(payload, bytes)
        files[label] = {
            "path": path,
            "blob": git(repo, "rev-parse", f"{gate_commit}:{path}"),
            "bytes": len(payload),
            "sha256": digest(payload),
        }
    return gate_commit, {"candidate_ancestor": subject.CANDIDATE_COMMIT, "commit": gate_commit, "tree": gate_tree, "files": files}


def run_verifier(repo: Path, upstream: str | None = None) -> dict[str, Any]:
    command = [sys.executable, str(repo / "tools/verify_pb_03_payload_inventory.py")]
    if upstream is not None:
        command.extend(["--upstream-repo", upstream])
    result = subprocess.run(command, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise AssertionError(f"verifier produced no JSON: rc={result.returncode}, stderr={result.stderr}") from error


def normalize_member_map(value: dict[str, Any]) -> dict[str, Any]:
    value.pop("toolchain", None)
    for label in ("candidate", "oracle"):
        replay = value[label].pop("replay", None)
        if replay is not None:
            if "observation" in value[label]:
                raise ValueError(f"{label} cannot contain replay and observation")
            value[label]["observation"] = {
                "kind": "caller_recorded_npz_receipt",
                "arrays_bytes": replay["arrays_bytes"],
                "arrays_sha256": replay["arrays_sha256"],
                "logical_sha256": replay["logical_sha256"],
                "member_count": replay["member_count"],
            }
        if "observation" not in value[label]:
            raise KeyError(f"{label} has neither replay nor observation")
    for member in value["members"]:
        source = "existing_complex_telemetry_magnitude" if member["name"] in subject.RESPONSE_HASH_DRIFT else f"logical_member:{member['name']}"
        for label in ("candidate", "oracle"):
            if member[label] is not None:
                member[label].setdefault("source", source)
    return value


def future_member_map() -> dict[str, Any]:
    value = json.loads((ROOT / subject.MEMBER_MAP_PATH).read_text(encoding="utf-8"))
    return normalize_member_map(value)


def bound_audit(bindings: dict[str, dict[str, str]]) -> str:
    anchors = {
        "member_map": bindings["member_map"]["sha256"],
        "verifier": bindings["verifier"]["sha256"],
        "mutation_test": bindings["mutation_test"]["sha256"],
        "source_map": subject.PRODUCTION_FILES["crates/sipi-pybert-direct/SOURCE-MAP-PB03-PAYLOAD.md"]["sha256"],
        "notice": subject.PRODUCTION_FILES["crates/sipi-pybert-direct/NOTICE-PYBERT-PB03-PAYLOAD.md"]["sha256"],
    }
    text = subject.EXPECTED_AUDIT_NORMALIZED
    for label, value in anchors.items():
        text = text.replace(f"{label}_sha256: <bound>", f"{label}_sha256: {value}")
    return text


def future_manifest(gate: dict[str, Any], member_map_payload: bytes) -> dict[str, Any]:
    value = yaml.safe_load((ROOT / subject.MANIFEST_PATH).read_text(encoding="utf-8"))
    value["git_gate"] = gate
    value["scope"] = {
        "source_mode": "caller_recorded_integrity_only_member_observation",
        "whole_payload_parity": False,
        "description": "Static Git archive recomputation plus caller-recorded NPZ/member receipts; no execution provenance claim.",
    }
    value["source"]["candidate"] = {
        "commit": subject.CANDIDATE_COMMIT,
        "tree": subject.CANDIDATE_TREE,
        "archive_static_recomputed": True,
    }
    value["claims"] = {
        "serializer_projection": True,
        "scoped_member_reduction": True,
        "execution_provenance": False,
        "replay_custody": False,
        "whole_payload_parity": False,
        "exact_whole_payload_parity": False,
        "global_row_closed": False,
        "product_capability": False,
        "release_approval": False,
    }
    value["non_claims"] = list(subject.EXPECTED_NON_CLAIMS)
    value["bindings"] = {
        "member_map": {"path": subject.MEMBER_MAP_PATH, "sha256": digest(member_map_payload)},
        "audit": {"path": str(FORMAL_PATHS[2]).replace("\\", "/"), "sha256": "0" * 64},
        "verifier": {"path": gate["files"]["verifier"]["path"], "sha256": gate["files"]["verifier"]["sha256"]},
        "mutation_test": {"path": gate["files"]["mutation_test"]["path"], "sha256": gate["files"]["mutation_test"]["sha256"]},
    }
    return value


class GateCheckoutTests(unittest.TestCase):
    def test_strict_scalar_helpers(self) -> None:
        self.assertTrue(subject.strict_int(1))
        self.assertFalse(subject.strict_int(True))
        self.assertFalse(subject.strict_int(1.0))
        self.assertFalse(subject.strict_string(1))

    def test_clean_gate_checkout_explicitly_skips_formal_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = clone_candidate(Path(temporary) / "gate")
            gate, _ = install_gate_tools(repo)
            result = run_verifier(repo)
            self.assertTrue(result["valid"], result["errors"])
            self.assertEqual(result["status"], "skipped_formal_artifacts_absent")
            self.assertEqual(result["gate_commit"], gate)

    def test_member_map_migration_accepts_legacy_and_final_shapes(self) -> None:
        final = normalize_member_map(json.loads((ROOT / subject.MEMBER_MAP_PATH).read_text(encoding="utf-8")))
        legacy = copy.deepcopy(final)
        legacy["toolchain"] = []
        for label in ("candidate", "oracle"):
            observation = legacy[label].pop("observation")
            legacy[label]["replay"] = {key: observation[key] for key in ("arrays_bytes", "arrays_sha256", "logical_sha256", "member_count")}
        for member in legacy["members"]:
            for label in ("candidate", "oracle"):
                if member[label] is not None:
                    member[label].pop("source")
        self.assertEqual(normalize_member_map(legacy), final)
        self.assertEqual(normalize_member_map(copy.deepcopy(final)), final)

    def test_member_map_migration_rejects_hybrid_shape(self) -> None:
        hybrid = normalize_member_map(json.loads((ROOT / subject.MEMBER_MAP_PATH).read_text(encoding="utf-8")))
        observation = hybrid["candidate"]["observation"]
        hybrid["candidate"]["replay"] = {key: observation[key] for key in ("arrays_bytes", "arrays_sha256", "logical_sha256", "member_count")}
        with self.assertRaisesRegex(ValueError, "cannot contain replay and observation"):
            normalize_member_map(hybrid)


@unittest.skipUnless(all((ROOT / path).is_file() for path in FORMAL_PATHS), "formal PB03 seed artifacts are absent")
@unittest.skipUnless(UPSTREAM and Path(UPSTREAM).is_dir(), "set PB03_UPSTREAM_REPO to the pinned upstream Git worktree")
class FormalGitRecordTests(unittest.TestCase):
    repo: Path
    baseline: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.repo = clone_candidate(Path(cls.temporary.name) / "record")
        gate_commit, gate = install_gate_tools(cls.repo)
        skipped = run_verifier(cls.repo)
        if not skipped.get("valid") or skipped.get("gate_commit") != gate_commit:
            raise AssertionError(f"gate checkout was not self-consistent: {skipped}")

        member_map = future_member_map()
        map_payload = (json.dumps(member_map, indent=2) + "\n").encode()
        manifest = future_manifest(gate, map_payload)
        audit = bound_audit(manifest["bindings"])
        manifest["bindings"]["audit"]["sha256"] = digest(audit.encode())
        write_json(cls.repo / subject.MEMBER_MAP_PATH, member_map)
        write_yaml(cls.repo / subject.MANIFEST_PATH, manifest)
        audit_path = cls.repo / FORMAL_PATHS[2]
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(audit, encoding="utf-8", newline="\n")
        cls.baseline = commit(cls.repo, "pb03 evidence record")

        result = run_verifier(cls.repo, UPSTREAM)
        if not result.get("valid"):
            raise AssertionError(f"formal baseline must pass before mutation: {result}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def restore_baseline(self) -> None:
        git(self.repo, "restore", "--source", self.baseline, "--staged", "--worktree", ".")
        if git(self.repo, "status", "--porcelain"):
            commit(self.repo, "restore formal baseline")

    def load_record(self) -> tuple[dict[str, Any], dict[str, Any], str]:
        manifest = yaml.safe_load((self.repo / subject.MANIFEST_PATH).read_text(encoding="utf-8"))
        member_map = json.loads((self.repo / subject.MEMBER_MAP_PATH).read_text(encoding="utf-8"))
        audit = (self.repo / FORMAL_PATHS[2]).read_text(encoding="utf-8")
        return manifest, member_map, audit

    def write_record(self, manifest: dict[str, Any], member_map: dict[str, Any], audit: str) -> None:
        write_json(self.repo / subject.MEMBER_MAP_PATH, member_map)
        manifest["bindings"]["member_map"]["sha256"] = digest((self.repo / subject.MEMBER_MAP_PATH).read_bytes())
        audit = re.sub(r"(?m)^member_map_sha256: [0-9a-f]{64}$", f"member_map_sha256: {manifest['bindings']['member_map']['sha256']}", audit)
        (self.repo / FORMAL_PATHS[2]).write_text(audit, encoding="utf-8", newline="\n")
        manifest["bindings"]["audit"]["sha256"] = digest((self.repo / FORMAL_PATHS[2]).read_bytes())
        write_yaml(self.repo / subject.MANIFEST_PATH, manifest)

    def assert_mutation_rejected(self, mutate: Callable[[dict[str, Any], dict[str, Any], str], str | None], label: str) -> None:
        self.restore_baseline()
        manifest, member_map, audit = self.load_record()
        changed_audit = mutate(manifest, member_map, audit)
        self.write_record(manifest, member_map, audit if changed_audit is None else changed_audit)
        commit(self.repo, f"reject {label}")
        result = run_verifier(self.repo, UPSTREAM)
        self.assertFalse(result["valid"], label)

    def test_baseline_is_valid_before_mutations(self) -> None:
        self.restore_baseline()
        result = run_verifier(self.repo, UPSTREAM)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["before"], subject.BEFORE_COUNTS)
        for key, expected in subject.COUNTS.items():
            self.assertEqual(result[key], expected)

    def test_all_response_metadata_except_hash_is_exactly_bound(self) -> None:
        values: dict[str, Any] = {
            "source": "drifted-source",
            "dtype": ">f8",
            "shape": [1, 401],
            "count": 402,
            "fortran_order": True,
        }
        for field, changed in values.items():
            with self.subTest(field=field):
                def mutate(_manifest: dict[str, Any], member_map: dict[str, Any], _audit: str, *, field: str = field, changed: Any = changed) -> None:
                    member = next(item for item in member_map["members"] if item["name"] == "chnl_H.npy")
                    member["candidate"][field] = changed

                self.assert_mutation_rejected(mutate, f"response-{field}")

    def test_response_hash_must_remain_drifted(self) -> None:
        def mutate(_manifest: dict[str, Any], member_map: dict[str, Any], _audit: str) -> None:
            member = next(item for item in member_map["members"] if item["name"] == "tx_H.npy")
            member["candidate"]["f64_sha256"] = member["oracle"]["f64_sha256"]
            member["classification"] = "exact"

        self.assert_mutation_rejected(mutate, "response-hash-equality")

    def test_before_inventory_is_derived_from_producers(self) -> None:
        def mutate(_manifest: dict[str, Any], member_map: dict[str, Any], _audit: str) -> None:
            member = next(item for item in member_map["members"] if item["candidate"] and item["candidate"]["producer"] == "pb03_serializer_projection")
            member["candidate"]["producer"] = "native_typed_result"

        self.assert_mutation_rejected(mutate, "producer-derived-before")

    def test_git_gate_full_commit_tree_and_blob_graph_is_bound(self) -> None:
        mutations = (
            ("commit", lambda manifest: manifest["git_gate"].__setitem__("commit", "0" * 40)),
            ("tree", lambda manifest: manifest["git_gate"].__setitem__("tree", "0" * 40)),
            ("candidate", lambda manifest: manifest["git_gate"].__setitem__("candidate_ancestor", "0" * 40)),
            ("blob", lambda manifest: manifest["git_gate"]["files"]["verifier"].__setitem__("blob", "0" * 40)),
            ("raw", lambda manifest: manifest["git_gate"]["files"]["mutation_test"].__setitem__("sha256", "0" * 64)),
        )
        for label, change in mutations:
            with self.subTest(label=label):
                self.assert_mutation_rejected(lambda manifest, _map, _audit, change=change: change(manifest), f"git-gate-{label}")

    def test_exact_schema_and_recursive_types_are_bound(self) -> None:
        mutations = (
            ("version-float", lambda manifest, _map: manifest.__setitem__("version", 1.0)),
            ("count-float", lambda manifest, _map: manifest["inventory"].__setitem__("candidate_count", 140.0)),
            ("extra-key", lambda manifest, _map: manifest.__setitem__("extra", True)),
            ("observation-extra", lambda _manifest, member_map: member_map["candidate"]["observation"].__setitem__("path", "hidden")),
            ("unsafe-path", lambda manifest, _map: manifest["bindings"]["member_map"].__setitem__("path", "../member-map.json")),
        )
        for label, change in mutations:
            with self.subTest(label=label):
                self.assert_mutation_rejected(lambda manifest, member_map, _audit, change=change: change(manifest, member_map), label)

    def test_production_file_change_after_candidate_is_rejected(self) -> None:
        self.restore_baseline()
        path = self.repo / "crates/sipi-pybert-direct/SOURCE-MAP-PB03-PAYLOAD.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nmutation\n", encoding="utf-8", newline="\n")
        commit(self.repo, "reject production drift")
        result = run_verifier(self.repo, UPSTREAM)
        self.assertFalse(result["valid"])

    def test_coordinated_audit_prose_change_is_rejected(self) -> None:
        def mutate(_manifest: dict[str, Any], _map: dict[str, Any], audit: str) -> str:
            return audit.replace("This record binds", "This altered record binds")

        self.assert_mutation_rejected(mutate, "audit-prose")


if __name__ == "__main__":
    unittest.main()
