import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from .com_direct_semantic_replay import (
        MAX_DFE_TAPS,
        MAX_LEGACY_CSV_BYTES,
        legacy_csv_projection,
        parameters,
        run_scenario_bounded,
        semantic_projection,
    )
    from .com_direct_semantic_replay_v2 import (
        CANDIDATE_COMMIT,
        CANDIDATE_TREE,
        admit_candidate_archive,
        bounded_regular_bytes,
        exactly_one_test_passed,
        load_harness_helper,
        materialize_archive,
    )
except ImportError:
    from com_direct_semantic_replay import (
        MAX_DFE_TAPS,
        MAX_LEGACY_CSV_BYTES,
        legacy_csv_projection,
        parameters,
        run_scenario_bounded,
        semantic_projection,
    )
    from com_direct_semantic_replay_v2 import (
        CANDIDATE_COMMIT,
        CANDIDATE_TREE,
        admit_candidate_archive,
        bounded_regular_bytes,
        exactly_one_test_passed,
        load_harness_helper,
        materialize_archive,
    )


class ComSemanticReplayPrepTests(unittest.TestCase):
    def result(self, search=None):
        metrics = {
            key: None
            for key in (
                "FOM", "COM_dB", "VEC_dB", "VEO_mV", "sigma_N_V",
                "available_signal_v", "interference_noise_v", "threshold_der",
                "eye_opening_v", "calibration_sigma_bn_v",
                "calibration_sigma_ne_v", "calibration_sigma_hp_v",
            )
        }
        portable = {} if search is None else {"search": search}
        return {
            "cases": [{
                "case_index": 0,
                "channels": {"fext": [], "next": [], "calibration_noise": None},
                "metrics": metrics,
                "diagnostics": {
                    "channel_impulse": {
                        "sample_count": 1,
                        "sha256": "0" * 64,
                        "source_kind": "impulse",
                    },
                    "portable_branches": portable,
                },
            }],
            "report_manifest": None,
        }

    def test_canonical_fixture_contains_current_f2_control(self):
        self.assertEqual(parameters()["parameters"]["f2"], 50.0e9)

    def test_production_candidate_and_separate_prep_helper_are_explicit(self):
        self.assertEqual(CANDIDATE_COMMIT, "af518684936f8656eda61288abe2647f7d909ea4")
        self.assertEqual(CANDIDATE_TREE, "e49c50407557806c4addae103acbfd576b01527e")
        _, path, digest = load_harness_helper()
        self.assertEqual(path.name, "com_direct_semantic_replay.py")
        self.assertEqual(path.parent.name, "tools")
        self.assertEqual(len(digest), 64)

    def test_real_search_taps_are_candidate_execution_observation(self):
        projection = semantic_projection(
            self.result({"dfe_taps": [0.25, -0.125]}),
            ["load_config", "run_com", "write_artifacts"],
        )
        self.assertEqual(
            projection["candidate_execution_observations"]["search_winner_dfe_taps"],
            [0.25, -0.125],
        )
        self.assertNotIn("upstream_serialized_result", projection)

    def test_missing_or_empty_search_winner_taps_fail_closed(self):
        for search in (
            {},
            {"dfe_taps": []},
            {"dfe_taps": [True]},
            {"dfe_taps": [float("nan")]},
            {"dfe_taps": [0.0] * (MAX_DFE_TAPS + 1)},
        ):
            with self.assertRaises(RuntimeError):
                semantic_projection(
                    self.result(search),
                    ["load_config", "run_com", "write_artifacts"],
                )

    def test_non_search_result_has_no_inferred_observation_or_port_order_wire(self):
        projection = semantic_projection(
            self.result(), ["load_config", "run_com", "write_artifacts"]
        )
        self.assertNotIn("candidate_execution_observations", projection)
        self.assertNotIn("port_order", projection)
        self.assertNotIn("port_order_observed", projection)

    def test_candidate_archive_spoof_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.tar"
            path.write_bytes(b"not the pinned archive")
            with self.assertRaises(RuntimeError):
                admit_candidate_archive(path)

    def test_tar_special_and_oversize_members_are_rejected(self):
        for special in ("symlink", "oversize"):
            with tempfile.TemporaryDirectory() as directory:
                archive = Path(directory) / "bad.tar"
                with tarfile.open(archive, "w") as handle:
                    info = tarfile.TarInfo("bad")
                    if special == "symlink":
                        info.type = tarfile.SYMTYPE
                        info.linkname = "target"
                    else:
                        info.size = 2
                    handle.addfile(info, None if special == "symlink" else io.BytesIO(b"xx"))
                limit = mock.patch(
                    "tools.com_direct_semantic_replay_v2.MAX_ARCHIVE_MEMBER_BYTES", 1
                ) if special == "oversize" else mock.patch(
                    "tools.com_direct_semantic_replay_v2.MAX_ARCHIVE_MEMBER_BYTES",
                    64 * 1024 * 1024,
                )
                with limit, self.assertRaises(RuntimeError):
                    materialize_archive(archive, Path(directory) / "out")

    def test_exact_test_parser_rejects_zero_tests(self):
        valid = (
            "running 1 test\n"
            "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; "
            "107 filtered out; finished in 0.01s"
        )
        self.assertTrue(exactly_one_test_passed(valid))
        for invalid in (
            "running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s",
            valid.replace("running 1 test", "running 11 tests"),
            valid.replace("1 passed", "21 passed"),
            valid + "\nrunning 1 test\n" + valid.splitlines()[1],
            valid + "\n" + valid,
            "running 0 tests\n"
            "test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s\n"
            + valid,
            valid
            + "\nrunning 0 tests\n"
            "test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s",
            valid
            + "\ntest result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s",
        ):
            self.assertFalse(exactly_one_test_passed(invalid))

    def test_scenario_timeout_and_output_cap_kill(self):
        with mock.patch("tools.com_direct_semantic_replay.SCENARIO_TIMEOUT_SECONDS", 0.05):
            with self.assertRaises(RuntimeError):
                run_scenario_bounded([sys.executable, "-c", "import time; time.sleep(1)"])
        with mock.patch("tools.com_direct_semantic_replay.MAX_SCENARIO_OUTPUT_BYTES", 32):
            with self.assertRaises(RuntimeError):
                run_scenario_bounded([sys.executable, "-c", "print('x'*10000)"])

    def test_bounded_reader_detects_identity_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "helper.py"
            path.write_bytes(b"x" * 128)
            original_open = Path.open

            class DriftingHandle:
                def __init__(self, handle):
                    self.handle = handle

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.handle.close()

                def read(self, size):
                    payload = self.handle.read(size)
                    descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC)
                    try:
                        os.write(descriptor, payload + b"y")
                    finally:
                        os.close(descriptor)
                    return payload

            def drifting_open(target, *args, **kwargs):
                handle = original_open(target, *args, **kwargs)
                return DriftingHandle(handle) if target == path.resolve() else handle

            with mock.patch.object(Path, "open", drifting_open):
                with self.assertRaises(RuntimeError):
                    bounded_regular_bytes(path, 1024)

    def test_legacy_csv_rejects_link_oversize_and_empty_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty = root / "empty.csv"
            empty.write_bytes(b"\nvalue\n")
            with self.assertRaises(RuntimeError):
                legacy_csv_projection(empty)
            oversized = root / "oversized.csv"
            oversized.write_bytes(b"h" * (MAX_LEGACY_CSV_BYTES + 1))
            with self.assertRaises(RuntimeError):
                legacy_csv_projection(oversized)
            target = root / "target.csv"
            target.write_text("a,b\n1,2\n", encoding="utf-8")
            link = root / "link.csv"
            try:
                link.symlink_to(target)
            except OSError:
                link.write_text("a,b\n1,2\n", encoding="utf-8")
                original_is_symlink = Path.is_symlink
                with mock.patch.object(
                    Path,
                    "is_symlink",
                    lambda candidate: candidate == link or original_is_symlink(candidate),
                ), self.assertRaises(RuntimeError):
                    legacy_csv_projection(link)
            else:
                with self.assertRaises(RuntimeError):
                    legacy_csv_projection(link)


if __name__ == "__main__":
    unittest.main()
