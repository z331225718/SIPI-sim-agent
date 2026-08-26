"""Mutation coverage for the v12 additive upstream integration ledger gate."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path

from tools import verify_upstream_integration_ledger_v12 as gate

EXPECTED_VERIFIER_SHA256 = "664994d931836056796b64dcaafd5bdf8bd45f35786361cc6c890b0da7408123"

OBSERVATION_MUTATION_PATHS = {
    ("PB-01", "selected_array_count"): (),
    ("PB-03", "whole_payload_parity"): (),
    ("COM-02", "numeric_parity"): ("formal_gate",),
    ("COM-02", "fresh_replay_count"): ("formal_gate",),
}


class LedgerV12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = gate._load()

    def reject(self, document: dict, reason: str = "") -> None:
        with self.assertRaises(gate.LedgerError, msg=reason):
            gate.validate(document)

    def row(self, document: dict, row_id: str) -> dict:
        return next(row for row in document["rows"] if row["id"] == row_id)

    def test_v12_baseline_and_harness_anchor(self) -> None:
        self.assertEqual(EXPECTED_VERIFIER_SHA256, gate.EXPECTED_VERIFIER_SHA)
        self.assertEqual(gate.validate(copy.deepcopy(self.document)), {"valid": True, "rows": 15, "release_ready": 0})

    def test_predecessor_candidate_and_archive_are_locked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["successor"]["predecessor_sha256"] = "0" * 64
        self.reject(mutated, "predecessor")
        for key in ("commit", "tree", "archive_sha256", "archive_bytes"):
            mutated = copy.deepcopy(self.document)
            mutated["candidate"][key] = 1 if key == "archive_bytes" else "0" * (64 if key != "commit" else 40)
            self.reject(mutated, "candidate:" + key)

    def test_as05_owner_exclusion_cannot_promote_xyce_or_xdm(self) -> None:
        for key, value in (("owner_decision", "required"), ("xyce_xdm_extension", "implemented")):
            mutated = copy.deepcopy(self.document)
            self.row(mutated, "AS-05")["current_observation"][key] = value
            self.reject(mutated, "AS-05:" + key)
        for claim in ("owner_excluded_not_required", "no_xyce_xdm_extension", "no_xyce_xdm_claim"):
            mutated = copy.deepcopy(self.document)
            self.row(mutated, "AS-05")["non_claims"].remove(claim)
            self.reject(mutated, "AS-05:nonclaim:" + claim)

    def test_pb_scoped_counts_and_nonclaims_are_locked(self) -> None:
        mutations = (
            ("PB-01", "selected_array_count", 13),
            ("PB-01", "default_dictionary_item_count", 24),
            ("PB-02", "exact_npz_member_count", 12),
            ("PB-03", "stable_subset_member_count", 45),
            ("PB-03", "candidate_total_member_count", 114),
            ("PB-03", "oracle_total_member_count", 149),
            ("PB-03", "whole_payload_parity", True),
        )
        for row_id, key, value in mutations:
            mutated = copy.deepcopy(self.document)
            self.row(mutated, row_id)["current_observation"][key] = value
            self.reject(mutated, "PB:" + row_id + ":" + key)
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "PB-03")["non_claims"].remove("no_whole_payload_parity")
        self.reject(mutated, "PB-03:nonclaim")

    def test_com_formal_status_blocker_and_scope_are_locked(self) -> None:
        observation = self.row(self.document, "COM-02")["current_observation"]
        mutations = (
            ("status", "passed"),
            ("blockers", []),
            ("port_order", "observed"),
            ("dfe_publication", "published"),
            ("fresh_replay_count", 1),
            ("numeric_parity", True),
            ("global_parity", True),
            ("release_ready", True),
            ("no_s_parameter_fit", False),
            ("channel_policy", "multi_pass_sparam_fit"),
        )
        for key, value in mutations:
            mutated = copy.deepcopy(self.document)
            self.row(mutated, "COM-02")["current_observation"]["formal_gate"][key] = value
            self.reject(mutated, "COM-02:gate:" + key)
        self.assertEqual(observation["formal_gate"]["blockers"], ["candidate_dfe_taps_not_published"])
        self.assertEqual(observation["formal_gate"]["channel_policy"], "one_final_fd_to_td_impulse")

    def test_com_nonclaims_and_release_gate_cannot_be_promoted(self) -> None:
        for row_id in ("COM-02", "COM-04"):
            for claim in ("candidate_dfe_taps_not_published", "no_numeric_parity", "no_global_parity", "no_release", "no_s_parameter_fit", "impulse_only", "one_final_fd_to_td_impulse", "no_row_close"):
                mutated = copy.deepcopy(self.document)
                self.row(mutated, row_id)["non_claims"].remove(claim)
                self.reject(mutated, row_id + ":nonclaim:" + claim)
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = 1
        self.reject(mutated, "summary:release")
        mutated = copy.deepcopy(self.document)
        mutated["summary"]["release_ready"] = False
        self.reject(mutated, "summary:type")

    def test_physical_evidence_and_audit_hashes_are_locked(self) -> None:
        mutations = (
            ("PB-01", "formal_manifest", "sha256"),
            ("COM-02", "formal_audit", "sha256"),
            ("COM-04", "aggregate", "sha256"),
        )
        for row_id, section, key in mutations:
            mutated = copy.deepcopy(self.document)
            self.row(mutated, row_id)["current_observation"][section][key] = "0" * 64
            self.reject(mutated, row_id + ":physical-hash")
        mutated = copy.deepcopy(self.document)
        mutated["rows"][6]["evidence"]["sha256"] = "0" * 64
        self.reject(mutated, "evidence")

    def test_plan_audit_and_harness_bindings_are_locked(self) -> None:
        for section in ("plan", "audit"):
            mutated = copy.deepcopy(self.document)
            mutated[section]["sha256"] = "0" * 64
            self.reject(mutated, section)
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["verifier"]["path"] = "tools/verify_upstream_integration_ledger_v11.py"
        self.reject(mutated, "harness:path")
        mutated = copy.deepcopy(self.document)
        mutated["harness"]["mutation_tests"]["sha256"] = "0" * 64
        self.reject(mutated, "harness:hash")

    def test_shape_and_policy_drift_fail_closed(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rows"].append(copy.deepcopy(mutated["rows"][0]))
        self.reject(mutated, "row-count")
        mutated = copy.deepcopy(self.document)
        mutated["policy"]["channel_policy"] = "fit_sparam"
        self.reject(mutated, "channel-policy")
        mutated = copy.deepcopy(self.document)
        mutated["policy"]["new_domain_features_allowed"] = True
        self.reject(mutated, "new-domain")
        mutated = copy.deepcopy(self.document)
        mutated["unexpected"] = True
        self.reject(mutated, "top-keys")

    def test_fixed_values_reject_bool_int_and_float_coercion(self) -> None:
        mutations = (
            ("policy", "new_domain_features_allowed", 0),
            ("candidate", "archive_bytes", 52992000.0),
            ("PB-01", "selected_array_count", 12.0),
            ("PB-03", "whole_payload_parity", 0),
            ("COM-02", "numeric_parity", 0),
            ("COM-02", "fresh_replay_count", 2.0),
        )
        for section, key, value in mutations:
            mutated = copy.deepcopy(self.document)
            if section == "policy":
                mutated[section][key] = value
            elif section == "candidate":
                mutated[section][key] = value
            else:
                observation = self.row(mutated, section)["current_observation"]
                for path in OBSERVATION_MUTATION_PATHS[(section, key)]:
                    observation = observation[path]
                observation[key] = value
            self.reject(mutated, "exact-type:" + section + ":" + key)
        mutated = copy.deepcopy(self.document)
        self.row(mutated, "COM-02")["current_observation"]["non_release_claim"] = 1
        self.reject(mutated, "exact-type:COM-02:non_release_claim")

    def test_outside_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v12-outside-") as outside_raw, tempfile.TemporaryDirectory(dir=gate.ROOT, prefix=".v12-custody-") as inside_raw:
            outside = Path(outside_raw) / "payload.json"
            outside.write_text("outside", encoding="utf-8")
            link = Path(inside_raw) / "linked.json"
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("symlink capability unavailable: " + str(exc))
            relative = link.relative_to(gate.ROOT).as_posix()
            self.assertFalse(gate._safe(relative))
            with self.assertRaises(gate.LedgerError):
                gate._bind({"path": relative, "sha256": "0" * 64}, "outside-symlink")

    @unittest.skipUnless(os.name == "nt", "reparse-point capability is Windows-specific")
    def test_outside_reparse_point_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v12-outside-") as outside_raw, tempfile.TemporaryDirectory(dir=gate.ROOT, prefix=".v12-custody-") as inside_raw:
            link = Path(inside_raw) / "reparse-dir"
            try:
                os.symlink(outside_raw, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("reparse capability unavailable: " + str(exc))
            if not gate._is_reparse(link.lstat()):
                self.skipTest("platform symlink is not reported as a reparse point")
            relative = link.relative_to(gate.ROOT).as_posix()
            self.assertFalse(gate._safe(relative))
            with self.assertRaises(gate.LedgerError):
                gate._bind({"path": relative, "sha256": "0" * 64}, "outside-reparse")

    def test_hardlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=gate.ROOT, prefix=".v12-custody-") as inside_raw:
            source = Path(inside_raw) / "source.bin"
            link = Path(inside_raw) / "hardlink.bin"
            source.write_bytes(b"hardlink")
            try:
                os.link(source, link)
            except (OSError, NotImplementedError) as exc:
                self.skipTest("hardlink capability unavailable: " + str(exc))
            nlink = source.stat().st_nlink
            if nlink <= 1:
                self.skipTest("platform does not expose hardlink nlink > 1")
            relative = link.relative_to(gate.ROOT).as_posix()
            self.assertFalse(gate._safe(relative))
            with self.assertRaises(gate.LedgerError):
                gate._bind({"path": relative, "sha256": "0" * 64}, "hardlink")


if __name__ == "__main__":
    unittest.main()
