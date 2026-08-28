"""Strict aggregation for the PB-01/PB-02 candidate-matrix replay.

The historical portable-matrix aggregate consumes a different report contract.
This module owns the smallest adapter for the implemented PB-01/PB-02 runner:
it validates the complete report envelope, preserves every scoped blocker, and
emits a deterministic aggregate.  It is evidence tooling only; it does not
change the Rust runtime or admit a new product capability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.pb-01-02-candidate-matrix-replay.v1"
AGGREGATE_SCHEMA = "sipi.pb-01-02-candidate-matrix-aggregate.v1"
MAX_REPORT_BYTES = 512 * 1024 * 1024
MAX_JSON_NODES = 2_000_000
MAX_JSON_DEPTH = 128
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")

PREP_COMMIT = "176956771a0d24255b427c0243d3dabc4e3fdeca"
PREP_TREE = "bf91215d3783ba97c5035ed0eafad687ebb95f3f"
PREP_PARENT = "2dea3bbe6039224704f1e07aebc3ebd6c178abed"
PREP_ARCHIVE_SHA256 = "126923be0c75df882fd0050d000c0f98d81ae447afbc1f9eddbd5ae079b24e34"
PREP_ARCHIVE_BYTES = 55_685_120
PREP_FILES = (
    "tools/run_pb_01_02_candidate_matrix.py",
    "tools/verify_pb_01_02_candidate_matrix_prep.py",
    "tools/test_verify_pb_01_02_candidate_matrix_prep.py",
    "docs/baselines/pb-01-02-candidate-matrix-prep.v1.yaml",
    "docs/baselines/audits/2026-08-29-pb-01-02-candidate-matrix-prep.md",
)
PREP_FILE_RECEIPTS = {
    "tools/run_pb_01_02_candidate_matrix.py": {
        "blob": "281caea1f57ff59961d0b8cd36695a5909a85679",
        "sha256": "3eb706ea5e2de057fa3824d09675d6e63ca5cffdcdc63dd724ee5b0f079ada1d",
        "bytes": 20_077,
    },
    "tools/verify_pb_01_02_candidate_matrix_prep.py": {
        "blob": "9483d0df9a8a6555f55d1e24cb0f98a0939ce056",
        "sha256": "1384ee198387fb7605ee56331bd466203e0bf83ace72cc23ae488140284918f3",
        "bytes": 42_993,
    },
    "tools/test_verify_pb_01_02_candidate_matrix_prep.py": {
        "blob": "42b7e33e333c45d144e98e868670271c8a8043c2",
        "sha256": "bef770a670abb134a85ac65f133cd0cdcc5c9e5240f06235bd3d727b41a30061",
        "bytes": 7_140,
    },
    "docs/baselines/pb-01-02-candidate-matrix-prep.v1.yaml": {
        "blob": "4367c6a3e8b370ad52a49e8ead198a4b3af644c7",
        "sha256": "8e237cca847e31584fb5053eb742b2058d5ea05501b68093e01a23675821adf3",
        "bytes": 14_705,
    },
    "docs/baselines/audits/2026-08-29-pb-01-02-candidate-matrix-prep.md": {
        "blob": "bb508fabda1eea60e24052961a46b2eea020f194",
        "sha256": "44d0965da1bd2c75b7a5aa1be0becbfc8c969e1552ea885bf5de82ad68b33b04",
        "bytes": 3_037,
    },
}

CANDIDATE = {
    "commit": "0d57b36f965588bed3393d2a0a529e4d573a493c",
    "tree": "26f2390c90dd9f44753da27041e12b10b8186d55",
    "archive_sha256": "97cbfeb61d94c7b473314e407286bde2391c6b83e59324d4faaa873ec41f8354",
    "inventory_sha256": "2c24154c7b60d02e1f33755886cd7172bf6cda9637d3cc02c0711629cc94031f",
    "scoped_inventory_sha256": "f309466c512186ac8caafea0b2f8f8a63fb857d3dc86423fb4f9e4bc94b6ab40",
}
UPSTREAM = {
    "commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
    "tree": "5faef6bdb341d444ad65d82a11c0018b15805e24",
    "archive_sha256": "e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25",
    "inventory_sha256": "829d2d5428c12e6aba58f0aae0f2a5bc8427b54fc6310fb4c90049e2797f8855",
    "scoped_inventory_sha256": "f2b48f2d796c0ddf0e7df9c6fbfd3bc031859944b58ace9b0505444cab8e66d5",
}
CORPUS = {
    "path": "docs/baselines/pb-01-02-portable-matrix-inputs.v1.json",
    "bytes": 5_339,
    "sha256": "77d6db2f34de256bea69888122e86281ba578a71da1a1719b790f9b9ed332ddb",
    "archive_present": True,
}
FIXTURES = {
    "PB-01": {
        "path": "crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml",
        "bytes": 1_171,
        "sha256": "d63bb7ab3466ae70406cd2a555ae5a95cda1264021fed8fb1cdca85da961cc48",
        "archive_present": True,
    },
    "PB-02": {
        "path": "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json",
        "bytes": 1_245,
        "sha256": "5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13",
        "archive_present": True,
    },
}

RUN_IDS = (
    "pb-01-02-candidate-run-01",
    "pb-01-02-candidate-run-02",
)
CHALLENGE = {
    "id": "pb-01-02-candidate-matrix-v1",
    "run_count": 2,
    "fresh_archive_replay": True,
    "nonce_required": True,
    "report_sha256_required": True,
}
CASE_IDS = (
    "pb01_duo_binary_analytic_line",
    "pb02_nrz_impulse",
    "pb02_pam4_impulse",
    "pb02_duo_binary_impulse",
    "pb02_impulse_tx_rx_equalization",
    "pb02_impulse_analytic_ctle",
    "pb02_impulse_jitter_bathtub_analysis",
)
CASE_LANES = {CASE_IDS[0]: "PB-01", **{case_id: "PB-02" for case_id in CASE_IDS[1:]}}
CASE_PATCHES = {
    "pb01_duo_binary_analytic_line": {"scalars": {"mod_type": "Duo-binary"}},
    "pb02_nrz_impulse": {},
    "pb02_pam4_impulse": {"modulation": "pam4"},
    "pb02_duo_binary_impulse": {"modulation": "duo_binary"},
    "pb02_impulse_tx_rx_equalization": {
        "rx": {
            "dfe": {
                "agcNAve": 4,
                "alpha": 0.01,
                "bandwidth": 12_000_000_000.0,
                "decisionScaler": 0.4,
                "deltaT": 1e-13,
                "gain": 0.1,
                "ideal": True,
                "lockSustain": 2,
                "nAve": 4,
                "nLockAve": 4,
                "relLockTol": 0.1,
                "tapLimits": [[-0.2, 0.2]],
                "useAgc": True,
            },
            "dfeTaps": 1,
            "ffe": {"cursorPosition": 1, "enabled": True, "weights": [0.0, 1.0, 0.0]},
        },
        "tx": {"ffe": {"cursorPosition": 1, "enabled": True, "weights": [0.05, 0.8, 0.15]}},
    },
    "pb02_impulse_analytic_ctle": {
        "rx": {
            "ctle": {
                "bandwidth": 12_000_000_000.0,
                "frequencyMaxHz": 20_000_000_000.0,
                "frequencyStepHz": 1_000_000_000.0,
                "impulseResponseVPerV": [1.0, 0.25, -0.05],
                "peakFrequency": 5_000_000_000.0,
                "peakMagnitudeDb": 1.7,
            },
            "nativeCtleEnabled": True,
        }
    },
    "pb02_impulse_jitter_bathtub_analysis": {
        "analysis": {"berEyeBits": 16, "includeBathtub": True, "includeJitter": True, "jitterEyeUis": 8}
    },
}
CASE_INPUTS = {
    "pb01_duo_binary_analytic_line": (1_178, "d69f1f2391099de3b1c15846f2ee1400164c48c1ee6abdacd058294c9e3f7a12"),
    "pb02_nrz_impulse": (1_297, "78b86c19952a3d2324d7898c4efa2f4a47ea930cf638496b34a1279fa5e2a007"),
    "pb02_pam4_impulse": (1_298, "60dc637747a0c15c69b34fc4a77871b4e1e9fabfb6eaedbbc5de8e98745f54a0"),
    "pb02_duo_binary_impulse": (1_304, "2213680c7a060062432624b24554e68932496b12eb8e5f5ba038277be9a5f163"),
    "pb02_impulse_tx_rx_equalization": (1_745, "be3720dd6df8cbec1495e75145e25f824f5f233ed48bb38a505d3383eb42da3c"),
    "pb02_impulse_analytic_ctle": (1_559, "dc02aa08cddd65727f4540b56a9fc1e65cf0e09fa07dcc7d135ffdb963da306b"),
    "pb02_impulse_jitter_bathtub_analysis": (1_290, "b1761bb84895c1f3b8805747cae30e3e9b9793fdfc99589c37678a79f0aaa4d7"),
}
CASE_PATCH_SHA256 = {
    "pb01_duo_binary_analytic_line": "2defed125a18ccb89433720ded6d3b9f28646ff1680803b5bbf0d92dba44933a",
    "pb02_nrz_impulse": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    "pb02_pam4_impulse": "dc86fedf497ea07aa717cdb5ba71f49d9b5a7cdfc2553a88401c0054d5aa3fce",
    "pb02_duo_binary_impulse": "4262a9f6b934ae6ca3e50df9303a1674cd146912e4a8f84282c3c516078f22ce",
    "pb02_impulse_tx_rx_equalization": "98c9b6a1a540d5bb9dd43f5b9c74ecf75c90a04ab0695bfacae434805e6a3df6",
    "pb02_impulse_analytic_ctle": "f5eb514c8e4a24f8891f7a822f6fd7f074e4bf1082af61c698e2e3e798ea4e43",
    "pb02_impulse_jitter_bathtub_analysis": "93b8974948e917d29a25b36ea9789db303c7c4804588ca34ae537981aa10c878",
}
EXPECTED_BLOCKERS = {
    "pb01_duo_binary_analytic_line": [],
    "pb02_nrz_impulse": ["complete_metadata_drift"],
    "pb02_pam4_impulse": ["complete_metadata_drift"],
    "pb02_duo_binary_impulse": ["complete_metadata_drift"],
    "pb02_impulse_tx_rx_equalization": [
        "candidate_artifact_invalid", "oracle_artifact_invalid", "strict_native_npz_member_set_drift"
    ],
    "pb02_impulse_analytic_ctle": [
        "complete_array_payload_drift", "complete_metadata_drift", "local_ctle_impulse_extension_not_in_pinned_native_schema"
    ],
    "pb02_impulse_jitter_bathtub_analysis": [
        "candidate_or_oracle_process_failed", "candidate_output_missing", "jitter_span_invalid_for_16_bit_prbs7_fixture", "oracle_output_missing"
    ],
}
PB01_ITEM_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p"
)
PB01_SCHEMA_NAMES = (
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s", "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p", "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H", "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out"
)
PB02_MEMBERS = (
    "channel_impulse_v_per_v.npy", "channel_output_v.npy", "ctle_output_v.npy", "rx_ffe_impulse_v_per_v.npy", "rx_filter_impulse_v_per_v.npy", "rx_input_v.npy", "rx_output_v.npy", "symbols_v.npy", "time_s.npy", "tx_channel_impulse_v_per_v.npy", "tx_waveform_v.npy"
)
TOOLCHAIN = {
    "cargo": ("cargo.exe", "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7", "e11749bef57e0f2056f4a11bb00871623d935559227c35a7b373e983f1eea6bb"),
    "rustc": ("rustc.exe", "86478e53f769379d7f0ebfa7c9aa97cb76ca92233f79aa2cc0dbee2efaac73c7", "d6dec673ca010f6a7d90aa3f4a896ad9d88b66b8fe090296c298eddfe9a406db"),
    "uv": ("uv.exe", "5a7ec85884c2ccb1be560cb8fac3eb890df1adf49bfcc070a270ba70401bdd68", "ab0d29803cb58959acc6cf64650fb215c72c2989b94fb6f9de5f22814ceca82d"),
    "link": ("link.exe", "ca11e6c45debd34bf652dfe984c5360a531a005ed78bf72852330c9c2590cf0d", "f5967e8fed8a0058b2813fa1c42f18645e258cb02d8817bef7760e09d0441412"),
}
HARNESS_SHA256 = {
    "runner": "3eb706ea5e2de057fa3824d09675d6e63ca5cffdcdc63dd724ee5b0f079ada1d",
    "legacy_matrix_primitives": "afde325bca6fd2b6e97b4b0ad34715aae2d8aa1aab1cc28b5cab3723c1fedcb2",
    "native_custody_primitives": "c7839a7d67425fda0df675c35925a87f7e3527996fa3b659e2ee7c036408d863",
}
NON_CLAIMS = [
    "This is an additive candidate replay from the immutable production commit, not the historical preparation gate.",
    "PB-01 compares selected numeric arrays across the dictionary and PyBertData class codec boundary; byte/class compatibility is not claimed.",
    "PB-02 strict comparison includes normalized metadata and logical NPZ member payloads; wrapper metadata is not silently discarded.",
    "The CTLE case is blocked because the local impulseResponseVPerV extension is not in the pinned native fixture schema; the jitter case is blocked because the 16-bit PRBS-7 span cannot satisfy jitterEyeUis=8.",
    "These reports are not a license decision, product capability admission, release approval, or global branch parity claim.",
]
FORMAL_PATHS = (
    "docs/baselines/pb-01-02-candidate-matrix-run-01.v1.json",
    "docs/baselines/pb-01-02-candidate-matrix-run-02.v1.json",
    "docs/baselines/pb-01-02-candidate-matrix-aggregate.v1.json",
    "docs/baselines/pb-01-02-candidate-matrix-formal.v1.yaml",
    "docs/baselines/audits/2026-08-29-pb-01-02-candidate-matrix-formal.md",
)


class AggregateError(RuntimeError):
    """A report or aggregate invariant failed."""


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise AggregateError(f"{label} key set drift")
    return value


def _finite(value: Any) -> None:
    nodes = 0

    def visit(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise AggregateError("JSON structure budget exceeded")
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise AggregateError("non-finite JSON number rejected")
            return
        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                visit(child, depth + 1)
            return
        raise AggregateError("unsupported JSON value type")

    visit(value)


def _pairs(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise AggregateError("duplicate or non-string JSON key")
        result[key] = value
    return result


def _read_regular(path: Path, limit: int = MAX_REPORT_BYTES) -> bytes:
    try:
        info = os.lstat(path)
    except OSError as error:
        raise AggregateError(f"evidence file is unavailable: {path}") from error
    if not stat.S_ISREG(info.st_mode) or os.path.islink(path) or int(info.st_nlink) != 1:
        raise AggregateError("evidence file must be a regular non-link with one link")
    if int(info.st_size) > limit:
        raise AggregateError("evidence file exceeds the bounded read budget")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise AggregateError("evidence file cannot be read") from error
    if len(payload) != int(info.st_size) or len(payload) > limit:
        raise AggregateError("evidence file changed during read")
    return payload


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = _read_regular(path)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(AggregateError(f"non-finite JSON constant: {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AggregateError(f"invalid JSON report: {path}") from error
    _finite(value)
    if type(value) is not dict:
        raise AggregateError("report root must be an object")
    return value, hashlib.sha256(payload).hexdigest()


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or HEX64.fullmatch(value) is None:
        raise AggregateError(f"{label} is not a SHA-256")
    return value


def _safe_relative(value: Any, label: str = "path") -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise AggregateError(f"{label} is not a path token")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root or "\\" in value:
        raise AggregateError(f"{label} is absolute or anchored")
    if any(part in ("", ".", "..") for part in posix.parts):
        raise AggregateError(f"{label} is not canonical relative")
    return posix.as_posix()


def _int(value: Any, label: str, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        raise AggregateError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> float | int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise AggregateError(f"{label} must be a finite number")
    return value


def _fact(value: Any, label: str, *, exclusive: bool = False, nlink_one: bool = False) -> dict[str, Any]:
    keys = {"bytes", "nlink", "nonlink", "path", "post_identity", "pre_identity", "regular", "sha256", "single_handle_read"}
    if exclusive:
        keys |= {"exclusive_create", "pre_absent", "readback_equal"}
    item = _exact(value, keys, label)
    _safe_relative(item["path"], f"{label}.path")
    _sha(item["sha256"], f"{label}.sha256")
    _int(item["bytes"], f"{label}.bytes", 0)
    if item["regular"] is not True or item["nonlink"] is not True or item["single_handle_read"] is not True:
        raise AggregateError(f"{label} custody flags drift")
    if type(item["nlink"]) is not int or item["nlink"] < 1 or (nlink_one and item["nlink"] != 1):
        raise AggregateError(f"{label}.nlink drift")
    for key in ("pre_identity", "post_identity"):
        if type(item[key]) is not list or len(item[key]) != 4 or any(type(part) is not int for part in item[key]):
            raise AggregateError(f"{label}.{key} drift")
    if item["pre_identity"] != item["post_identity"]:
        raise AggregateError(f"{label} changed during read")
    if exclusive and (item["exclusive_create"] is not True or item["pre_absent"] is not True or item["readback_equal"] is not True):
        raise AggregateError(f"{label} exclusive custody flags drift")
    return item


def _process(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"exit_code", "stderr", "stdout"}, label)
    _int(item["exit_code"], f"{label}.exit_code")
    _fact(item["stdout"], f"{label}.stdout", exclusive=True, nlink_one=True)
    _fact(item["stderr"], f"{label}.stderr", exclusive=True, nlink_one=True)
    return item


def _artifact(value: Any, label: str, case_id: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AggregateError(f"{label} artifact is not an object")
    if value.get("present") is True:
        item = _exact(value, {"bytes", "case_id", "kind", "nlink", "nonlink", "path", "post_identity", "pre_absent", "pre_identity", "present", "regular", "role", "sha256", "single_handle_read"}, label)
        if item["case_id"] != case_id or item["role"] not in {"candidate", "oracle"} or item["kind"] not in {"legacy_result", "meta", "arrays"}:
            raise AggregateError(f"{label} artifact identity drift")
        if item["pre_absent"] is not True:
            raise AggregateError(f"{label}.pre_absent drift")
        _fact(
            {key: item[key] for key in ("bytes", "nlink", "nonlink", "path", "post_identity", "pre_identity", "regular", "sha256", "single_handle_read")},
            label,
            nlink_one=True,
        )
        return item
    item = _exact(value, {"case_id", "kind", "path", "present", "role"}, label)
    if item["case_id"] != case_id or item["present"] is not False or item["role"] not in {"candidate", "oracle"} or item["kind"] not in {"legacy_result", "meta", "arrays"}:
        raise AggregateError(f"{label} absent artifact identity drift")
    _safe_relative(item["path"], f"{label}.path")
    return item


def _metadata(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"canonical_sha256", "fields"}, label)
    _sha(item["canonical_sha256"], f"{label}.canonical_sha256")
    if type(item["fields"]) is not dict or "$object" not in item["fields"]:
        raise AggregateError(f"{label}.fields drift")
    for path, field in item["fields"].items():
        if type(path) is not str:
            raise AggregateError(f"{label} field path type drift")
        if type(field) is not dict or "type" not in field or field["type"] not in {"object", "array", "null", "bool", "number", "string"}:
            raise AggregateError(f"{label} field type drift")
        kind = field["type"]
        expected = {"type", "keys"} if kind == "object" else {"type", "length", "sha256"} if kind == "array" else {"type", "value"}
        if set(field) != expected:
            raise AggregateError(f"{label}.{path} key set drift")
        if kind == "object" and (type(field["keys"]) is not list or any(type(key) is not str for key in field["keys"])):
            raise AggregateError(f"{label}.{path} object keys drift")
        if kind == "array":
            _int(field["length"], f"{label}.{path}.length", 0)
            _sha(field["sha256"], f"{label}.{path}.sha256")
        if kind == "null" and field["value"] is not None:
            raise AggregateError(f"{label}.{path} null type drift")
        if kind == "bool" and type(field["value"]) is not bool:
            raise AggregateError(f"{label}.{path} bool type drift")
        if kind == "number":
            _number(field["value"], f"{label}.{path}.value")
        if kind == "string" and type(field["value"]) is not str:
            raise AggregateError(f"{label}.{path} string type drift")
    return item


def _npy(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"count", "dtype", "f64_sha256", "fortran_order", "shape"}, label)
    if item["dtype"] not in {"<f8", ">f8", "|f8"} or type(item["fortran_order"]) is not bool:
        raise AggregateError(f"{label} scalar type drift")
    _sha(item["f64_sha256"], f"{label}.f64_sha256")
    _int(item["count"], f"{label}.count", 0)
    if type(item["shape"]) is not list or any(type(dim) is not int or dim < 0 for dim in item["shape"]):
        raise AggregateError(f"{label}.shape drift")
    expected_count = math.prod(item["shape"]) if item["shape"] else 1
    if item["count"] != expected_count:
        raise AggregateError(f"{label} count/shape cross-field drift")
    return item


def _npz(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"bytes", "logical_members", "logical_sha256", "sha256", "uncompressed_bytes"}, label)
    _int(item["bytes"], f"{label}.bytes", 0)
    _int(item["uncompressed_bytes"], f"{label}.uncompressed_bytes", 0)
    _sha(item["sha256"], f"{label}.sha256")
    _sha(item["logical_sha256"], f"{label}.logical_sha256")
    if type(item["logical_members"]) is not dict or tuple(item["logical_members"]) != PB02_MEMBERS:
        raise AggregateError(f"{label}.logical_members set/order drift")
    for member in PB02_MEMBERS:
        _npy(item["logical_members"][member], f"{label}.{member}")
    return item


def _side(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"arrays", "meta"}, label)
    _npz(item["arrays"], f"{label}.arrays")
    _metadata(item["meta"], f"{label}.meta")
    return item


def _validate_pb01_comparison(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"blockers", "candidate_process", "candidate_schema", "class_pickle_covered_by_matrix", "kind", "oracle_process", "oracle_schema", "rows"}, label)
    if item["kind"] != "pb01_selected_numeric_arrays" or item["blockers"] != [] or item["class_pickle_covered_by_matrix"] is not False:
        raise AggregateError(f"{label} identity/claim drift")
    _process(item["candidate_process"], f"{label}.candidate_process")
    _process(item["oracle_process"], f"{label}.oracle_process")
    if item["candidate_process"]["exit_code"] != 0 or item["oracle_process"]["exit_code"] != 0:
        raise AggregateError(f"{label} process status drift")
    candidate_schema = _exact(item["candidate_schema"], {"array_keys", "item_names", "kind", "schema"}, f"{label}.candidate_schema")
    if candidate_schema != {"array_keys": sorted(PB01_SCHEMA_NAMES), "item_names": list(PB01_SCHEMA_NAMES), "kind": "python_pickle_dict", "schema": "sipi.pybert_data.v1"}:
        raise AggregateError(f"{label}.candidate_schema drift")
    if item["oracle_schema"] != {"kind": "PyBertData_class_pickle"}:
        raise AggregateError(f"{label}.oracle_schema drift")
    if type(item["rows"]) is not list or len(item["rows"]) != len(PB01_ITEM_NAMES):
        raise AggregateError(f"{label}.rows cardinality drift")
    for expected_name, row in zip(PB01_ITEM_NAMES, item["rows"]):
        row = _exact(row, {"length", "max_abs", "name", "passed", "scale", "tolerance"}, f"{label}.{expected_name}")
        if row["name"] != expected_name or row["passed"] is not True:
            raise AggregateError(f"{label}.{expected_name} identity/status drift")
        _int(row["length"], f"{label}.{expected_name}.length", 1)
        for key in ("max_abs", "scale", "tolerance"):
            _number(row[key], f"{label}.{expected_name}.{key}")
        if row["max_abs"] < 0 or row["scale"] < 1 or row["tolerance"] != 1.1e-6 or row["max_abs"] > row["tolerance"]:
            raise AggregateError(f"{label}.{expected_name} numeric gate drift")
    return item


def _validate_pb02_comparison(value: Any, label: str) -> dict[str, Any]:
    item = _exact(value, {"candidate", "candidate_process", "kind", "oracle", "oracle_process"}, label)
    if item["kind"] != "pb02_complete_meta_and_logical_npz":
        raise AggregateError(f"{label}.kind drift")
    _process(item["candidate_process"], f"{label}.candidate_process")
    _process(item["oracle_process"], f"{label}.oracle_process")
    if label.endswith("pb02_impulse_jitter_bathtub_analysis"):
        if item["candidate_process"]["exit_code"] == 0 or item["oracle_process"]["exit_code"] == 0:
            raise AggregateError("jitter comparison must retain process failure")
    elif item["candidate_process"]["exit_code"] != 0 or item["oracle_process"]["exit_code"] != 0:
        raise AggregateError(f"{label} process status drift")
    for side in ("candidate", "oracle"):
        if item[side] is not None:
            _side(item[side], f"{label}.{side}")
    return item


def _validate_input(value: Any, case_id: str) -> dict[str, Any]:
    lane = CASE_LANES[case_id]
    extension = "yaml" if lane == "PB-01" else "json"
    item = _exact(value, {"archive_derived_input", "base_fixture", "custody", "derived_bytes", "derived_sha256", "patch", "patch_sha256", "path"}, f"{case_id}.input")
    expected_fixture = FIXTURES[lane]
    if item["base_fixture"] != expected_fixture or item["patch"] != CASE_PATCHES[case_id] or item["patch_sha256"] != CASE_PATCH_SHA256[case_id]:
        raise AggregateError(f"{case_id}.input provenance drift")
    expected_bytes, expected_sha = CASE_INPUTS[case_id]
    if item["derived_bytes"] != expected_bytes or item["derived_sha256"] != expected_sha or item["archive_derived_input"] is not True or item["path"] != f"{case_id}/input.{extension}":
        raise AggregateError(f"{case_id}.input cross-field drift")
    _safe_relative(item["path"], f"{case_id}.input.path")
    _validate_input_custody(item["custody"], case_id)
    return item


def _validate_input_custody(value: Any, case_id: str) -> dict[str, Any]:
    item = _exact(value, {"case_id", "equal", "post", "pre"}, f"{case_id}.input.custody")
    if item["case_id"] != case_id or item["equal"] is not True:
        raise AggregateError(f"{case_id}.input custody identity drift")
    _fact(item["pre"], f"{case_id}.input.custody.pre", exclusive=True, nlink_one=True)
    _fact(item["post"], f"{case_id}.input.custody.post", nlink_one=True)
    if item["pre"]["sha256"] != item["post"]["sha256"] or item["pre"]["bytes"] != item["post"]["bytes"]:
        raise AggregateError(f"{case_id}.input custody digest drift")
    return item


def _validate_case(value: Any, expected_id: str) -> dict[str, Any]:
    item = _exact(value, {"artifacts", "blockers", "comparison", "id", "input", "lane", "status"}, f"case {expected_id}")
    if item["id"] != expected_id or item["lane"] != CASE_LANES[expected_id] or item["blockers"] != EXPECTED_BLOCKERS[expected_id]:
        raise AggregateError(f"case {expected_id} identity/blocker drift")
    expected_status = "passed" if not EXPECTED_BLOCKERS[expected_id] else "blocked"
    if item["status"] != expected_status:
        raise AggregateError(f"case {expected_id} status drift")
    _validate_input(item["input"], expected_id)
    if item["lane"] == "PB-01":
        _validate_pb01_comparison(item["comparison"], expected_id)
        expected_artifact_count = 2
    else:
        _validate_pb02_comparison(item["comparison"], expected_id)
        expected_artifact_count = 4
    if type(item["artifacts"]) is not list or len(item["artifacts"]) != expected_artifact_count:
        raise AggregateError(f"case {expected_id} artifact cardinality drift")
    for index, artifact in enumerate(item["artifacts"]):
        _artifact(artifact, f"case {expected_id}.artifacts[{index}]", expected_id)
    if item["lane"] == "PB-02" and expected_id != "pb02_impulse_tx_rx_equalization":
        for role in ("candidate", "oracle"):
            side = item["comparison"][role]
            role_artifacts = [artifact for artifact in item["artifacts"] if artifact["role"] == role]
            arrays_artifacts = [artifact for artifact in role_artifacts if artifact["kind"] == "arrays"]
            meta_artifacts = [artifact for artifact in role_artifacts if artifact["kind"] == "meta"]
            if side is None:
                if any(artifact["present"] for artifact in role_artifacts):
                    raise AggregateError(f"case {expected_id}.{role} artifact present without comparison side")
                continue
            if len(arrays_artifacts) != 1 or len(meta_artifacts) != 1 or not arrays_artifacts[0]["present"] or not meta_artifacts[0]["present"]:
                raise AggregateError(f"case {expected_id}.{role} artifact cardinality/presence drift")
            arrays = side["arrays"]
            artifact = arrays_artifacts[0]
            if artifact["sha256"] != arrays["sha256"] or artifact["bytes"] != arrays["bytes"]:
                raise AggregateError(f"case {expected_id}.{role} arrays artifact cross-field drift")
    return item


def _validate_toolchain(value: Any) -> dict[str, Any]:
    item = _exact(value, {"cargo", "link", "rustc", "timeout_seconds", "uv"}, "toolchain")
    if item["timeout_seconds"] != 1200:
        raise AggregateError("toolchain timeout drift")
    for role, expected in TOOLCHAIN.items():
        identity = _exact(item[role], {"executable", "file_custody_equal", "file_custody_post", "file_custody_pre", "file_sha256", "path_redacted", "role", "version_exit", "version_sha256"}, f"toolchain.{role}")
        if identity["role"] != role or identity["executable"] != expected[0] or identity["path_redacted"] is not True or identity["file_sha256"] != expected[1] or identity["version_sha256"] != expected[2] or identity["version_exit"] != 0 or identity["file_custody_equal"] is not True:
            raise AggregateError(f"toolchain.{role} identity drift")
        if "/" in identity["executable"] or "\\" in identity["executable"] or ":" in identity["executable"]:
            raise AggregateError(f"toolchain.{role} path disclosure")
        _fact(identity["file_custody_pre"], f"toolchain.{role}.file_custody_pre")
        _fact(identity["file_custody_post"], f"toolchain.{role}.file_custody_post")
        if identity["file_custody_pre"] != identity["file_custody_post"]:
            raise AggregateError(f"toolchain.{role} file custody drift")
    return item


def _validate_build(value: Any) -> dict[str, Any]:
    item = _exact(value, {"binary_pre", "cargo_binary_source", "env", "process"}, "build")
    _fact(item["binary_pre"], "build.binary_pre", exclusive=True, nlink_one=True)
    _fact(item["cargo_binary_source"], "build.cargo_binary_source")
    if item["binary_pre"]["sha256"] != item["cargo_binary_source"]["sha256"] or item["binary_pre"]["bytes"] != item["cargo_binary_source"]["bytes"]:
        raise AggregateError("build binary source cross-field drift")
    env = _exact(item["env"], {"cargo_cache_lock_bound", "cargo_config_and_flags_cleared", "cargo_home_explicit", "cargo_offline", "cargo_target_external", "path_closed", "rustc_explicit", "rustc_wrappers_cleared"}, "build.env")
    if any(value is not True for value in env.values()):
        raise AggregateError("build environment custody drift")
    _process(item["process"], "build.process")
    if item["process"]["exit_code"] != 0:
        raise AggregateError("candidate build did not pass")
    return item


def _validate_oracle(value: Any) -> dict[str, Any]:
    item = _exact(value, {"clean_archive_or_venv_only", "host_pythonpath_absent", "host_uv_flags_cleared", "host_virtual_env_absent", "modules", "oracle_work_archive_sha256", "oracle_work_started_clean", "process", "uv_cache_explicit_lock_bound", "uv_link_mode_copy", "uv_offline_frozen_no_config"}, "oracle_runtime")
    for key in ("clean_archive_or_venv_only", "host_pythonpath_absent", "host_uv_flags_cleared", "host_virtual_env_absent", "oracle_work_started_clean", "uv_cache_explicit_lock_bound", "uv_link_mode_copy", "uv_offline_frozen_no_config"):
        if item[key] is not True:
            raise AggregateError(f"oracle_runtime.{key} drift")
    if item["oracle_work_archive_sha256"] != UPSTREAM["archive_sha256"]:
        raise AggregateError("oracle runtime archive drift")
    _process(item["process"], "oracle_runtime.process")
    if item["process"]["exit_code"] != 0:
        raise AggregateError("oracle probe did not pass")
    modules = _exact(item["modules"], {"numpy", "pybert", "scipy"}, "oracle_runtime.modules")
    for name in ("numpy", "pybert", "scipy"):
        module = _exact(modules[name], {"file", "owner", "relative_path", "version"}, f"oracle_runtime.modules.{name}")
        if module["owner"] != "venv" or type(module["version"]) is not str:
            raise AggregateError(f"oracle module {name} identity drift")
        _safe_relative(module["relative_path"], f"oracle_runtime.modules.{name}.relative_path")
        _fact(module["file"], f"oracle_runtime.modules.{name}.file", nlink_one=True)
    return item


def _validate_custody(value: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    item = _exact(value, {"archive_materialization", "artifacts", "inputs", "materialized_archives_created_new", "output", "run_root_created_new", "run_root_path_redacted", "work_root_empty_before_run", "work_root_outside_candidate_repo", "work_root_outside_upstream_repo", "work_root_path_redacted"}, "custody")
    for key in ("materialized_archives_created_new", "run_root_created_new", "run_root_path_redacted", "work_root_empty_before_run", "work_root_outside_candidate_repo", "work_root_outside_upstream_repo", "work_root_path_redacted"):
        if item[key] is not True:
            raise AggregateError(f"custody.{key} drift")
    output = _exact(item["output"], {"exclusive_report", "fresh_root"}, "custody.output")
    if output != {"exclusive_report": True, "fresh_root": True}:
        raise AggregateError("custody.output drift")
    archives = item["archive_materialization"]
    if type(archives) is not list or len(archives) != 3:
        raise AggregateError("custody archive cardinality drift")
    expected_roles = ("candidate", "upstream_pristine", "upstream_oracle")
    for archive, role in zip(archives, expected_roles):
        archive = _exact(archive, {"archive_sha256", "fact", "role"}, f"custody.archive.{role}")
        if archive["role"] != role or archive["archive_sha256"] != (CANDIDATE if role == "candidate" else UPSTREAM)["archive_sha256"]:
            raise AggregateError(f"custody.archive.{role} identity drift")
        _fact(archive["fact"], f"custody.archive.{role}.fact", nlink_one=True)
    if type(item["inputs"]) is not list or len(item["inputs"]) != len(cases):
        raise AggregateError("custody input cardinality drift")
    for input_item, case in zip(item["inputs"], cases):
        if input_item != case["input"]["custody"]:
            raise AggregateError(f"custody input cross-field drift: {case['id']}")
    flattened = [artifact for case in cases for artifact in case["artifacts"]]
    if item["artifacts"] != flattened:
        raise AggregateError("custody artifact cross-field drift")
    for index, artifact in enumerate(item["artifacts"]):
        _artifact(artifact, f"custody.artifacts[{index}]", artifact["case_id"])
    return item


def _validate_report(value: Any, expected_run_id: str) -> dict[str, Any]:
    report = _exact(value, {"build", "candidate", "cases", "challenge", "claims", "codec_boundary", "corpus", "custody", "fixtures", "fresh_run_nonce", "harness", "non_claims", "oracle_runtime", "run_id", "schema", "source_mode", "status", "toolchain", "upstream", "version"}, "report")
    if report["schema"] != SCHEMA or report["version"] != 1 or report["run_id"] != expected_run_id or report["source_mode"] != "git_archive_at_immutable_commit":
        raise AggregateError("report header drift")
    if report["status"] not in {"scoped_matrix_blocked", "passed_scoped"} or type(report["fresh_run_nonce"]) is not str or HEX64.fullmatch(report["fresh_run_nonce"]) is None:
        raise AggregateError("report run identity/status drift")
    index = RUN_IDS.index(expected_run_id) + 1
    if report["challenge"] != {**CHALLENGE, "run_index": index}:
        raise AggregateError("report challenge drift")
    if report["candidate"] != CANDIDATE or report["upstream"] != UPSTREAM or report["corpus"] != CORPUS or report["fixtures"] != FIXTURES:
        raise AggregateError("report source/provenance identity drift")
    _validate_toolchain(report["toolchain"])
    _validate_build(report["build"])
    _validate_oracle(report["oracle_runtime"])
    codec = _exact(report["codec_boundary"], {"candidate", "class_codec_byte_parity", "comparison", "oracle"}, "codec_boundary")
    if codec != {"candidate": "python_pickle_dict_sipi.pybert_data.v1", "class_codec_byte_parity": False, "comparison": "selected_numeric_arrays_only", "oracle": "PyBertData_class_pickle"}:
        raise AggregateError("codec boundary drift")
    harness = _exact(report["harness"], {"immutable_harness_commit", "legacy_matrix_primitives", "native_custody_primitives", "runner", "source_mode"}, "harness")
    if harness["immutable_harness_commit"] is not None or harness["source_mode"] != "working_tree_content_hash_at_replay":
        raise AggregateError("harness state drift")
    for key in ("runner", "legacy_matrix_primitives", "native_custody_primitives"):
        ref = _exact(harness[key], {"path", "sha256"}, f"harness.{key}")
        _safe_relative(ref["path"], f"harness.{key}.path")
        _sha(ref["sha256"], f"harness.{key}.sha256")
        if ref["sha256"] != HARNESS_SHA256[key]:
            raise AggregateError(f"harness.{key} content receipt drift")
    if harness["runner"]["path"] != "tools/run_pb_01_02_candidate_matrix.py" or harness["legacy_matrix_primitives"]["path"] != "tools/run_pb_01_02_portable_matrix.py" or harness["native_custody_primitives"]["path"] != "tools/run_pb_02_direct_replay.py":
        raise AggregateError("harness path drift")
    if report["non_claims"] != NON_CLAIMS:
        raise AggregateError("report non-claim boundary drift")
    cases = report["cases"]
    if type(cases) is not list or len(cases) != len(CASE_IDS):
        raise AggregateError("report case cardinality drift")
    cases = [_validate_case(case, expected_id) for case, expected_id in zip(cases, CASE_IDS)]
    expected_claims = {
        "global_branch_parity": False,
        "pb01_duo_selected_array_parity": cases[0]["status"] == "passed",
        "pb02_nrz_pam4_duo_eq_logical_npz_parity": all(case["status"] == "passed" for case in cases[1:5]),
        "product_capability_admission": False,
        "release_acceptance": False,
        "whole_payload_parity": False,
    }
    claims = _exact(report["claims"], set(expected_claims), "report.claims")
    if claims != expected_claims:
        raise AggregateError("report claims cross-field drift")
    _validate_custody(report["custody"], cases)
    expected_status = "passed_scoped" if all(case["status"] == "passed" for case in cases) else "scoped_matrix_blocked"
    if report["status"] != expected_status:
        raise AggregateError("report status/case cross-field drift")
    return report


def load_report(path: Path, expected_run_id: str) -> tuple[dict[str, Any], str]:
    if expected_run_id not in RUN_IDS:
        raise AggregateError("unknown fixed run id")
    report, digest = _load_json(path)
    return _validate_report(report, expected_run_id), digest


def _stable_report_id(path: Path, repository_root: Path | None = None) -> str:
    resolved = path.resolve()
    base = (repository_root or ROOT).resolve()
    try:
        return resolved.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _without_runtime_facts(value: Any) -> Any:
    if type(value) is dict:
        return {key: _without_runtime_facts(item) for key, item in value.items() if key not in {"candidate_process", "oracle_process", "custody", "pre_identity", "post_identity", "file_custody_pre", "file_custody_post"}}
    if type(value) is list:
        return [_without_runtime_facts(item) for item in value]
    return value


def _case_projection(case: dict[str, Any]) -> Any:
    # Artifact digests can legitimately vary across fresh runs (for example,
    # a pickle may contain runtime-owned metadata).  The report-level artifact
    # custody still validates every digest; the cross-run projection compares
    # only stable artifact identity and size/availability.
    return _without_runtime_facts({key: value for key, value in case.items() if key != "artifacts"}) | {
        "artifact_payloads": sorted(
            (item.get("role"), item.get("kind"), item.get("present"), item.get("path"), item.get("bytes"))
            for item in case["artifacts"]
        )
    }


def _logical_arrays_equal(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Compare decompressed typed payloads, not incidental ZIP container bytes."""

    return first["arrays"]["logical_members"] == second["arrays"]["logical_members"] and first["arrays"]["logical_sha256"] == second["arrays"]["logical_sha256"]


