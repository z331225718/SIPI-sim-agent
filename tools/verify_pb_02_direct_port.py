"""Verify the PB-02 PyBERT native direct-port evidence and lane boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "pb-02-direct-port.v1.yaml"
DEFAULT_UPSTREAM = Path(r"C:\Users\z3312\code\Py-bert-agent")
EXPECTED_SCHEMA = "sipi.pb-02-direct-port.v1"
EXPECTED_STATUS = "direct_port_native_core_candidate_replay_unbound_open"
EXPECTED_COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
EXPECTED_TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
EXPECTED_AUDIT = "docs/baselines/audits/2026-08-22-pb-02-direct-port.md"
EXPECTED_AUDIT_SHA256 = "5f9f2308762efb1f1cc32f091a93f29a6e06db780300ea58d2debb915478d49d"
CRATE = ROOT / "crates" / "sipi-pybert-direct"
# v1 is an immutable historical observation.  Its root and runner blobs came
# from the predecessor lane commits; current PB-02 additions are attested by
# the additive v2 verifier instead of rebinding this record.
HISTORICAL_ROOT_COMMIT = "81d19e7fab6621f57890cf6ac6a72bd64fc56b9a"
HISTORICAL_RUNNER_COMMIT = "81d19e7fab6621f57890cf6ac6a72bd64fc56b9a"

# These values are deliberately repeated outside the YAML so a mutated
# manifest cannot redefine the source identity it is supposed to prove.
EXPECTED_SOURCE_FILES: dict[str, tuple[str, str, str]] = {
    "native/pybert-core/src/analysis.rs": (
        "crates/sipi-pybert-direct/src/analysis.rs",
        "0f2a5abc9d627a350501effcddf4ac22104e8f1f",
        "a1e2f15ca445bab1ac5cc95262b929ebf8caa90bf02d9f3e780d367db6aa066a",
    ),
    "native/pybert-core/src/bathtub.rs": (
        "crates/sipi-pybert-direct/src/bathtub.rs",
        "7b79b052f4571657756ede7df928c3db1ebaf809",
        "919f6d21c1fbc30a20258aa9d41319e3dde0ce7d013c392e4cba79d56d66f6b5",
    ),
    "native/pybert-core/src/capabilities.rs": (
        "crates/sipi-pybert-direct/src/capabilities.rs",
        "6091c051643c6c51f8f954314c2745929e113f92",
        "b09364910dfadf8c13efe5818c1b17cc9853b4055f29a7ac1c388cb28121f0b6",
    ),
    "native/pybert-core/src/channel.rs": (
        "crates/sipi-pybert-direct/src/channel.rs",
        "44665b5afa3956a55611b1b5e862a99e251de17d",
        "91961d25a6d4d604c78e6eedd42c5dbed0eba3e6bee85f624f901168ffa327ca",
    ),
    "native/pybert-core/src/decoder.rs": (
        "crates/sipi-pybert-direct/src/decoder.rs",
        "7566dbcb34588a386ca53b2edbd113c1a384573a",
        "81da93d719ca69542046a9ffef071d3876aad62830dfbb161ad76fb0121567f0",
    ),
    "native/pybert-core/src/equalization.rs": (
        "crates/sipi-pybert-direct/src/equalization.rs",
        "ae91583c5675a82fe229918c41602b8531fb775d",
        "fa286b527fc023f70edeb60777006ef431252527890098f63672b054fc11b295",
    ),
    "native/pybert-core/src/error.rs": (
        "crates/sipi-pybert-direct/src/error.rs",
        "dc981e70baf221b7a2f474e7fe27cc371d2d8da2",
        "64a082b795379ee3e0265c5c9e103bbaa3f17421a05f2cc7c6fd6ee78cd8b891",
    ),
    "native/pybert-core/src/event.rs": (
        "crates/sipi-pybert-direct/src/event.rs",
        "525cf44fb2b50ffc79f1b9efa1fadd138369ca41",
        "b95d3b26a96529e9723681c6b123f702ec2decef49e429f59f554bbee8dd60f5",
    ),
    "native/pybert-core/src/input.rs": (
        "crates/sipi-pybert-direct/src/input.rs",
        "ae6d1883b65640d1719022df2c9e8b0763636dc0",
        "3de56d604e0eac89cea31ae0c99bb8a7607f15a99c6cfef4cd818386a2003134",
    ),
    "native/pybert-core/src/jitter.rs": (
        "crates/sipi-pybert-direct/src/jitter.rs",
        "92e0fd6e6b2d40590b967f5f5d057a3de2969672",
        "0f1fcc46d026b43edf13da64262833d2ac004a06369e584f5094f801296288c8",
    ),
    "native/pybert-core/src/output.rs": (
        "crates/sipi-pybert-direct/src/output.rs",
        "54cfa6b4d51c6ef923885d29a9004dd5265b26d2",
        "74a54504c38424532f19fa0f6a9b22942b07694ef771d4d3ab37dda1e7b3b1ac",
    ),
    "native/pybert-core/src/pattern.rs": (
        "crates/sipi-pybert-direct/src/pattern.rs",
        "b8d31f2a1039ac80d5697411c86889efa9dbf5b3",
        "1c414cb04a54b9c46d09651d6909baaee925670d6a431a264ce9d45eced99274",
    ),
    "native/pybert-core/src/pipeline.rs": (
        "crates/sipi-pybert-direct/src/pipeline.rs",
        "51f3277ab45dbe73679087dbcc04a652a735f6f6",
        "10cd44ebb38ae35d7eec5324eabe9c3b9b1b33353c1315069ae1fcb85f82695f",
    ),
    "native/pybert-core/src/receiver.rs": (
        "crates/sipi-pybert-direct/src/receiver.rs",
        "50c315f82892fdf233fe55aef7b3a96a177d9dde",
        "1794615295afc3e9aebdcb76dc140106f12a93c6ce781bc0828c450392e4ec43",
    ),
    "native/pybert-core/src/response.rs": (
        "crates/sipi-pybert-direct/src/response.rs",
        "8833f7a3f74a1450124539192e1090ac071d52b9",
        "9812483ad36a306103a0ea7830c49c4e1a0a71aae383d2a05fcbbc7f711902bd",
    ),
    "native/pybert-core/src/signal.rs": (
        "crates/sipi-pybert-direct/src/signal.rs",
        "e67f7985fe8e353ebbd2e215bc2dd17020521378",
        "d9ddaa2941dff69722c78823e55d223222aff25f8b38c493c956771d567b6557",
    ),
    "native/pybert-core/src/simulation.rs": (
        "crates/sipi-pybert-direct/src/simulation.rs",
        "1f19bff64315e0042bab89d67e9131c289f5e583",
        "99425e94e6336dd39330ce6c1db4bbd0c43699ed7abc9e8a1fe8f56acde239fd",
    ),
    "native/pybert-core/src/statistical_eye.rs": (
        "crates/sipi-pybert-direct/src/statistical_eye.rs",
        "e2f9dea5d8734903514720d93b1a0ce2079a61ee",
        "d7b98d3fb6efee9f5589877140882bd8f7843edf63d6534fc69ad86eef73fc3e",
    ),
    "native/pybert-core/src/units.rs": (
        "crates/sipi-pybert-direct/src/units.rs",
        "57ad85737a7231f5c6ae77312cc77b1446aae3d4",
        "df775c9a0157cd9e52391cf6a6623db3bb316108d0dbe525ad7a053375d1cd03",
    ),
}

EXPECTED_ADAPTED_SOURCE = {
    "path": "native/pybert-core/src/lib.rs",
    "target": "crates/sipi-pybert-direct/src/lib.rs",
    "blob_sha1": "a8cdc5b34e282c5b1e663f1c1b0a85bf03606b51",
    "source_sha256": "94db66853fa4117e90db395a75dc41e1a103e652cfef5831d773193b66d3b457",
    "target_sha256": "e092cd09f2b792add6a1a19ae47caa990dd86c5b37b16ed0925a9655d1d45aec",
    "delta": "additive_runner_module_and_reexports_only",
}

EXPECTED_EXTERNAL: dict[str, tuple[str, str, str, str]] = {
    "core_manifest": (
        "native/pybert-core/Cargo.toml",
        "0af08f1305c37718ab27f77cbf400adc1093d48e",
        "3c4065fbab3426421c43af0d2f04bbd09fe36c18d2544321d21d3cc2c4bb952c",
        "MIT",
    ),
    "python_extension_boundary": (
        "native/pybert-python/src/lib.rs",
        "89aa11197349da28f7a8d1427113d5ff3ff65f9b",
        "d6cdd06c3fb6a86efe8af0616fc6ef9e1e896fcac9262a339e5cf30877f6ed13",
        "MIT",
    ),
    "python_cli": (
        "src/pybert/cli.py",
        "4c1116007d31bcebf8db3252363eed7774c7b349",
        "3826b0c156166e6f04b0e9997ce64a53a53867db6d89143b7c582ca2cf4337c9",
        "BSD-3-Clause",
    ),
    "python_backend": (
        "src/pybert/engine/rust_backend.py",
        "1010aba98627f6777146f870f95d278d0b7e3b00",
        "a63eeae3066d4cb1cbb05dd9edca05f90bda389d3f145b3be9464cac95ef3ce2",
        "BSD-3-Clause",
    ),
    "license_file": (
        "LICENSE",
        "64d198ba43675ede5fbdef1ec918a63954951640",
        "4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1",
        "BSD-3-Clause",
    ),
}

EXPECTED_ARRAY_HASHES = {
    "channel_impulse_v_per_v": "82d5182c90ecefa00f9e9d91f02ad8be6d9d082f377bd1f96c00f010bc053e36",
    "channel_output_v": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    "ctle_output_v": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    "rx_ffe_impulse_v_per_v": "8034367eec76495180b08e634d0bf4236b83a30d9ce7be3fd843fe8860f4de41",
    "rx_filter_impulse_v_per_v": "6c3c396ed6b5c36dcae172271f462051b1266b851e92df3deea8ac65478fd712",
    "rx_input_v": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    "rx_output_v": "bbe26fb833fd898ba1033701957b0cace8d7387a22d0518f9404630406013309",
    "symbols_v": "6884fb21aa1699022a9207c5cfeecc8d67d10e93d698ad6e7e2ee75e5c47c365",
    "time_s": "58bbee68c5a97e80d59296425c4726ebeabe38d848dc055134fb4a65f6d2b6b2",
    "tx_channel_impulse_v_per_v": "82d5182c90ecefa00f9e9d91f02ad8be6d9d082f377bd1f96c00f010bc053e36",
    "tx_waveform_v": "40b756e3bbe3ed90ade86b60c2f4d51764cd4033b577629835076308de2c1a35",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str, raw: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
    )
    return result.stdout if raw else result.stdout.decode("ascii").strip()


def _historical_target(path: Path, commit: str) -> bytes:
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    return bytes(_git(ROOT, "show", f"{commit}:{relative}", raw=True))


def _check(blockers: list[str], condition: bool, message: str) -> None:
    if not condition:
        blockers.append(message)


def _mapping(document: dict[str, Any], blockers: list[str]) -> dict[str, dict[str, Any]]:
    direct = document.get("direct_port_files")
    _check(blockers, isinstance(direct, dict), "direct-port source record missing")
    if not isinstance(direct, dict):
        return {}
    _check(
        blockers,
        direct.get("license_boundary") == "native_core_manifest_declares_MIT",
        "direct-port license boundary drift",
    )
    _check(
        blockers,
        direct.get("source_bytes_copied_from_exact_git_objects") is True,
        "exact source-copy attestation drift",
    )
    files = direct.get("files")
    _check(blockers, isinstance(files, dict), "direct-port source map missing")
    if not isinstance(files, dict):
        return {}
    _check(blockers, set(files) == set(EXPECTED_SOURCE_FILES), "direct-port source path set drift")
    for source_path, expected in EXPECTED_SOURCE_FILES.items():
        item = files.get(source_path)
        _check(blockers, isinstance(item, dict), f"source binding missing: {source_path}")
        if isinstance(item, dict):
            target, blob, digest = expected
            _check(blockers, item.get("target") == target, f"target binding drift: {source_path}")
            _check(blockers, item.get("blob_sha1") == blob, f"Git blob binding drift: {source_path}")
            _check(blockers, item.get("sha256") == digest, f"source hash binding drift: {source_path}")
    adapted = direct.get("adapted_files")
    _check(blockers, isinstance(adapted, dict), "adapted source map missing")
    adapted_item = adapted.get(EXPECTED_ADAPTED_SOURCE["path"]) if isinstance(adapted, dict) else None
    _check(blockers, isinstance(adapted_item, dict), "adapted crate root binding missing")
    if isinstance(adapted_item, dict):
        for key in ("target", "blob_sha1", "source_sha256", "target_sha256", "delta"):
            _check(
                blockers,
                adapted_item.get(key) == EXPECTED_ADAPTED_SOURCE[key],
                f"adapted crate root binding drift: {key}",
            )
        target = ROOT / EXPECTED_ADAPTED_SOURCE["target"]
        _check(
            blockers,
            _sha256(_historical_target(target, HISTORICAL_ROOT_COMMIT)) == EXPECTED_ADAPTED_SOURCE["target_sha256"],
            "adapted crate root target hash drift",
        )
    return files


def _verify_external_source(source: Path, blockers: list[str]) -> bool:
    checked = False
    try:
        commit = str(_git(source, "rev-parse", "HEAD"))
        tree = str(_git(source, "rev-parse", f"{commit}^{{tree}}"))
        _check(blockers, commit == EXPECTED_COMMIT, "upstream checkout commit drift")
        _check(blockers, tree == EXPECTED_TREE, "upstream checkout tree drift")
        for path, (_target, expected_blob, expected_sha) in EXPECTED_SOURCE_FILES.items():
            blob = str(_git(source, "rev-parse", f"{commit}:{path}"))
            payload = bytes(_git(source, "cat-file", "blob", f"{commit}:{path}", raw=True))
            target = CRATE / _target.removeprefix("crates/sipi-pybert-direct/")
            target_payload = _historical_target(target, HISTORICAL_ROOT_COMMIT)
            _check(blockers, blob == expected_blob, f"upstream Git blob drift: {path}")
            _check(blockers, _sha256(payload) == expected_sha, f"upstream source hash drift: {path}")
            _check(blockers, target_payload == payload, f"copied bytes drift: {path}")
        adapted_path = EXPECTED_ADAPTED_SOURCE["path"]
        adapted_blob = str(_git(source, "rev-parse", f"{commit}:{adapted_path}"))
        adapted_payload = bytes(_git(source, "cat-file", "blob", f"{commit}:{adapted_path}", raw=True))
        adapted_target = ROOT / EXPECTED_ADAPTED_SOURCE["target"]
        _check(blockers, adapted_blob == EXPECTED_ADAPTED_SOURCE["blob_sha1"], "adapted crate root Git blob drift")
        _check(blockers, _sha256(adapted_payload) == EXPECTED_ADAPTED_SOURCE["source_sha256"], "adapted crate root source hash drift")
        target_payload = _historical_target(adapted_target, HISTORICAL_ROOT_COMMIT)
        runner_exports = (
            b"pub use runner::{\n"
            b"    DirectRunError, DirectRunReport, run_sim_native_file, run_sim_native_json,\n"
            b"    strict_simulation_input_json,\n"
            b"};\n"
        )
        reconstructed = target_payload.replace(b"mod runner;\n", b"", 1).replace(runner_exports, b"", 1)
        _check(blockers, reconstructed == adapted_payload, "adapted crate root delta drift")
        for name, (path, expected_blob, expected_sha, _license) in EXPECTED_EXTERNAL.items():
            blob = str(_git(source, "rev-parse", f"{commit}:{path}"))
            payload = bytes(_git(source, "cat-file", "blob", f"{commit}:{path}", raw=True))
            _check(blockers, blob == expected_blob, f"external Git blob drift: {name}")
            _check(blockers, _sha256(payload) == expected_sha, f"external source hash drift: {name}")
        checked = True
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        blockers.append(f"upstream Git object check failed: {error}")
    return checked


def verify(
    document: dict[str, Any],
    *,
    source: Path | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    blockers: list[str] = []
    _check(blockers, isinstance(document, dict), "evidence must be a mapping")
    if not isinstance(document, dict):
        return {"valid": False, "status": None, "blockers": blockers, "source_git_objects_checked": False}

    _check(blockers, document.get("schema") == EXPECTED_SCHEMA, "schema drift")
    _check(blockers, document.get("status") == EXPECTED_STATUS, "status drift or overclaim")
    scope = document.get("scope")
    _check(blockers, isinstance(scope, dict), "scope missing")
    if isinstance(scope, dict):
        expected_scope = {
            "workflow": "PB-02",
            "command": "sim-native",
            "lane_crate": "crates/sipi-pybert-direct",
            "product_workspace_modified": False,
            "adapter_semantics_modified": False,
            "new_domain_feature": False,
        }
        for key, expected in expected_scope.items():
            _check(blockers, scope.get(key) == expected, f"scope drift: {key}")

    source_record = document.get("source")
    _check(blockers, isinstance(source_record, dict), "source record missing")
    if isinstance(source_record, dict):
        _check(blockers, source_record.get("repository") == "pybert", "source repository drift")
        _check(blockers, source_record.get("commit") == EXPECTED_COMMIT, "source commit drift")
        _check(blockers, source_record.get("tree") == EXPECTED_TREE, "source tree drift")
        for name, (path, blob, digest, license_name) in EXPECTED_EXTERNAL.items():
            item = source_record.get(name)
            _check(blockers, isinstance(item, dict), f"external source record missing: {name}")
            if isinstance(item, dict):
                _check(blockers, item.get("path") == path, f"external path drift: {name}")
                _check(blockers, item.get("blob_sha1") == blob, f"external blob drift: {name}")
                _check(blockers, item.get("sha256") == digest, f"external hash drift: {name}")
                _check(blockers, item.get("declared_license") == license_name, f"external license drift: {name}")
        extension = source_record.get("python_extension_boundary")
        if isinstance(extension, dict):
            _check(blockers, extension.get("copied_into_lane") is False, "Python extension copy policy drift")
            _check(blockers, extension.get("runtime_license_scope") == "BSD-3-Clause", "Python runtime license scope drift")

    _mapping(document, blockers)

    contract = document.get("artifact_contract")
    _check(blockers, isinstance(contract, dict), "artifact contract missing")
    if isinstance(contract, dict):
        expected_contract = {
            "input": "strict_SimulationInputV1_JSON_only",
            "rejects_unknown_fields": True,
            "does_not_coerce_legacy_yaml": True,
            "output_files": ["meta.json", "arrays.npz"],
            "metadata_schema": "pybert.native-cli-result.v1",
            "arrays_format": "NumPy_NPY_float64_members_in_uncompressed_NPZ_container",
            "diagnostics": "typed_pipeline_capabilities_events_and_cancellation",
            "errors": "typed_json_on_stderr_and_nonzero_exit_without_success_artifacts",
            "output_directory_links_rejected": True,
        }
        for key, expected in expected_contract.items():
            _check(blockers, contract.get(key) == expected, f"artifact contract drift: {key}")

    wrapper = document.get("wrapper_boundary")
    _check(blockers, isinstance(wrapper, dict), "SIPI wrapper boundary missing")
    if isinstance(wrapper, dict):
        for key, expected in {
            "owner": "sipi_lane",
            "strict_json_admission": True,
            "artifact_writer": True,
            "uncompressed_npz_writer": True,
            "output_directory_symlink_rejection": True,
            "upstream_parity_claim": "excluded_from_native_numerical_core_parity",
        }.items():
            _check(blockers, wrapper.get(key) == expected, f"SIPI wrapper boundary drift: {key}")

    extension_contract = document.get("python_extension_boundary")
    _check(blockers, isinstance(extension_contract, dict), "Python extension boundary missing")
    if isinstance(extension_contract, dict):
        for key, expected in {
            "source_only_contract": "native/pybert-python/src/lib.rs",
            "copied_or_built_into_product": False,
            "clean_archive_cargo_check": "passed",
            "clean_archive_release_build": "passed",
            "pyo3_numpy_abi_boundary": "verified_against_pinned_source",
        }.items():
            _check(blockers, extension_contract.get(key) == expected, f"Python boundary drift: {key}")

    replay = document.get("fresh_replay")
    _check(blockers, isinstance(replay, dict), "fresh replay record missing")
    if isinstance(replay, dict):
        _check(
            blockers,
            replay.get("status") == "historical_observation_unbound_pending_immutable_runner",
            "fresh replay status drift or overclaim",
        )
        _check(blockers, replay.get("runner") == "tools/run_pb_02_direct_replay.py", "fresh replay runner drift")
        _check(blockers, replay.get("reports") == [], "fresh replay reports must remain empty until an immutable candidate commit")
        _check(blockers, replay.get("aggregate") is None, "fresh replay aggregate must remain empty until the second-stage replay")
        _check(blockers, replay.get("fixture") == "crates/sipi-pybert-direct/fixtures/pb-02-nrz.json", "fixture path drift")
        _check(blockers, replay.get("fixture_sha256") == "5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13", "fixture hash drift")
        historical = replay.get("historical_observation")
        _check(blockers, isinstance(historical, dict), "historical replay observation missing")
        if isinstance(historical, dict):
            _check(blockers, historical.get("oracle_processes") == 2, "historical oracle process count drift")
            _check(blockers, historical.get("product_processes") == 2, "historical product process count drift")
            for key in ("oracle_array_hashes_equal", "product_array_hashes_equal", "oracle_product_array_hashes_equal"):
                _check(blockers, historical.get(key) is True, f"historical replay parity flag drift: {key}")
            _check(blockers, historical.get("product_meta_sha256") == "27735e7c5767dff07322f40d03e412a740c3a53e54e2446606b9bfcc2ff32573", "historical product meta hash drift")
            _check(blockers, historical.get("product_arrays_npz_sha256") == "1d87aa3cd71aa0c0a673c50c6083c94ef519b73b3d82620ecbbbc532d4ebf957", "historical product NPZ hash drift")
            _check(blockers, historical.get("exact_array_hashes") == EXPECTED_ARRAY_HASHES, "historical array hash map drift")

    parity = document.get("parity")
    _check(blockers, isinstance(parity, dict), "parity record missing")
    if isinstance(parity, dict):
        for key, expected in {
            "scope": "one_explicit_PRBS7_NRZ_impulse_response_profile",
            "status": "historical_unbound_observation_only",
            "tolerance": "pending_immutable_replay",
            "all_uncovered_input_branches_remain_open": True,
            "row_promotion": "forbidden_until_independent_branch_matrix_is_complete",
        }.items():
            _check(blockers, parity.get(key) == expected, f"parity claim drift: {key}")

    audit = document.get("audit")
    _check(blockers, isinstance(audit, dict), "audit binding missing")
    audit_path = root / EXPECTED_AUDIT
    if isinstance(audit, dict):
        _check(blockers, audit.get("path") == EXPECTED_AUDIT, "audit path drift")
        _check(blockers, audit.get("sha256") == EXPECTED_AUDIT_SHA256, "audit hash binding drift")
    _check(blockers, audit_path.is_file(), "audit file missing")
    if audit_path.is_file():
        _check(blockers, _sha256(audit_path.read_bytes()) == EXPECTED_AUDIT_SHA256, "audit content hash drift")

    cargo_path = root / "crates" / "sipi-pybert-direct" / "Cargo.toml"
    _check(blockers, cargo_path.is_file(), "lane Cargo.toml missing")
    if cargo_path.is_file():
        try:
            cargo = tomllib.loads(cargo_path.read_text(encoding="utf-8"))
            _check(blockers, cargo.get("package", {}).get("name") == "sipi-pybert-direct", "lane crate name drift")
            _check(
                blockers,
                cargo.get("package", {}).get("license") is None
                and cargo.get("package", {}).get("license-file") == "NOTICE-PYBERT-LICENSE-BOUNDARY.md",
                "lane crate license boundary must remain unresolved and notice-bound",
            )
            _check(blockers, "workspace" in cargo, "lane-local workspace boundary missing")
        except (OSError, tomllib.TOMLDecodeError) as error:
            blockers.append(f"lane Cargo.toml invalid: {error}")

    required_files = [
        "NOTICE-PYBERT-LICENSE-BOUNDARY.md",
        "SOURCE-MAP.md",
        "src/lib.rs",
        "src/runner.rs",
        "src/bin/sipi-pybert-direct.rs",
        "tests/direct.rs",
        "fixtures/pb-02-nrz.json",
    ]
    for relative in required_files:
        _check(blockers, (CRATE / relative).is_file(), f"lane file missing: {relative}")
    notice_path = CRATE / "NOTICE-PYBERT-LICENSE-BOUNDARY.md"
    if notice_path.is_file():
        notice = notice_path.read_text(encoding="utf-8")
        for marker in (EXPECTED_COMMIT, EXPECTED_TREE, 'license = "MIT"', "BSD-3-Clause", "non-distributed"):
            _check(blockers, marker in notice, f"lane license-boundary marker missing: {marker}")
    source_map_path = CRATE / "SOURCE-MAP.md"
    if source_map_path.is_file():
        source_map = source_map_path.read_text(encoding="utf-8")
        for marker in ("native/pybert-core", "pb-02-direct-port.v1.yaml", "NOTICE-PYBERT-LICENSE-BOUNDARY.md"):
            _check(blockers, marker in source_map, f"lane source-map marker missing: {marker}")
    markers = {
        "src/lib.rs": ("mod runner;", "run_sim_native_json"),
        "src/runner.rs": (
            "strict_simulation_input_json",
            "simulate_native_v1",
            "meta.json",
            "arrays.npz",
            "typed_simulation_input_v1",
            "ERROR_SCHEMA",
            "PYTHON_BOUNDARY_SOURCE",
            "crc32",
            "npy_f64",
        ),
        "src/bin/sipi-pybert-direct.rs": ("--output-dir", "ExitCode"),
    }
    for relative, expected_markers in markers.items():
        path = CRATE / relative
        if path.is_file():
            if relative == "src/runner.rs":
                text = _historical_target(path, HISTORICAL_RUNNER_COMMIT).decode("utf-8")
            else:
                text = path.read_text(encoding="utf-8")
            for marker in expected_markers:
                _check(blockers, marker in text, f"lane marker missing: {relative}:{marker}")

    # The direct-port lane must not alter the product workspace root manifest.
    try:
        diff = _git(root, "diff", "--name-only", "--", "Cargo.toml")
        _check(blockers, diff == "", "root Cargo.toml was modified")
    except (OSError, subprocess.CalledProcessError):
        blockers.append("cannot inspect root Cargo.toml diff")

    source_checked = _verify_external_source(source, blockers) if source is not None else False
    non_claims = set(document.get("non_claims", []))
    for claim in (
        "This lane does not implement PB-03 legacy YAML projection, PB-04 selection, or PB-05 comparison.",
        "This lane does not copy the Python CLI or PyO3 extension source.",
        "The historical two-run observation is not immutable candidate evidence; reproducible admission waits for two reports and an aggregate from the pinned replay runner.",
        "Strict JSON admission, artifact writing, NPZ compression choice, and symlink rejection are SIPI wrapper policies and are excluded from the upstream native numerical parity claim.",
        "This lane does not change the product CLI, adapter, root Cargo workspace, PLAN, ledger, or release capability.",
        "This evidence is not a release or legal conclusion; BSD-3-Clause applies to the referenced PyBERT Python runtime boundary, while the copied native crate declares MIT.",
    ):
        _check(blockers, claim in non_claims, "required non-claim missing")

    return {
        "valid": not blockers,
        "schema": document.get("schema"),
        "status": document.get("status"),
        "source_paths": len(EXPECTED_SOURCE_FILES),
        "source_git_objects_checked": source_checked,
        "fresh_runs": 0,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--source", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        document = yaml.safe_load(args.evidence.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        print(json.dumps({"valid": False, "blockers": [f"cannot read evidence: {error}"]}))
        return 1
    result = verify(document, source=args.source)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("valid" if result["valid"] else "blocked")
        for blocker in result["blockers"]:
            print(f"- {blocker}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
