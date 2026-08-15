"""Mutation tests for the rejected current P7-chain preflight record."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("p7_current_preflight", ROOT / "tools" / "verify_p7_current_candidate_chain_rebinding_preflight.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CurrentCandidateChainPreflightTests(unittest.TestCase):
    def document(self) -> dict:
        return json.loads((ROOT / "docs" / "baselines" / "p7-current-candidate-chain-rebinding-preflight.v1.yaml").read_text(encoding="utf-8"))

    def test_document_is_valid(self) -> None:
        GATE.validate(self.document())

    def test_layout_rejection_and_downstream_stop_are_fail_closed(self) -> None:
        document = self.document()
        document["static_layout"]["result"] = "layout_conformant"
        with self.assertRaisesRegex(GATE.PreflightError, "layout_rejection_invalid"):
            GATE.validate(document)
        document = self.document()
        document["downstream"]["archive_invoked"] = True
        with self.assertRaisesRegex(GATE.PreflightError, "downstream_gate_invalid"):
            GATE.validate(document)

    def test_candidate_and_release_state_are_fail_closed(self) -> None:
        document = self.document()
        document["candidate_cargo_lock_sha256"] = "0" * 64
        with self.assertRaisesRegex(GATE.PreflightError, "candidate_lock_mismatch"):
            GATE.validate(document)
        document = self.document()
        document["release_candidate"] = True
        with self.assertRaisesRegex(GATE.PreflightError, "promotion_state_invalid"):
            GATE.validate(document)

    def test_external_twin_and_layout_output_are_bound(self) -> None:
        document = self.document()
        twin = {
            "schema": GATE.TWIN_SCHEMA,
            "status": "identical",
            "commit": document["candidate_source_commit"],
            "tree": document["candidate_tree"],
            "lock_sha256": document["candidate_cargo_lock_sha256"],
            "toolchain_sha256": document["candidate_toolchain_sha256"],
            "rustflags_sha256": "a" * 64,
            "target": "x86_64-pc-windows-msvc",
            "build_a": {"binary_sha256": document["twin_build"]["binary_sha256"], "binary_bytes": document["twin_build"]["binary_bytes"]},
            "build_b": {"binary_sha256": document["twin_build"]["binary_sha256"], "binary_bytes": document["twin_build"]["binary_bytes"]},
            "comparison": {"size_match": True, "digest_match": True},
            "limitations": ["provisional"],
        }
        raw = json.dumps(twin, sort_keys=True, separators=(",", ":")).encode()
        document["twin_build"]["report_sha256"] = GATE.sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            twin_path = root / "twin.json"
            layout_path = root / "layout.stdout"
            policy_path = root / "layout-policy.json"
            stage_path = root / "sipi.exe"
            stage = b"synthetic-stage"
            document["twin_build"]["binary_sha256"] = GATE.sha256_bytes(stage)
            document["twin_build"]["binary_bytes"] = len(stage)
            document["static_layout"]["stage_executable_sha256"] = GATE.sha256_bytes(stage)
            policy = b'{"synthetic":"policy"}\n'
            document["static_layout"]["policy_sha256"] = GATE.sha256_bytes(policy)
            twin["build_a"] = {"binary_sha256": document["twin_build"]["binary_sha256"], "binary_bytes": document["twin_build"]["binary_bytes"]}
            twin["build_b"] = {"binary_sha256": document["twin_build"]["binary_sha256"], "binary_bytes": document["twin_build"]["binary_bytes"]}
            raw = json.dumps(twin, sort_keys=True, separators=(",", ":")).encode()
            document["twin_build"]["report_sha256"] = GATE.sha256_bytes(raw)
            twin_path.write_bytes(raw)
            layout_path.write_bytes(GATE.EXPECTED_LAYOUT_STDOUT)
            policy_path.write_bytes(policy)
            stage_path.write_bytes(stage)
            GATE.verify_external_observation(document, twin_path, layout_path, policy_path, stage_path)
            policy_path.write_bytes(b'{"synthetic":"drift"}\n')
            with self.assertRaisesRegex(GATE.PreflightError, "layout_policy_mismatch"):
                GATE.verify_external_observation(document, twin_path, layout_path, policy_path, stage_path)
            policy_path.write_bytes(policy)
            stage_path.write_bytes(b"drifted-stage")
            with self.assertRaisesRegex(GATE.PreflightError, "stage_executable_mismatch"):
                GATE.verify_external_observation(document, twin_path, layout_path, policy_path, stage_path)
            stage_path.write_bytes(stage)
            tampered = copy.deepcopy(twin)
            tampered["comparison"] = {"size_match": True, "digest_match": False}
            twin_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(GATE.PreflightError, "twin_digest_mismatch"):
                GATE.verify_external_observation(document, twin_path, layout_path, policy_path, stage_path)


if __name__ == "__main__":
    unittest.main()