def _challenge_projection(challenge: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in challenge.items() if key != "run_index"}


def _prep_binding() -> dict[str, Any]:
    return {
        "commit": PREP_COMMIT,
        "tree": PREP_TREE,
        "parent": PREP_PARENT,
        "archive_sha256": PREP_ARCHIVE_SHA256,
        "archive_bytes": PREP_ARCHIVE_BYTES,
        "files": {path: dict(PREP_FILE_RECEIPTS[path]) for path in PREP_FILES},
    }


def aggregate_documents(
    first: dict[str, Any],
    first_hash: str,
    second: dict[str, Any],
    second_hash: str,
    first_path: Path,
    second_path: Path,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    if first_path.resolve() == second_path.resolve() or first_hash == second_hash:
        raise AggregateError("two reports must have distinct paths and full digests")
    if first["fresh_run_nonce"] == second["fresh_run_nonce"]:
        raise AggregateError("two reports must have distinct fresh nonces")
    common_keys = ("candidate", "upstream", "corpus", "fixtures", "toolchain", "harness", "codec_boundary", "source_mode")
    blockers: list[str] = []
    for key in common_keys:
        if first[key] != second[key]:
            blockers.append(f"cross_run_{key}_drift")
    cases: list[dict[str, Any]] = []
    for first_case, second_case in zip(first["cases"], second["cases"]):
        if first_case["id"] != second_case["id"] or first_case["lane"] != second_case["lane"]:
            raise AggregateError("case order/id drift between reports")
        if _case_projection(first_case) != _case_projection(second_case):
            blockers.append(f"{first_case['id']}:cross_run_case_payload_drift")
        case_blockers = sorted(set(first_case["blockers"]) | set(second_case["blockers"]))
        if first_case["status"] != "passed" or second_case["status"] != "passed":
            blockers.extend(f"{first_case['id']}:{blocker}" for blocker in case_blockers)
        selected = False
        typed = False
        if first_case["lane"] == "PB-01":
            selected = first_case["status"] == second_case["status"] == "passed"
        else:
            first_side = first_case["comparison"]["candidate"]
            second_side = second_case["comparison"]["candidate"]
            first_oracle = first_case["comparison"]["oracle"]
            second_oracle = second_case["comparison"]["oracle"]
            selected = first_side is not None and second_side is not None and first_oracle is not None and second_oracle is not None and _logical_arrays_equal(first_side, first_oracle) and _logical_arrays_equal(second_side, second_oracle)
            typed = selected and first_side["meta"] == first_oracle["meta"] and second_side["meta"] == second_oracle["meta"]
        complete = first_case["status"] == second_case["status"] == "passed" and typed and first_case["lane"] == "PB-02"
        cases.append({
            "id": first_case["id"],
            "lane": first_case["lane"],
            "first_status": first_case["status"],
            "second_status": second_case["status"],
            "status": "passed" if complete or (first_case["lane"] == "PB-01" and selected) else "blocked",
            "blockers": case_blockers,
            "selected_array_parity": selected,
            "complete_typed_output_parity": complete,
        })
    claims = {
        "pb01_duo_selected_array_parity": cases[0]["selected_array_parity"],
        "pb02_complete_typed_output_parity": all(case["complete_typed_output_parity"] for case in cases[1:]),
        "global_branch_parity": False,
        "whole_payload_parity": False,
        "release_acceptance": False,
        "product_capability_admission": False,
    }
    return {
        "schema": AGGREGATE_SCHEMA,
        "version": 1,
        "status": "passed_scoped" if not blockers else "blocked",
        "prep": _prep_binding(),
        "candidate": first["candidate"],
        "upstream": first["upstream"],
        "corpus": first["corpus"],
        "fixtures": first["fixtures"],
        "reports": [
            {"path": _stable_report_id(first_path, repository_root), "sha256": first_hash, "run_id": first["run_id"], "fresh_run_nonce": first["fresh_run_nonce"], "challenge": first["challenge"]},
            {"path": _stable_report_id(second_path, repository_root), "sha256": second_hash, "run_id": second["run_id"], "fresh_run_nonce": second["fresh_run_nonce"], "challenge": second["challenge"]},
        ],
        "toolchain": first["toolchain"],
        "cases": cases,
        "cross_run": {
            "candidate_equal": first["candidate"] == second["candidate"],
            "upstream_equal": first["upstream"] == second["upstream"],
            "corpus_equal": first["corpus"] == second["corpus"],
            "fixtures_equal": first["fixtures"] == second["fixtures"],
            "toolchain_equal": first["toolchain"] == second["toolchain"],
            "harness_equal": first["harness"] == second["harness"],
            "challenge_equal": _challenge_projection(first["challenge"]) == _challenge_projection(second["challenge"]),
            "run_ids_distinct": first["run_id"] != second["run_id"],
            "nonces_distinct": first["fresh_run_nonce"] != second["fresh_run_nonce"],
            "report_sha256_distinct": first_hash != second_hash,
            "case_projection_equal": all(_case_projection(a) == _case_projection(b) for a, b in zip(first["cases"], second["cases"])),
        },
        "claims": claims,
        "blockers": sorted(set(blockers)),
        "non_claims": [
            "This aggregate is a separate Stage-2 adapter for the candidate-matrix report contract.",
            "PB-01 selected-array parity does not claim full PyBertData class-pickle or whole-branch parity.",
            "PB-02 metadata, artifact, CTLE schema, and jitter-span blockers are preserved; no blocked case is promoted.",
            "This aggregate is not a license decision, product capability admission, release approval, or global parity claim.",
        ],
    }


def aggregate(first_path: Path, second_path: Path, output: Path | None = None) -> dict[str, Any]:
    first, first_hash = load_report(first_path, RUN_IDS[0])
    second, second_hash = load_report(second_path, RUN_IDS[1])
    document = aggregate_documents(first, first_hash, second, second_hash, first_path, second_path)
    if output is not None:
        payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        if len(payload) > MAX_REPORT_BYTES:
            raise AggregateError("aggregate exceeds the bounded report budget")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-report", type=Path, required=True)
    parser.add_argument("--second-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = aggregate(args.first_report, args.second_report, args.output)
    except (AggregateError, OSError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps({"status": document["status"], "output": str(args.output)}, ensure_ascii=False, sort_keys=True))
    return 0 if document["status"] == "passed_scoped" else 1


if __name__ == "__main__":
    raise SystemExit(main())
