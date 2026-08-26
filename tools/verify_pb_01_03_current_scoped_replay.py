"""Fail-closed verifier for the PB-01/02/03 current scoped replay bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "baselines" / "pb-01-03-current-scoped-replay-bc882d2e.v1.yaml"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32,64}\Z")
PATH_LEAK = re.compile(
    r"(?:[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:Users|home|tmp|var/tmp|private)/|\\(?:Users|Temp)\\)",
    re.IGNORECASE,
)

CANDIDATE_COMMIT = "bc882d2e5a19c2a844bacc485ede5b874e8f9c37"
CANDIDATE_TREE = "d87cfecea77ccd670073a6c069658e6b4e8c3137"
CANDIDATE_ARCHIVE = "1f44f6dccba7a00684a82c4c7ce6248eb5ea7f353875af5d9589d17ece6883d0"
UPSTREAM_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
UPSTREAM_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
UPSTREAM_ARCHIVE = "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25"

PB01_SCHEMA = "sipi.pb-01-legacy-leaf-replay.v1"
PB02_SCHEMA = "sipi.pb-02-direct-replay.v1"
PB03_SCHEMA = "sipi.pb-03-direct-replay.v1"

PB01_ITEMS = (
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_s",
    "ctle_s",
    "dfe_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
    "chnl_H",
    "tx_H",
    "ctle_H",
    "dfe_H",
    "tx_out_H",
    "ctle_out_H",
    "dfe_out_H",
    "tx_out",
)
PB01_SELECTED = (
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
)
PB02_MEMBERS = (
    "channel_impulse_v_per_v.npy",
    "channel_output_v.npy",
    "ctle_output_v.npy",
    "rx_ffe_impulse_v_per_v.npy",
    "rx_filter_impulse_v_per_v.npy",
    "rx_input_v.npy",
    "rx_output_v.npy",
    "symbols_v.npy",
    "time_s.npy",
    "tx_channel_impulse_v_per_v.npy",
    "tx_waveform_v.npy",
)
PB03_STABLE = (
    "ber_auto_correlation.npy",
    "ber_error_indices.npy",
    "ber_observed_bits.npy",
    "ber_reference_bits.npy",
    "channel_impulse_v_per_v.npy",
    "channel_output_v.npy",
    "ctle_output_v.npy",
    "dfe_bits.npy",
    "dfe_clock_times_s.npy",
    "dfe_clocks.npy",
    "dfe_decision_scalers_v.npy",
    "dfe_decisions.npy",
    "dfe_locked.npy",
    "dfe_output_v.npy",
    "dfe_signal_samples_v.npy",
    "dfe_tap_weights_v.npy",
    "dfe_ui_estimates_s.npy",
    "legacy_channel_frequency_hz.npy",
    "legacy_channel_raw_im.npy",
    "legacy_channel_raw_re.npy",
    "legacy_channel_terminated_im.npy",
    "legacy_channel_terminated_re.npy",
    "legacy_channel_trimmed_im.npy",
    "legacy_channel_trimmed_re.npy",
    "legacy_stage_ctle_im.npy",
    "legacy_stage_ctle_out_im.npy",
    "legacy_stage_ctle_out_re.npy",
    "legacy_stage_ctle_re.npy",
    "legacy_stage_dfe_im.npy",
    "legacy_stage_dfe_out_im.npy",
    "legacy_stage_dfe_out_re.npy",
    "legacy_stage_dfe_re.npy",
    "legacy_stage_tx_im.npy",
    "legacy_stage_tx_out_im.npy",
    "legacy_stage_tx_out_re.npy",
    "legacy_stage_tx_re.npy",
    "rx_ffe_impulse_v_per_v.npy",
    "rx_filter_impulse_v_per_v.npy",
    "rx_input_v.npy",
    "rx_output_v.npy",
    "symbols_v.npy",
    "time_s.npy",
    "tx_channel_impulse_v_per_v.npy",
    "tx_waveform_v.npy",
)

PB02_LOGICAL_SHA = "5090a1478ea6e985342d8500c6220cdde5c7fa2c416abbdeb595dcdc380c275a"
PB03_STABLE_SHA = "67e0fb568f1d0461e1b60c2b5cd3e52c5ade90bb689067740bff7d82d0fe02e7"

REPLAY_RUNNERS = {
    "tools/run_pb_01_legacy_leaf_replay.py": "4632a402962b24bdc1cd2c2869c728d58f1dc9afe6e9372e6b4499203033bd87",
    "tools/run_pb_02_direct_replay.py": "c7839a7d67425fda0df675c35925a87f7e3527996fa3b659e2ee7c036408d863",
    "tools/run_pb_03_direct_replay.py": "c54f238c9bc4a21c62107b939625c75f967558d33098366c017ab928b5709d51",
    "tools/pb_03_replay_common.py": "bd10f6bbc63bde8fe3b7f1fb2083ac568ca41d2c42d21faedf127f8b6540d5c9",
}

EXPECTED_REPORTS = {
    "PB-01": [
        {
            "path": "docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb01-run-01.v1.json",
            "sha256": "de1307394a1435af1c7162558662101791b081f741b3a4776d2e40284c6c7528",
            "run_id": "pb01-current-a-20260825180204",
            "fresh_run_nonce": "16a1b2e41a8f239fa63342dfb5e39d1372e55b3cce7439771de5c71daba593fa",
        },
        {
            "path": "docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb01-run-02.v1.json",
            "sha256": "1d779f9e46679fbc62a09333283b5e80691c50073693cb0fe9b078e342faa528",
            "run_id": "pb01-current-b-20260825180352",
            "fresh_run_nonce": "d05bae15bcaed48e034667aaeaa1dc2281057a31de7f09f3ef19c45ee537c7f7",
        },
    ],
    "PB-02": [
        {
            "path": "docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb02-run-01.v1.json",
            "sha256": "38c1f00b30282911a3dea84058a242a35f604142a8c86f7c72ff7e20d6b9c8ca",
            "run_id": "pb02-current-a-20260825175748",
            "fresh_run_nonce": "e9d337f2e5fb9ee8fb2b157971ca70f8924473228d81babfbd609ca2550ea306",
        },
        {
            "path": "docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb02-run-02.v1.json",
            "sha256": "722b71d85c503fe1e3047dbce21767158784b6f098738330a2634ee19845bfd0",
            "run_id": "pb02-current-b-20260825180014",
            "fresh_run_nonce": "b67e2d490e814fd8ae512d6c0a69af48ddd9a3d040e6018c68084bc98e884da9",
        },
    ],
    "PB-03": [
        {
            "path": "docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb03-run-01.v1.json",
            "sha256": "a27a26ac06d81894ec3190de212b7be963e57a876d1f900dac3e4ffd9e61d556",
            "run_id": "pb03-current-a-20260825180534",
            "fresh_run_nonce": "f2118d3ff6904227969ad80b6d985d23",
        },
        {
            "path": "docs/baselines/pb-01-03-current-scoped-replay-bc882d2e-pb03-run-02.v1.json",
            "sha256": "0f069b8a659255f2a30d9220dc3ae0e0a6a340cc090bc1a10ba32355b3762d3b",
            "run_id": "pb03-current-b-20260825180814",
            "fresh_run_nonce": "cbcee92db8984a0cb62c116f401537a4",
        },
    ],
}

EXPECTED_TOOLCHAINS = {
    "PB-01": {
        "timeout_seconds": 1200,
        "cargo": {
            "role": "cargo",
            "executable": "cargo.exe",
            "path_redacted": True,
            "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7",
            "version_exit_code": 0,
            "version_output_sha256": "4e9216fb7cac2573c1a8d60be140200103a52ab9fd9415070d94a98b1ef5973a",
        },
        "rustc": {
            "role": "rustc",
            "executable": "rustc.exe",
            "path_redacted": True,
            "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7",
            "version_exit_code": 0,
            "version_output_sha256": "d6dec673ca010f6a7d90aa3f4a896ad9d88b66b8fe090296c298eddfe9a406db",
        },
        "uv": {
            "role": "uv",
            "executable": "uv.exe",
            "path_redacted": True,
            "file_sha256": "5a7ec85884c2ccb1be560cb8fac3eb890df1adf49bfcc070a270ba70401bdd68",
            "version_exit_code": 0,
            "version_output_sha256": "ab0d29803cb58959acc6cf64650fb215c72c2989b94fb6f9de5f22814ceca82d",
        },
    },
    "PB-02": {},
    "PB-03": {
        "timeout_seconds": 1200,
        "cargo": {
            "role": "cargo",
            "executable": "cargo.EXE",
            "path_redacted": True,
            "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7",
            "version_exit_code": 0,
            "version_output_sha256": "4e9216fb7cac2573c1a8d60be140200103a52ab9fd9415070d94a98b1ef5973a",
        },
        "rustc": {
            "role": "rustc",
            "executable": "rustc.EXE",
            "path_redacted": True,
            "file_sha256": "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7",
            "version_exit_code": 0,
            "version_output_sha256": "d6dec673ca010f6a7d90aa3f4a896ad9d88b66b8fe090296c298eddfe9a406db",
        },
        "uv": {
            "role": "uv",
            "executable": "uv.EXE",
            "path_redacted": True,
            "file_sha256": "5a7ec85884c2ccb1be560cb8fac3eb890df1adf49bfcc070a270ba70401bdd68",
            "version_exit_code": 0,
            "version_output_sha256": "ab0d29803cb58959acc6cf64650fb215c72c2989b94fb6f9de5f22814ceca82d",
        },
        "python": {
            "role": "python",
            "executable": "python.EXE",
            "path_redacted": True,
            "file_sha256": "ee3131591ecdc30ebc9221769239e9d89df47380ed01e1b25ba2c68f6e808417",
            "version_exit_code": 0,
            "version_output_sha256": "92f6867409cdf8c3f751b9944dd73439d19ddc74b01315c6cafb474011d2fa1e",
        },
    },
}
EXPECTED_TOOLCHAINS["PB-02"] = dict(EXPECTED_TOOLCHAINS["PB-01"])

EXPECTED_SOURCE = {
    "PB-01": {
        "candidate_keys": ["archive_sha256", "cargo_lock_sha256", "commit", "inventory", "rust_toolchain_sha256", "tree"],
        "upstream_keys": ["archive_sha256", "commit", "inventory", "license_sha256", "tree", "uv_lock_sha256"],
        "candidate_inventory_sha256": "a037cb5c972b258a059b2e9501f07eb27f51c1fd3feb0947ea846121564ab0b6",
        "upstream_inventory_sha256": "60550ce1cbb83fdf481e6cd2534b7063c684df3c6094838d2f4b6c1714776ed1",
    },
    "PB-02": {
        "candidate_keys": ["archive_sha256", "cargo_lock_sha256", "commit", "inventory", "rust_toolchain_sha256", "tree"],
        "upstream_keys": ["archive_sha256", "commit", "inventory", "license_sha256", "native_core_cargo_lock_sha256", "tree", "uv_lock_sha256"],
        "candidate_inventory_sha256": "a037cb5c972b258a059b2e9501f07eb27f51c1fd3feb0947ea846121564ab0b6",
        "upstream_inventory_sha256": "26ccbee692b9c4984c6cee0cff6c3987fc013e914905a66019937f940a5abfb9",
    },
    "PB-03": {
        "candidate_keys": ["archive_sha256", "commit", "tree"],
        "upstream_keys": ["archive_sha256", "commit", "tree"],
        "candidate_inventory_sha256": None,
        "upstream_inventory_sha256": None,
    },
}

CARGO_LOCK_SHA256 = "b5edc5d3222383490ed0ca274fed1c8d009ca43188227531e54887d1bd682403"
RUST_TOOLCHAIN_SHA256 = "3cc13c37191008eaab5490eea2136223fa1bc5b5d2aa9c74a199a0c0c854aa90"
UPSTREAM_LICENSE_SHA256 = "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1"
UPSTREAM_UV_LOCK_SHA256 = "624b62d7a84fbc48579de17e2ae171f5e4190d6ad7e5231e67ddafb9d3fa0d86"

EXPECTED_HARNESS_PB01 = {
    "source_mode": "git_archive_at_immutable_commit",
    "runner": {
        "path": "tools/run_pb_01_legacy_leaf_replay.py",
        "sha256": REPLAY_RUNNERS["tools/run_pb_01_legacy_leaf_replay.py"],
    },
    "custody_runner_helper": {
        "path": "tools/run_pb_02_direct_replay.py",
        "sha256": REPLAY_RUNNERS["tools/run_pb_02_direct_replay.py"],
    },
}

EXPECTED_AUDIT_SHA256 = "ae0a25f90f5dd310af8fb62f8624d7979a7ea2b33636b18dccbe8af068283cce"
EXPECTED_NORMALIZED_ANCHOR_SHA256 = "bfd472d138fde41cdf2c1c061a2bc02f46152451ac768a68d4d0f7c694b09d6b"
EXPECTED_NORMALIZED_VERIFIER_SHA256 = "69eca360a9e7a8acdd55a32b36ec4fb129a37370bc3d4092b64bb6bb22d56c79"
EXPECTED_NORMALIZED_MUTATION_TESTS_SHA256 = "7c992c9d4fe4fd5ef260e48b4cc22146d3b4d546e907b550f05ca57feecbc5e2"

EXPECTED_AUDIT_PATH = "docs/baselines/audits/2026-08-26-pb-01-03-current-scoped-replay-bc882d2e.md"
EXPECTED_MANIFEST_KEYS = {
    "anchors",
    "claims",
    "date",
    "evidence",
    "non_claims",
    "rows",
    "schema",
    "scope",
    "status",
    "toolchain_gate",
}
EXPECTED_EVIDENCE_KEYS = {"audit", "audit_sha256", "mutation_tests", "replay_runners", "verifier"}
EXPECTED_REPORT_BINDING_KEYS = {"fresh_run_nonce", "path", "run_id", "sha256"}
EXPECTED_ROW_KEYS = {
    "PB-01": {"artifact", "command", "fixture", "id", "reports", "source", "toolchain"},
    "PB-02": {"artifact", "command", "fixture", "id", "reports", "source", "toolchain"},
    "PB-03": {"artifact", "command", "fixture", "id", "reports", "source", "stable_subset", "toolchain"},
}
HARNESS_NORMALIZATION_ALGORITHM = "sha256-source-with-dynamic-assignment-lines-removed-v1"
HARNESS_VERIFIER_PATH = "tools/verify_pb_01_03_current_scoped_replay.py"
HARNESS_MUTATION_TESTS_PATH = "tools/test_verify_pb_01_03_current_scoped_replay.py"


def _expected_harness_anchors() -> dict[str, Any]:
    return {
        "algorithm": HARNESS_NORMALIZATION_ALGORITHM,
        "mutation_tests": {
            "path": HARNESS_MUTATION_TESTS_PATH,
            "normalized_sha256": EXPECTED_NORMALIZED_MUTATION_TESTS_SHA256,
        },
        "verifier": {
            "path": HARNESS_VERIFIER_PATH,
            "normalized_sha256": EXPECTED_NORMALIZED_VERIFIER_SHA256,
        },
    }

EXPECTED_TOP_KEYS = {
    "PB-01": {
        "artifact_contract",
        "candidate",
        "fixture",
        "fresh_run_nonce",
        "harness",
        "non_claims",
        "replay",
        "reproducibility",
        "run_id",
        "schema",
        "source_mode",
        "status",
        "toolchain",
        "upstream",
    },
    "PB-02": {
        "candidate",
        "custody",
        "fixture",
        "fresh_run_nonce",
        "non_claims",
        "replay",
        "run_id",
        "schema",
        "source_mode",
        "status",
        "toolchain",
        "upstream",
    },
    "PB-03": {
        "blockers",
        "build",
        "candidate",
        "claims",
        "custody",
        "fixture",
        "fresh_run_nonce",
        "non_claims",
        "replay",
        "row",
        "run_id",
        "schema",
        "source_mode",
        "status",
        "toolchain",
        "upstream",
    },
}

EXPECTED_NON_CLAIMS = {
    "PB-01": [
        "This is one scoped NRZ analytic-metallic-line 23-key dictionary leaf, not complete PyBERT branch parity.",
        "The Rust artifact is a Python-readable canonical-item dictionary, not a PyBertData class-compatible pickle.",
        "Imported S2P, .pybert_cfg pickle input, AMI/IBIS, periodic/random noise, adaptive DFE/Viterbi, and jitter/eye/bathtub branches remain open.",
        "The external Python invocation is oracle evidence only; the Rust candidate does not call Python at runtime.",
        "This report is not a license decision, product admission, release approval, or redistribution authorization.",
    ],
    "PB-02": [
        "This report does not prove parity for uncovered SimulationInputV1 branches.",
        "SIPI strict JSON, artifact, NPZ compression, and symlink policies are wrapper behavior, not upstream sim-native semantics.",
        "The report is not a license decision, release approval, or product capability admission.",
    ],
    "PB-03": [
        "This is one frozen fixture only.",
        "PB-03 payload parity is only the fixed stable array subset, not whole-payload parity.",
        "The candidate and oracle do not prove independent implementations.",
        "Uncovered branches, global parity, product capability, and release approval remain open.",
    ],
}

EXPECTED_PB02_CUSTODY = {
    "materialized_archives_created_new": True,
    "run_root_created_new": True,
    "run_root_path_redacted": True,
    "work_root_empty_before_run": True,
    "work_root_outside_candidate_repo": True,
    "work_root_outside_upstream_repo": True,
    "work_root_path_redacted": True,
}
EXPECTED_PB03_CUSTODY = {
    "materialized_archives_created_new": True,
    "run_root_created_new": True,
    "work_root_created_new": True,
    "work_root_outside_candidate_repo": True,
    "work_root_outside_upstream_repo": True,
    "work_root_path_redacted": True,
}

EXPECTED_PB03_BUILD = {
    EXPECTED_REPORTS["PB-03"][0]["path"]: {
        "binary_sha256": "58ea6bb94229379d1c3fa9e7f4b4093bf97d46e6f28eb3be5c8bc0075657bf58",
        "stderr_sha256": "fbcaae7c0df779417f492d9debfc81b6a464c86da5e99c2d2a9bdb2416289e3e",
        "canonical_sha256": "65add294634cf5728505791ee9edea254db03cd351df6bac05442a855a077095",
        "timestamp_hex": "34698d6a",
        "guid_hex": "e797a2f9d7e9e24ca1e9769b96933adc",
    },
    EXPECTED_REPORTS["PB-03"][1]["path"]: {
        "binary_sha256": "2b181ddb422fab7243102f9b49828fa101204b28efb92fe3c0f62a820b656a17",
        "stderr_sha256": "6f5fb95046871993ec8293e0f5b1bcfafc13130f70027e68d816fe7c3c25a006",
        "canonical_sha256": "bef05a2775c74ad1e43172c28843715efe575e3fd6ec410f4e612c073bd6e930",
        "timestamp_hex": "b8698d6a",
        "guid_hex": "4c85d256a3cfe44596fcbb5c8f27c444",
    },
}

PB01_FIXTURE = {
    "path": "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml",
    "bytes": 1171,
    "sha256": "d63bb7ab3466ae70406cd2a555ae5a95cda1264021fed8fb1cdca85da961cc48",
}
PB02_FIXTURE = {
    "path": "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json",
    "bytes": 1245,
    "sha256": "5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13",
}
PB03_FIXTURE = {
    "path": "crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml",
    "bytes": 1170,
    "sha256": "2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f",
}


def _expected_manifest_source(row: str) -> dict[str, Any]:
    expected = EXPECTED_SOURCE[row]
    return {
        "candidate": {
            "archive_sha256": CANDIDATE_ARCHIVE,
            "commit": CANDIDATE_COMMIT,
            "inventory_sha256": expected["candidate_inventory_sha256"],
            "tree": CANDIDATE_TREE,
        },
        "upstream": {
            "archive_sha256": UPSTREAM_ARCHIVE,
            "commit": UPSTREAM_COMMIT,
            "inventory_sha256": expected["upstream_inventory_sha256"],
            "tree": UPSTREAM_TREE,
        },
    }


def _normalized_anchor_payload() -> dict[str, Any]:
    return {
        "candidate": {
            "archive_sha256": CANDIDATE_ARCHIVE,
            "commit": CANDIDATE_COMMIT,
            "tree": CANDIDATE_TREE,
        },
        "harness": _expected_harness_anchors(),
        "rows": {
            row: {
                "report_schema": {"PB-01": PB01_SCHEMA, "PB-02": PB02_SCHEMA, "PB-03": PB03_SCHEMA}[row],
                "reports": EXPECTED_REPORTS[row],
                "source": _expected_manifest_source(row),
                "toolchain": EXPECTED_TOOLCHAINS[row],
            }
            for row in ("PB-01", "PB-02", "PB-03")
        },
        "upstream": {
            "archive_sha256": UPSTREAM_ARCHIVE,
            "commit": UPSTREAM_COMMIT,
            "tree": UPSTREAM_TREE,
        },
    }


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


_DYNAMIC_ASSIGNMENT_PREFIXES = (
    b"EXPECTED_AUDIT_SHA256 = ",
    b"EXPECTED_NORMALIZED_ANCHOR_SHA256 = ",
    b"EXPECTED_NORMALIZED_VERIFIER_SHA256 = ",
    b"EXPECTED_NORMALIZED_MUTATION_TESTS_SHA256 = ",
)


def _normalized_source_sha(path: Path, strip_dynamic_assignments: bool) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if strip_dynamic_assignments:
        lines = raw.splitlines(keepends=True)
        raw = b"".join(line for line in lines if not any(line.startswith(prefix) for prefix in _DYNAMIC_ASSIGNMENT_PREFIXES))
    return hashlib.sha256(raw).hexdigest()


def _path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return not posix.is_absolute() and not windows.is_absolute() and not windows.drive and ".." not in posix.parts


def _path_free(value: Any) -> bool:
    return PATH_LEAK.search(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)) is None


def _check(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _check_keys(value: Any, expected: set[str], label: str, errors: list[str]) -> None:
    _check(errors, isinstance(value, dict) and set(value) == expected, f"{label} schema drift")


def _load_json(root: Path, relative: Any, errors: list[str], label: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    _check(errors, _path(relative), f"{label} path is not repository-relative")
    if not _path(relative):
        return None, None, None
    target = root / relative
    try:
        raw = target.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as error:
        errors.append(f"{label} cannot be loaded: {error}")
        return None, _sha(target), None
    _check(errors, isinstance(value, dict), f"{label} is not an object")
    return value if isinstance(value, dict) else None, _sha(target), raw


def _check_hash(value: Any, label: str, errors: list[str]) -> None:
    _check(errors, isinstance(value, str) and HEX64.fullmatch(value) is not None, f"{label} must be a lowercase SHA-256")


def _check_inventory(value: Any, expected_sha256: str, label: str, errors: list[str]) -> None:
    _check(errors, isinstance(value, dict) and set(value) == {"entries", "sha256"}, f"{label} shape drift")
    if not isinstance(value, dict):
        return
    entries = value.get("entries")
    _check(errors, isinstance(entries, list) and bool(entries), f"{label} entries missing")
    _check_hash(value.get("sha256"), f"{label} digest", errors)
    if not isinstance(entries, list):
        return
    normalized: list[dict[str, Any]] = []
    paths: list[str] = []
    for index, entry in enumerate(entries):
        prefix = f"{label} entry-{index + 1}"
        _check(errors, isinstance(entry, dict) and set(entry) == {"bytes", "path", "sha256"}, f"{prefix} shape drift")
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        _check(errors, _path(path), f"{prefix} path drift")
        _check(errors, isinstance(entry.get("bytes"), int) and entry["bytes"] > 0, f"{prefix} byte count drift")
        _check_hash(entry.get("sha256"), prefix, errors)
        if _path(path):
            paths.append(path)
        normalized.append(entry)
    _check(errors, paths == sorted(paths) and len(paths) == len(set(paths)), f"{label} ordering or duplicate drift")
    _check(errors, value.get("sha256") == expected_sha256, f"{label} anchored digest drift")
    _check(errors, hashlib.sha256(_canonical(normalized)).hexdigest() == value.get("sha256"), f"{label} canonical digest mismatch")


def _check_source(report: dict[str, Any], row: str, errors: list[str]) -> None:
    candidate = report.get("candidate")
    upstream = report.get("upstream")
    expected = EXPECTED_SOURCE[row]
    _check(errors, isinstance(candidate, dict), f"{row} candidate source missing")
    _check(errors, isinstance(upstream, dict), f"{row} upstream source missing")
    if isinstance(candidate, dict):
        _check(errors, sorted(candidate) == expected["candidate_keys"], f"{row} candidate source schema drift")
        _check(errors, candidate.get("commit") == CANDIDATE_COMMIT, f"{row} candidate commit drift")
        _check(errors, candidate.get("tree") == CANDIDATE_TREE, f"{row} candidate tree drift")
        _check(errors, candidate.get("archive_sha256") == CANDIDATE_ARCHIVE, f"{row} candidate archive drift")
        if expected["candidate_inventory_sha256"] is None:
            _check(errors, "inventory" not in candidate, f"{row} candidate inventory unexpectedly promoted")
        else:
            _check_inventory(candidate.get("inventory"), expected["candidate_inventory_sha256"], f"{row} candidate inventory", errors)
        if row in {"PB-01", "PB-02"}:
            _check(errors, candidate.get("cargo_lock_sha256") == CARGO_LOCK_SHA256, f"{row} candidate cargo lock drift")
            _check(errors, candidate.get("rust_toolchain_sha256") == RUST_TOOLCHAIN_SHA256, f"{row} candidate Rust toolchain drift")
    if isinstance(upstream, dict):
        _check(errors, sorted(upstream) == expected["upstream_keys"], f"{row} upstream source schema drift")
        _check(errors, upstream.get("commit") == UPSTREAM_COMMIT, f"{row} upstream commit drift")
        _check(errors, upstream.get("tree") == UPSTREAM_TREE, f"{row} upstream tree drift")
        _check(errors, upstream.get("archive_sha256") == UPSTREAM_ARCHIVE, f"{row} upstream archive drift")
        if expected["upstream_inventory_sha256"] is None:
            _check(errors, "inventory" not in upstream, f"{row} upstream inventory unexpectedly promoted")
        else:
            _check_inventory(upstream.get("inventory"), expected["upstream_inventory_sha256"], f"{row} upstream inventory", errors)
        if row in {"PB-01", "PB-02"}:
            _check(errors, upstream.get("license_sha256") == UPSTREAM_LICENSE_SHA256, f"{row} upstream license drift")
            _check(errors, upstream.get("uv_lock_sha256") == UPSTREAM_UV_LOCK_SHA256, f"{row} upstream uv lock drift")
        if row == "PB-02":
            _check(errors, upstream.get("native_core_cargo_lock_sha256") is None, "PB-02 native core lock boundary drift")


def _check_toolchain(value: Any, row: str, errors: list[str]) -> None:
    _check(errors, isinstance(value, dict), f"{row} toolchain missing")
    if not isinstance(value, dict):
        return
    _check(errors, value == EXPECTED_TOOLCHAINS[row], f"{row} toolchain anchor drift")
    _check(errors, isinstance(value.get("timeout_seconds"), int) and value["timeout_seconds"] > 0, f"{row} toolchain timeout malformed")
    for role in EXPECTED_TOOLCHAINS[row]:
        if role == "timeout_seconds":
            continue
        item = value.get(role)
        _check(errors, isinstance(item, dict), f"{row} {role} identity missing")
        if not isinstance(item, dict):
            continue
        required = {"role", "executable", "path_redacted", "file_sha256", "version_exit_code", "version_output_sha256"}
        _check(errors, set(item) == required, f"{row} {role} identity shape drift")
        _check(errors, item.get("role") == role, f"{row} {role} role drift")
        executable = item.get("executable")
        _check(errors, isinstance(executable, str) and bool(executable) and not any(c in executable for c in ("/", "\\", ":")), f"{row} {role} executable leaks a path")
        _check(errors, item.get("path_redacted") is True, f"{row} {role} path-redaction drift")
        _check(errors, item.get("version_exit_code") == 0, f"{row} {role} version failed")
        _check_hash(item.get("file_sha256"), f"{row} {role} executable digest", errors)
        _check_hash(item.get("version_output_sha256"), f"{row} {role} version digest", errors)


def _check_common_report(report: dict[str, Any], row: str, fixture: dict[str, Any], errors: list[str]) -> None:
    expected_schema = {"PB-01": PB01_SCHEMA, "PB-02": PB02_SCHEMA, "PB-03": PB03_SCHEMA}[row]
    _check(errors, set(report) == EXPECTED_TOP_KEYS[row], f"{row} report top-level schema drift")
    _check(errors, report.get("schema") == expected_schema, f"{row} report schema drift")
    _check(errors, report.get("status") == "passed", f"{row} report is not passed")
    _check(errors, report.get("source_mode") == "git_archive_at_immutable_commit", f"{row} source mode drift")
    _check(errors, isinstance(report.get("run_id"), str) and bool(report.get("run_id")), f"{row} run ID missing")
    nonce = report.get("fresh_run_nonce")
    _check(errors, isinstance(nonce, str) and NONCE.fullmatch(nonce) is not None, f"{row} fresh nonce malformed")
    if "blockers" in report:
        _check(errors, report.get("blockers") == [], f"{row} report blockers are not empty")
    expected_fixture = dict(fixture)
    expected_fixture["archive_present"] = True
    _check(errors, report.get("fixture") == expected_fixture, f"{row} fixture binding drift")
    _check_source(report, row, errors)
    _check_toolchain(report.get("toolchain"), row, errors)
    _check(errors, report.get("non_claims") == EXPECTED_NON_CLAIMS[row], f"{row} non-claim schema/content drift")
    if row == "PB-01":
        _check(errors, report.get("reproducibility") == {"binary_bit_reproducible": False}, "PB-01 reproducibility boundary drift")
        _check(errors, report.get("harness") == EXPECTED_HARNESS_PB01, "PB-01 harness anchor drift")
    elif row == "PB-02":
        _check(errors, report.get("custody") == EXPECTED_PB02_CUSTODY, "PB-02 custody schema/claim drift")
        replay = report.get("replay")
        if isinstance(replay, dict):
            _check(errors, set(replay) == {"build", "candidate", "oracle", "parity"}, "PB-02 replay schema drift")
    else:
        _check(errors, report.get("row") == "PB-03", "PB-03 row anchor drift")
        _check(errors, report.get("custody") == EXPECTED_PB03_CUSTODY, "PB-03 custody schema/claim drift")
        _check(errors, report.get("blockers") == [], "PB-03 blocker boundary drift")
        replay = report.get("replay")
        if isinstance(replay, dict):
            _check(errors, set(replay) == {"candidate_artifact", "candidate_process", "comparison", "oracle_artifact", "oracle_process", "payload", "selection", "semantic_gate"}, "PB-03 replay schema drift")
    _check(errors, _path_free(report), f"{row} report contains an absolute host path")


def _check_pb01(report: dict[str, Any], errors: list[str]) -> None:
    contract = report.get("artifact_contract")
    _check_keys(contract, {"array_key_policy", "canonical_item_names", "result_suffix", "rust_codec", "selected_arrays", "upstream_codec"}, "PB-01 artifact contract", errors)
    if isinstance(contract, dict):
        _check(errors, contract.get("canonical_item_names") == list(PB01_ITEMS), "PB-01 canonical 23-key list drift")
        _check(errors, contract.get("selected_arrays") == list(PB01_SELECTED), "PB-01 selected array list drift")
        _check(errors, contract.get("array_key_policy") == "exact_set_equal_to_canonical_item_names", "PB-01 array-key policy drift")
        _check(errors, contract.get("result_suffix") == ".pybert_data", "PB-01 result suffix drift")
        _check(errors, contract.get("rust_codec") == "python_pickle_dict_sipi.pybert_data.v1", "PB-01 dictionary codec drift")
        _check(errors, contract.get("upstream_codec") == "PyBertData_pickle", "PB-01 oracle codec drift")
    schema = report.get("replay", {}).get("candidate_artifact_schema") if isinstance(report.get("replay"), dict) else None
    _check(
        errors,
        schema
        == {
            "kind": "python_pickle_dict",
            "schema": "sipi.pybert_data.v1",
            "item_names": list(PB01_ITEMS),
            "array_keys": sorted(PB01_ITEMS),
        },
        "PB-01 default dictionary schema drift",
    )
    replay = report.get("replay")
    _check_keys(replay, {"build", "candidate", "candidate_artifact_schema", "comparison", "oracle"}, "PB-01 replay", errors)
    if not isinstance(replay, dict):
        return
    _check_keys(replay.get("candidate_artifact_schema"), {"array_keys", "item_names", "kind", "schema"}, "PB-01 artifact schema", errors)
    comparison = replay.get("comparison")
    _check_keys(comparison, {"arrays", "blockers", "policy", "status"}, "PB-01 comparison", errors)
    if isinstance(comparison, dict):
        _check(errors, comparison.get("status") == "passed" and comparison.get("blockers") == [], "PB-01 comparison gate drift")
        _check_keys(comparison.get("policy"), {"absolute_tolerance", "formula", "relative_scale"}, "PB-01 comparison policy", errors)
        rows = comparison.get("arrays")
        _check(errors, isinstance(rows, list) and [item.get("name") for item in rows] == list(PB01_SELECTED), "PB-01 selected comparison names drift")
        if isinstance(rows, list):
            for item in rows:
                _check_keys(item, {"length", "max_abs", "name", "passed", "scale", "tolerance"}, "PB-01 comparison item", errors)
                _check(errors, isinstance(item, dict) and item.get("passed") is True, "PB-01 selected array did not pass")
                if not isinstance(item, dict):
                    continue
                numeric = [item.get("max_abs"), item.get("scale"), item.get("tolerance")]
                _check(errors, isinstance(item.get("length"), int) and item["length"] > 0, "PB-01 comparison length malformed")
                _check(errors, all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in numeric), "PB-01 comparison numeric fact malformed")
                if all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in numeric):
                    _check(errors, item["scale"] >= 1.0 and item["max_abs"] >= 0.0, "PB-01 comparison scale drift")
                    _check(errors, math.isclose(item["tolerance"], 1.0e-7 + 1.0e-6 * item["scale"], rel_tol=0.0, abs_tol=1.0e-15), "PB-01 tolerance formula drift")
                    _check(errors, item["max_abs"] <= item["tolerance"], "PB-01 selected array tolerance failed")
    for role in ("candidate", "oracle"):
        process = replay.get(role)
        _check_keys(process, {"artifact", "exit_code", "stderr_sha256", "stdout_sha256"}, f"PB-01 {role} process", errors)
        _check(errors, isinstance(process, dict) and process.get("exit_code") == 0, f"PB-01 {role} process failed")
        if isinstance(process, dict):
            artifact = process.get("artifact")
            _check_keys(artifact, {"bytes", "path", "present", "sha256"}, f"PB-01 {role} artifact", errors)
            _check(errors, isinstance(artifact, dict) and artifact.get("present") is True, f"PB-01 {role} artifact missing")
            if isinstance(artifact, dict):
                _check(errors, isinstance(artifact.get("bytes"), int) and artifact["bytes"] > 0, f"PB-01 {role} artifact size malformed")
                _check_hash(artifact.get("sha256"), f"PB-01 {role} artifact", errors)
                _check(errors, _path(artifact.get("path")), f"PB-01 {role} artifact path drift")
    build = replay.get("build")
    _check_keys(build, {"binary_bytes", "binary_sha256", "exit_code", "stderr_sha256", "stdout_sha256"}, "PB-01 build", errors)
    _check(errors, isinstance(build, dict) and build.get("exit_code") == 0, "PB-01 build failed")
    if isinstance(build, dict):
        _check_hash(build.get("binary_sha256"), "PB-01 binary", errors)
        _check(errors, isinstance(build.get("binary_bytes"), int) and build["binary_bytes"] > 0, "PB-01 binary size malformed")
    claims = report.get("non_claims")
    joined = "\n".join(claims) if isinstance(claims, list) else ""
    for phrase in ("not a PyBertData class-compatible pickle", "Imported S2P", "AMI/IBIS", "adaptive DFE/Viterbi"):
        _check(errors, phrase in joined, f"PB-01 non-claim boundary missing: {phrase}")


def _check_pb02(report: dict[str, Any], errors: list[str]) -> None:
    replay = report.get("replay")
    _check_keys(replay, {"build", "candidate", "oracle", "parity"}, "PB-02 replay", errors)
    if not isinstance(replay, dict):
        return
    _check_keys(replay.get("build"), {"binary_bytes", "binary_sha256", "exit_code", "stderr_sha256", "stdout_sha256"}, "PB-02 build", errors)
    parity = replay.get("parity")
    _check_keys(parity, {"array_member_names", "candidate_array_members_equal_oracle", "candidate_exit_zero", "oracle_exit_zero"}, "PB-02 parity", errors)
    if isinstance(parity, dict):
        _check(errors, parity.get("array_member_names") == list(PB02_MEMBERS), "PB-02 eleven-member list drift")
        _check(errors, parity.get("candidate_array_members_equal_oracle") is True, "PB-02 member equality gate drift")
        _check(errors, parity.get("candidate_exit_zero") is True and parity.get("oracle_exit_zero") is True, "PB-02 process gate drift")
    logical_summaries: list[dict[str, Any]] = []
    for role in ("candidate", "oracle"):
        process = replay.get(role)
        _check_keys(process, {"artifacts", "exit_code", "stderr_sha256", "stdout_sha256"}, f"PB-02 {role} process", errors)
        _check(errors, isinstance(process, dict) and process.get("exit_code") == 0, f"PB-02 {role} process failed")
        if not isinstance(process, dict):
            continue
        _check_hash(process.get("stderr_sha256"), f"PB-02 {role} stderr", errors)
        _check_hash(process.get("stdout_sha256"), f"PB-02 {role} stdout", errors)
        artifacts = process.get("artifacts")
        _check_keys(
            artifacts,
            {"arrays", "arrays_present", "meta_json_valid", "meta_normalized_sha256", "meta_present", "meta_schema", "meta_sha256"},
            f"PB-02 {role} artifacts",
            errors,
        )
        if isinstance(artifacts, dict):
            _check(errors, artifacts.get("arrays_present") is True, f"PB-02 {role} arrays presence drift")
            _check(errors, artifacts.get("meta_present") is True and artifacts.get("meta_json_valid") is True, f"PB-02 {role} metadata gate drift")
            _check(errors, artifacts.get("meta_schema") == "pybert.native-cli-result.v1", f"PB-02 {role} metadata schema drift")
            _check_hash(artifacts.get("meta_sha256"), f"PB-02 {role} metadata", errors)
            _check_hash(artifacts.get("meta_normalized_sha256"), f"PB-02 {role} normalized metadata", errors)
        arrays = artifacts.get("arrays") if isinstance(artifacts, dict) else None
        _check(errors, isinstance(arrays, dict), f"PB-02 {role} arrays summary missing")
        if not isinstance(arrays, dict):
            continue
        _check_keys(arrays, {"bytes", "logical_members", "logical_sha256", "member_bytes", "member_sha256", "sha256"}, f"PB-02 {role} arrays", errors)
        members = arrays.get("logical_members")
        _check(errors, isinstance(members, dict) and list(members) == list(PB02_MEMBERS), f"PB-02 {role} logical member set drift")
        if isinstance(members, dict):
            for member_name, member in members.items():
                _check_keys(member, {"count", "dtype", "f64_sha256", "fortran_order", "shape"}, f"PB-02 {role} member {member_name}", errors)
                if isinstance(member, dict):
                    _check(errors, isinstance(member.get("count"), int) and member["count"] > 0, f"PB-02 {role} member count malformed")
                    _check(errors, isinstance(member.get("dtype"), str) and bool(member["dtype"]), f"PB-02 {role} member dtype malformed")
                    _check_hash(member.get("f64_sha256"), f"PB-02 {role} member {member_name} f64", errors)
                    _check(errors, isinstance(member.get("fortran_order"), bool), f"PB-02 {role} member order malformed")
                    _check(errors, isinstance(member.get("shape"), list) and all(isinstance(dim, int) and dim >= 0 for dim in member["shape"]), f"PB-02 {role} member shape malformed")
        _check(errors, arrays.get("logical_sha256") == PB02_LOGICAL_SHA, f"PB-02 {role} logical digest drift")
        _check(errors, isinstance(arrays.get("bytes"), int) and arrays["bytes"] > 0, f"PB-02 {role} NPZ size malformed")
        _check_hash(arrays.get("sha256"), f"PB-02 {role} NPZ", errors)
        member_bytes = arrays.get("member_bytes")
        _check(errors, isinstance(member_bytes, dict) and list(member_bytes) == list(PB02_MEMBERS), f"PB-02 {role} member byte map drift")
        if isinstance(member_bytes, dict):
            for member_name, member_size in member_bytes.items():
                _check(errors, isinstance(member_size, int) and member_size > 0, f"PB-02 {role} member {member_name} byte count malformed")
        member_sha256 = arrays.get("member_sha256")
        _check(errors, isinstance(member_sha256, dict) and list(member_sha256) == list(PB02_MEMBERS), f"PB-02 {role} member SHA map drift")
        if isinstance(member_sha256, dict):
            for member_name, member_digest in member_sha256.items():
                _check_hash(member_digest, f"PB-02 {role} member {member_name}", errors)
        logical_summaries.append(arrays)
    if len(logical_summaries) == 2:
        _check(errors, logical_summaries[0].get("logical_members") == logical_summaries[1].get("logical_members"), "PB-02 member facts differ")
        _check(errors, logical_summaries[0].get("logical_sha256") == logical_summaries[1].get("logical_sha256"), "PB-02 logical digests differ")
    build = replay.get("build")
    _check(errors, isinstance(build, dict) and build.get("exit_code") == 0, "PB-02 build failed")
    if isinstance(build, dict):
        _check_hash(build.get("binary_sha256"), "PB-02 binary", errors)
        _check_hash(build.get("stderr_sha256"), "PB-02 build stderr", errors)
        _check_hash(build.get("stdout_sha256"), "PB-02 build stdout", errors)
        _check(errors, isinstance(build.get("binary_bytes"), int) and build["binary_bytes"] > 0, "PB-02 binary size malformed")


def _check_pb03_build(build: Any, report_path: str, errors: list[str]) -> None:
    _check_keys(build, {"binary_custody", "binary_sha256", "exit_code", "stderr_sha256", "stdout_sha256"}, "PB-03 build", errors)
    if not isinstance(build, dict):
        return
    expected_binary = EXPECTED_PB03_BUILD.get(report_path)
    _check(errors, expected_binary is not None, "PB-03 build report anchor missing")
    _check(errors, build.get("exit_code") == 0, "PB-03 build exit gate drift")
    _check(errors, build.get("binary_sha256") == expected_binary["binary_sha256"] if expected_binary else False, "PB-03 binary SHA anchor drift")
    _check(errors, build.get("stderr_sha256") == expected_binary["stderr_sha256"] if expected_binary else False, "PB-03 build stderr anchor drift")
    _check(errors, build.get("stdout_sha256") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "PB-03 build stdout anchor drift")
    custody = build.get("binary_custody")
    _check_keys(custody, {"bytes", "canonical_sha256", "characteristics", "format", "machine", "normalization", "profile", "raw_sha256", "repro_entry", "schema"}, "PB-03 PE custody", errors)
    if not isinstance(custody, dict) or expected_binary is None:
        return
    _check(errors, custody.get("bytes") == 3631616, "PB-03 PE byte count drift")
    _check(errors, custody.get("canonical_sha256") == expected_binary["canonical_sha256"], "PB-03 PE canonical SHA drift")
    _check(errors, custody.get("raw_sha256") == expected_binary["binary_sha256"], "PB-03 PE raw SHA drift")
    _check(errors, custody.get("canonical_sha256") == build.get("binary_custody", {}).get("canonical_sha256"), "PB-03 PE canonical self-binding drift")
    _check(errors, custody.get("characteristics") == 34 and custody.get("format") == "PE" and custody.get("machine") == 34404 and custody.get("profile") == "pe32-plus", "PB-03 PE identity drift")
    _check(errors, custody.get("schema") == "sipi.windows-pe-replay-custody.v1", "PB-03 PE custody schema drift")
    normalization = custody.get("normalization")
    _check_keys(normalization, {"changed_byte_count", "fields", "map", "ranges"}, "PB-03 PE normalization", errors)
    if isinstance(normalization, dict):
        expected_fields = [
            "IMAGE_FILE_HEADER.TimeDateStamp",
            "IMAGE_DEBUG_DIRECTORY[0].TimeDateStamp",
            "IMAGE_DEBUG_DIRECTORY[1].TimeDateStamp",
            "IMAGE_DEBUG_DIRECTORY[2].TimeDateStamp",
            "CodeView.RSDS[0].GUID",
        ]
        _check(errors, normalization.get("changed_byte_count") == 32, "PB-03 PE normalization count drift")
        _check(errors, normalization.get("fields") == expected_fields, "PB-03 PE normalization fields drift")
        _check(errors, normalization.get("map") == "zero-only:IMAGE_FILE_HEADER.TimeDateStamp+IMAGE_DEBUG_DIRECTORY.TimeDateStamp+CodeView.RSDS.GUID", "PB-03 PE normalization map drift")
        ranges = normalization.get("ranges")
        _check(errors, isinstance(ranges, list) and len(ranges) == 5, "PB-03 PE normalization ranges drift")
        if isinstance(ranges, list) and len(ranges) == 5:
            expected_ranges = [
                {"canonical_hex": "00000000", "field": "IMAGE_FILE_HEADER.TimeDateStamp", "length": 4, "offset": 240, "raw_hex": expected_binary["timestamp_hex"]},
                {"canonical_hex": "00000000", "field": "IMAGE_DEBUG_DIRECTORY[0].TimeDateStamp", "length": 4, "offset": 3197348, "raw_hex": expected_binary["timestamp_hex"]},
                {"canonical_hex": "00000000", "field": "IMAGE_DEBUG_DIRECTORY[1].TimeDateStamp", "length": 4, "offset": 3197376, "raw_hex": expected_binary["timestamp_hex"]},
                {"canonical_hex": "00000000", "field": "IMAGE_DEBUG_DIRECTORY[2].TimeDateStamp", "length": 4, "offset": 3197404, "raw_hex": expected_binary["timestamp_hex"]},
                {"canonical_hex": "00000000000000000000000000000000", "field": "CodeView.RSDS[0].GUID", "length": 16, "offset": 3197680, "raw_hex": expected_binary["guid_hex"]},
            ]
            _check(errors, ranges == expected_ranges, "PB-03 PE normalization range anchor drift")
    _check(errors, custody.get("repro_entry") == {"bytes": 0, "debug_directory_index": None, "present": False, "raw_sha256": None}, "PB-03 PE repro-entry boundary drift")


def _check_pb03(report: dict[str, Any], report_path: str, errors: list[str]) -> None:
    expected_claims = {
        "global_row_closed": False,
        "independent_implementation": False,
        "payload_parity": True,
        "payload_scope": "fixed_pb03_stable_array_subset",
        "release_approval": False,
        "whole_payload_parity": False,
    }
    _check(errors, report.get("claims") == expected_claims, "PB-03 claim boundary drift")
    _check_pb03_build(report.get("build"), report_path, errors)
    replay = report.get("replay")
    _check(errors, isinstance(replay, dict), "PB-03 replay missing")
    if not isinstance(replay, dict):
        return
    payload = replay.get("payload")
    _check(errors, payload == {"candidate_logical_sha256": PB03_STABLE_SHA, "equal": True, "oracle_logical_sha256": PB03_STABLE_SHA}, "PB-03 stable payload gate drift")
    _check(errors, replay.get("semantic_gate") is True, "PB-03 semantic gate drift")
    _check(errors, replay.get("selection") == {"candidate": None, "expected": None, "oracle": None}, "PB-03 selection boundary drift")
    summaries: list[dict[str, Any]] = []
    for role, expected_count in (("candidate_artifact", 113), ("oracle_artifact", 150)):
        artifact = replay.get(role)
        _check(errors, isinstance(artifact, dict), f"PB-03 {role} missing")
        if not isinstance(artifact, dict):
            continue
        _check_keys(
            artifact,
            {"arrays", "arrays_present", "comparison", "meta_json_valid", "meta_payload_sha256", "meta_present", "meta_schema", "meta_sha256", "selection"},
            f"PB-03 {role} schema",
            errors,
        )
        _check(errors, artifact.get("meta_present") is True and artifact.get("meta_json_valid") is True, f"PB-03 {role} metadata gate drift")
        _check(errors, artifact.get("meta_schema") == "pybert.native-cli-result.v1", f"PB-03 {role} metadata schema drift")
        _check_hash(artifact.get("meta_payload_sha256"), f"PB-03 {role} metadata payload", errors)
        _check_hash(artifact.get("meta_sha256"), f"PB-03 {role} metadata", errors)
        _check(errors, artifact.get("comparison") is None and artifact.get("selection") is None, f"PB-03 {role} wrapper comparison drift")
        arrays = artifact.get("arrays")
        _check(errors, isinstance(arrays, dict), f"PB-03 {role} arrays summary missing")
        if not isinstance(arrays, dict):
            continue
        _check_keys(arrays, {"bytes", "logical_member_count", "logical_members", "logical_sha256", "sha256"}, f"PB-03 {role} arrays", errors)
        _check(errors, arrays.get("logical_member_count") == expected_count, f"PB-03 {role} total member count drift")
        members = arrays.get("logical_members")
        _check(errors, isinstance(members, dict) and list(members) == list(PB03_STABLE), f"PB-03 {role} stable subset list drift")
        if isinstance(members, dict):
            _check(errors, len(members) == len(PB03_STABLE), f"PB-03 {role} stable subset count drift")
            _check(errors, hashlib.sha256(_canonical({name: members[name] for name in PB03_STABLE})).hexdigest() == PB03_STABLE_SHA, f"PB-03 {role} stable subset digest drift")
            for member_name, member in members.items():
                _check_keys(member, {"count", "dtype", "f64_sha256", "fortran_order", "shape"}, f"PB-03 {role} member {member_name}", errors)
                if isinstance(member, dict):
                    _check(errors, isinstance(member.get("count"), int) and member["count"] > 0, f"PB-03 {role} member count malformed")
                    _check(errors, isinstance(member.get("dtype"), str) and bool(member["dtype"]), f"PB-03 {role} member dtype malformed")
                    _check_hash(member.get("f64_sha256"), f"PB-03 {role} member {member_name} f64", errors)
                    _check(errors, isinstance(member.get("fortran_order"), bool), f"PB-03 {role} member order malformed")
                    _check(errors, isinstance(member.get("shape"), list) and all(isinstance(dim, int) and dim >= 0 for dim in member["shape"]), f"PB-03 {role} member shape malformed")
        _check(errors, isinstance(arrays.get("bytes"), int) and arrays["bytes"] > 0, f"PB-03 {role} NPZ size malformed")
        _check_hash(arrays.get("sha256"), f"PB-03 {role} NPZ", errors)
        _check_hash(arrays.get("logical_sha256"), f"PB-03 {role} total logical digest", errors)
        summaries.append(arrays)
    for role in ("candidate_process", "oracle_process"):
        process = replay.get(role)
        _check_keys(process, {"exit_code", "stderr_sha256", "stdout_sha256"}, f"PB-03 {role}", errors)
        _check(errors, isinstance(process, dict) and process.get("exit_code") == 0, f"PB-03 {role} failed")
        if isinstance(process, dict):
            _check_hash(process.get("stderr_sha256"), f"PB-03 {role} stderr", errors)
            _check_hash(process.get("stdout_sha256"), f"PB-03 {role} stdout", errors)
    if len(summaries) == 2:
        _check(errors, summaries[0].get("logical_member_count") < summaries[1].get("logical_member_count"), "PB-03 candidate/oracle total count boundary drift")
    for phrase in ("fixed stable array subset", "whole-payload parity", "global parity", "release approval"):
        joined = "\n".join(report.get("non_claims", [])) if isinstance(report.get("non_claims"), list) else ""
        _check(errors, phrase in joined, f"PB-03 non-claim boundary missing: {phrase}")


def _verify_row(manifest_row: dict[str, Any], root: Path, errors: list[str]) -> list[dict[str, Any]]:
    row = manifest_row.get("id")
    _check(errors, row in {"PB-01", "PB-02", "PB-03"}, "unknown row binding")
    if row not in {"PB-01", "PB-02", "PB-03"}:
        return []
    _check_keys(manifest_row, EXPECTED_ROW_KEYS[row], f"{row} manifest row", errors)
    expected_fixture = {"PB-01": PB01_FIXTURE, "PB-02": PB02_FIXTURE, "PB-03": PB03_FIXTURE}[row]
    _check(errors, manifest_row.get("fixture") == expected_fixture, f"{row} manifest fixture drift")
    expected_command = {"PB-01": "sim", "PB-02": "sim-native", "PB-03": "sim-rust"}[row]
    _check(errors, manifest_row.get("command") == expected_command, f"{row} manifest command drift")
    _check(errors, manifest_row.get("source") == _expected_manifest_source(row), f"{row} manifest source anchor drift")
    _check(errors, manifest_row.get("toolchain") == EXPECTED_TOOLCHAINS[row], f"{row} manifest toolchain anchor drift")
    expected_artifact = {
        "PB-01": {
            "default_dictionary_schema": "sipi.pybert_data.v1",
            "default_dictionary_item_count": 23,
            "selected_array_count": 12,
            "comparison_status": "passed",
            "exact_class_pickle_claim": False,
        },
        "PB-02": {
            "exact_npz_member_count": 11,
            "logical_sha256": PB02_LOGICAL_SHA,
            "comparison_status": "passed",
        },
        "PB-03": {
            "stable_subset_member_count": len(PB03_STABLE),
            "candidate_total_member_count": 113,
            "oracle_total_member_count": 150,
            "stable_subset_logical_sha256": PB03_STABLE_SHA,
            "whole_payload_parity": False,
            "comparison_status": "passed_scoped_subset_only",
        },
    }[row]
    _check(errors, manifest_row.get("artifact") == expected_artifact, f"{row} manifest artifact scope drift")
    if row == "PB-03":
        _check(errors, manifest_row.get("stable_subset") == list(PB03_STABLE), "PB-03 manifest stable subset drift")
    reports = manifest_row.get("reports")
    _check(errors, reports == EXPECTED_REPORTS[row], f"{row} report manifest anchors drift")
    _check(errors, isinstance(reports, list) and len(reports) == 2, f"{row} requires exactly two reports")
    loaded: list[dict[str, Any]] = []
    if not isinstance(reports, list):
        return loaded
    for index, binding in enumerate(reports):
        label = f"{row} report-{index + 1}"
        _check(errors, isinstance(binding, dict), f"{label} binding missing")
        if not isinstance(binding, dict):
            continue
        _check_keys(binding, EXPECTED_REPORT_BINDING_KEYS, f"{label} binding", errors)
        expected_binding = EXPECTED_REPORTS[row][index] if index < len(EXPECTED_REPORTS[row]) else {}
        _check(errors, binding == expected_binding, f"{label} hard anchor drift")
        report, actual_hash, raw = _load_json(root, binding.get("path"), errors, label)
        _check(errors, actual_hash == expected_binding.get("sha256"), f"{label} physical full-file SHA drift")
        _check(errors, actual_hash == binding.get("sha256"), f"{label} full-file SHA drift")
        _check(errors, isinstance(binding.get("sha256"), str) and HEX64.fullmatch(binding["sha256"]) is not None, f"{label} bound SHA malformed")
        _check(errors, isinstance(raw, str) and _path_free(raw), f"{label} report text contains an absolute host path")
        if report is None:
            continue
        _check(errors, report.get("run_id") == expected_binding.get("run_id"), f"{label} run ID binding drift")
        _check(errors, report.get("fresh_run_nonce") == expected_binding.get("fresh_run_nonce"), f"{label} nonce binding drift")
        _check_common_report(report, row, expected_fixture, errors)
        if row == "PB-01":
            _check_pb01(report, errors)
        elif row == "PB-02":
            _check_pb02(report, errors)
        else:
            _check_pb03(report, expected_binding.get("path"), errors)
        loaded.append(report)
    if len(loaded) == 2:
        first, second = loaded
        _check(errors, first.get("run_id") != second.get("run_id"), f"{row} run IDs are not independent")
        _check(errors, first.get("fresh_run_nonce") != second.get("fresh_run_nonce"), f"{row} fresh nonces are not independent")
        _check(errors, first.get("candidate") == second.get("candidate"), f"{row} candidate identities differ")
        _check(errors, first.get("upstream") == second.get("upstream"), f"{row} upstream identities differ")
        _check(errors, first.get("fixture") == second.get("fixture"), f"{row} fixture identities differ")
        _check(errors, first.get("toolchain") == second.get("toolchain"), f"{row} toolchain identities differ")
        hashes = [reports[index].get("sha256") for index in range(2) if isinstance(reports[index], dict)]
        _check(errors, len(hashes) == 2 and hashes[0] != hashes[1], f"{row} full report SHAs are not independent")
    return loaded


def verify(manifest_path: Path = MANIFEST, root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        return {"valid": False, "errors": [str(error)]}
    _check(errors, isinstance(document, dict), "manifest is not an object")
    if not isinstance(document, dict):
        return {"valid": False, "errors": errors}
    _check(errors, set(document) == EXPECTED_MANIFEST_KEYS, "manifest top-level schema drift")
    _check(errors, document.get("schema") == "sipi.pb-01-03-current-scoped-replay-bound.v1", "manifest schema drift")
    _check(errors, document.get("status") == "accepted_current_scoped_replay_open", "manifest status drift")
    _check(errors, document.get("date") == "2026-08-26", "manifest date drift")
    anchors = document.get("anchors")
    expected_anchors = {"algorithm": "json-canonical-sha256-v1", "normalized_sha256": EXPECTED_NORMALIZED_ANCHOR_SHA256, "harness": _expected_harness_anchors()}
    _check(errors, anchors == expected_anchors, "manifest normalized anchor drift")
    _check(
        errors,
        hashlib.sha256(_canonical(_normalized_anchor_payload())).hexdigest() == EXPECTED_NORMALIZED_ANCHOR_SHA256,
        "verifier normalized anchor constant drift",
    )
    expected_harness = _expected_harness_anchors()
    _check(errors, isinstance(anchors, dict) and anchors.get("harness") == expected_harness, "manifest harness anchor drift")
    for harness_name, strip_dynamic in (("verifier", True), ("mutation_tests", False)):
        harness_binding = expected_harness[harness_name]
        harness_path = root / harness_binding["path"]
        _check(
            errors,
            _normalized_source_sha(harness_path, strip_dynamic) == harness_binding["normalized_sha256"],
            f"{harness_name} normalized source anchor drift",
        )
    scope = document.get("scope")
    _check(errors, isinstance(scope, dict), "manifest scope missing")
    if isinstance(scope, dict):
        expected_scope = {
            "candidate_commit": CANDIDATE_COMMIT,
            "candidate_tree": CANDIDATE_TREE,
            "candidate_archive_sha256": CANDIDATE_ARCHIVE,
            "upstream_commit": UPSTREAM_COMMIT,
            "upstream_tree": UPSTREAM_TREE,
            "upstream_archive_sha256": UPSTREAM_ARCHIVE,
            "source_mode": "git_archive_at_immutable_commit",
            "candidate_archive_is_clean_commit_archive": True,
            "upstream_archive_is_pinned_commit_archive": True,
        }
        _check(errors, scope == expected_scope, "manifest source scope drift")
    claims = document.get("claims")
    _check(
        errors,
        claims
        == {
            "nested_output_parity": False,
            "global_row_closed": False,
            "branch_complete": False,
            "release_approval": False,
            "product_capability_admission": False,
            "independent_implementation": False,
            "license_decision": False,
            "whole_payload_parity": False,
            "candidate_clean_archive_replay": True,
            "pinned_upstream_archive_replay": True,
        },
        "manifest claim boundary drift",
    )
    toolchain_gate = document.get("toolchain_gate")
    _check(
        errors,
        toolchain_gate
        == {
            "required_roles_by_row": {
                "PB-01": ["cargo", "rustc", "uv"],
                "PB-02": ["cargo", "rustc", "uv"],
                "PB-03": ["cargo", "rustc", "uv", "python"],
            },
            "pair_identity_exact": True,
            "path_free_identity": True,
            "fresh_nonce_min_hex_chars": 32,
        },
        "manifest toolchain gate drift",
    )
    rows = document.get("rows")
    _check(errors, isinstance(rows, list) and [row.get("id") for row in rows if isinstance(row, dict)] == ["PB-01", "PB-02", "PB-03"], "manifest row set drift")
    loaded: dict[str, list[dict[str, Any]]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                row_id = row.get("id")
                loaded[row_id] = _verify_row(row, root, errors)
    evidence = document.get("evidence")
    _check(errors, isinstance(evidence, dict), "manifest evidence missing")
    if isinstance(evidence, dict):
        _check_keys(evidence, EXPECTED_EVIDENCE_KEYS, "manifest evidence", errors)
        audit_path = evidence.get("audit")
        _check(errors, audit_path == EXPECTED_AUDIT_PATH, "audit path anchor drift")
        _check(errors, _path(audit_path), "audit path is not repository-relative")
        if _path(audit_path):
            audit_file = root / audit_path
            _check(errors, audit_file.is_file(), "audit file is missing")
            _check(errors, evidence.get("audit_sha256") == EXPECTED_AUDIT_SHA256, "audit hard anchor drift")
            _check(errors, _sha(audit_file) == EXPECTED_AUDIT_SHA256, "audit SHA drift")
            try:
                audit_text = audit_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                audit_text = ""
            _check(errors, bool(audit_text) and _path_free(audit_text), "audit contains an absolute host path")
            _check(errors, f"NORMALIZED_ANCHOR_SHA256: {EXPECTED_NORMALIZED_ANCHOR_SHA256}" in audit_text, "audit normalized anchor marker missing")
            _check(errors, f"HARNESS_ANCHOR_ALGORITHM: {HARNESS_NORMALIZATION_ALGORITHM}" in audit_text, "audit harness algorithm marker missing")
            for harness_name in ("verifier", "mutation_tests"):
                harness_binding = expected_harness[harness_name]
                marker = "HARNESS_ANCHOR: " + "|".join((harness_name, harness_binding["path"], harness_binding["normalized_sha256"]))
                _check(errors, marker in audit_text, f"audit harness anchor missing: {harness_name}")
            for row in ("PB-01", "PB-02", "PB-03"):
                for binding in EXPECTED_REPORTS[row]:
                    marker = "REPORT_ANCHOR: " + "|".join(
                        (row, binding["path"], binding["sha256"], binding["run_id"], binding["fresh_run_nonce"])
                    )
                    _check(errors, marker in audit_text, f"audit report anchor missing: {row}/{binding['path']}")
        runner_bindings = evidence.get("replay_runners")
        expected_runner_bindings = [{"path": path, "sha256": digest} for path, digest in REPLAY_RUNNERS.items()]
        _check(errors, runner_bindings == expected_runner_bindings, "replay runner manifest anchors drift")
        _check(errors, isinstance(runner_bindings, list), "replay runner bindings missing")
        if isinstance(runner_bindings, list):
            observed = {}
            for binding in runner_bindings:
                _check(errors, isinstance(binding, dict), "replay runner binding malformed")
                if not isinstance(binding, dict):
                    continue
                _check_keys(binding, {"path", "sha256"}, "replay runner binding", errors)
                path = binding.get("path")
                _check(errors, _path(path) and path in REPLAY_RUNNERS, "unexpected replay runner path")
                if _path(path):
                    observed[path] = binding.get("sha256")
                    _check(errors, _sha(root / path) == binding.get("sha256"), f"replay runner SHA drift: {path}")
            _check(errors, observed == REPLAY_RUNNERS, "replay runner set or digest drift")
        for name in ("verifier", "mutation_tests"):
            binding = evidence.get(name)
            _check(errors, isinstance(binding, dict) and set(binding) == {"path", "sha256"} and _path(binding.get("path")), f"{name} binding malformed")
            if isinstance(binding, dict) and _path(binding.get("path")):
                target = root / binding["path"]
                _check(errors, binding.get("path") == expected_harness[name]["path"], f"{name} path anchor drift")
                _check_hash(binding.get("sha256"), f"{name} binding", errors)
                _check(errors, target.is_file() and _sha(target) == binding.get("sha256"), f"{name} SHA drift")
    _check(errors, _path_free(document), "manifest contains an absolute host path")
    return {
        "valid": not errors,
        "errors": errors,
        "candidate_commit": CANDIDATE_COMMIT,
        "rows": {row: len(value) for row, value in loaded.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = verify(args.manifest.resolve(), args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
