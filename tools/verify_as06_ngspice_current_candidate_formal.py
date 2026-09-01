"""Verify the immutable AS-06 current-candidate ngspice record.

The record is intentionally limited to a two-run, external-ngspice result
observation.  It does not promote the solver, the Rust implementation, or
any S-parameter/Xyce route to a release claim.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
MAX_RECORD = 2 * 1024 * 1024
MAX_ARCHIVE = 128 * 1024 * 1024

REPORT_SCHEMA = "sipi.as-06-ngspice-current-candidate.v1"
AGGREGATE_SCHEMA = "sipi.as-06-ngspice-current-candidate.aggregate.v1"
MANIFEST_SCHEMA = "sipi.as-06-ngspice-current-candidate-formal.v1"
STATUS = "passed_scoped_external_observation"

FORMAL_DIR = "docs/baselines/as06-specific"
REPORTS = (
    f"{FORMAL_DIR}/as06-ngspice-current-candidate-run-01.v1.json",
    f"{FORMAL_DIR}/as06-ngspice-current-candidate-run-02.v1.json",
)
AGGREGATE = f"{FORMAL_DIR}/as06-ngspice-current-candidate-aggregate.v1.json"
MANIFEST = f"{FORMAL_DIR}/as06-ngspice-current-candidate.v1.yaml"
AUDIT = f"{FORMAL_DIR}/audit-2026-09-01-as06-ngspice-current-candidate.md"
VERIFIER = "tools/verify_as06_ngspice_current_candidate_formal.py"
TESTS = "tools/test_verify_as06_ngspice_current_candidate_formal.py"

CANDIDATE = {
    "commit": "a9543da167895a04077bb796c4942feec95e9b89",
    "tree": "c1ed1402410c25990e12c6ccdbe1dbb423660fd7",
    "sha256": "d0863f62973ba02a28c6fbe10718292bc0ab3f2dc5a2f43794c2edceab33385b",
    "bytes": 59975680,
}
UPSTREAM = {
    "commit": "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5",
    "tree": "b6bde97128030d6cea0d68b2f0a35d807be8c402",
    "sha256": "a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144",
    "bytes": 120238080,
}
RUNS = (
    {
        "run_id": "as06-a9543da1-run01",
        "caller_challenge": "97df5eeb69a6ff4ccefc347e9a98c88d42e1c26c15ffcf0aa324cf89d7d36d01",
        "fresh_run_nonce": "420223af26c9fed74d9766ff7caf24bda4bb0dae2a01dea5806529dd72d50b6b",
    },
    {
        "run_id": "as06-a9543da1-run02",
        "caller_challenge": "3d3bc8c6d5b60b76c7b2866dcf864109051612139ef5fb4b0e5b050d4da330f8",
        "fresh_run_nonce": "0945820d6e1a3657c414489c8ee129083de8bc7b2b5485d982f00422650a097a",
    },
)

RUNNER = {
    "path": "tools/run_as_06_ngspice_current_candidate.py",
    "commit": "36621b76ff400aad406575dc9b392cc794d2e593",
    "tree": "d239226250e452c195e2cf1e708726661ad8eaa9",
    "blob": "703ddead2dc8d8e1f6d66b3d8d6158c802450d0b",
    "sha256": "cafd4b98898dbac7a5b229aa0ed2ff2a38759679161c573dd0f9784a37ea4191",
    "bytes": 12260,
}
SOURCE_MAP = {
    "path": "docs/baselines/as-06-run-rfm-source-map.v4.yaml",
    "sha256": "9c96655e08fce504ae936b4e0c0cfb93a53ceafee7f0a3a9f848e1add0239304",
}
INPUTS = {
    "deck_sha256": "4c9bcfe30462ca61c62d9ecba9c50d73311f5e18b57cc6afe7e58c76f2b56e5a",
    "rfm_sha256": "894b5da3aba954d3d288689458be99d7434db966b4df4675db52165c4db2b55d",
    "code_model_sha256": "a23fa36d39328c8a000eb405a66cd293dae6015f3f50df09c4ea887faa104bab",
    "ngspice_sha256": "86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453",
}
CLAIMS = {
    "external_solver_scoped_observation": True,
    "solver_correctness": False,
    "release_acceptance": False,
    "s_parameter_fit": False,
    "as05_xyce_xdm": False,
    "environment_injection_resistance": False,
    "hostile_writer_resistance": False,
}
RESULT = {
    "headers": ["time", "v(src)", "v(out)"],
    "waveform_rows": 1029,
    "float_bit_exact": True,
    "max_abs_error": 0.0,
    "logical_manifest_equal": True,
    "runtime_semantics_equal": True,
    "rust_reconstruction_rms": 0.0,
    "upstream_reconstruction_rms": 0.0,
    "rust_reconstruction_max": 0.0,
    "upstream_reconstruction_max": 0.0,
}

DECK = "artifacts/rfm-ngspice-poc/product-run/direct-rfm-example.sp"
RFM = "artifacts/rfm-ngspice-poc/source-fit/source_model.rfm"
MODEL = "src/agent_spice/lib/ngspice/rfm.cm"


class StrictLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate keys."""


def _mapping(loader: StrictLoader, node: yaml.MappingNode, deep: bool = False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def _hex(value: object, length: int = 64) -> bool:
    pattern = HEX64 if length == 64 else HEX40
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _typed_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(
            _typed_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _finite(value: object) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite value")
        return
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
        return
    if isinstance(value, list):
        for child in value:
            _finite(child)
        return
    raise ValueError("unsupported value type")


def _no_absolute_paths(value: object) -> None:
    if isinstance(value, str):
        if re.search(r"(?i)(?:^[a-z]:[\\/]|^//|^/|[\\/]Users[\\/]|[\\/]home[\\/])", value):
            raise ValueError("absolute path leaked into record")
        if "\\\\" in value:
            raise ValueError("UNC path leaked into record")
        return
    if isinstance(value, dict):
        for child in value.values():
            _no_absolute_paths(child)
        return
    if isinstance(value, list):
        for child in value:
            _no_absolute_paths(child)


def _exact(value: object, keys: tuple[str, ...], label: str) -> None:
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"{label} keyset drift")


def _receipt(value: object, label: str, expected_basename: str | None = None) -> None:
    _exact(value, ("basename", "bytes", "sha256", "nlink", "path_redacted"), label)
    if not isinstance(value["basename"], str) or not value["basename"]:
        raise ValueError(f"{label} basename drift")
    if "/" in value["basename"] or "\\" in value["basename"]:
        raise ValueError(f"{label} basename is a path")
    if expected_basename is not None and value["basename"] != expected_basename:
        raise ValueError(f"{label} basename drift")
    if type(value["bytes"]) is not int or value["bytes"] <= 0:
        raise ValueError(f"{label} byte count drift")
    if type(value["nlink"]) is not int or value["nlink"] < 1:
        raise ValueError(f"{label} link count drift")
    if value["path_redacted"] is not True or not _hex(value["sha256"]):
        raise ValueError(f"{label} receipt drift")


def _toolchain(value: object, label: str) -> None:
    roles = ("cargo", "rustc", "python", "ngspice")
    _exact(value, roles, label)
    expected_basenames = {
        "cargo": "cargo.exe",
        "rustc": "rustc.exe",
        "python": "python.exe",
        "ngspice": "ngspice.exe",
    }
    for role in roles:
        item = value[role]
        _exact(
            item,
            ("role", "basename", "sha256", "version_exit", "version_sha256", "path_redacted"),
            f"{label}.{role}",
        )
        if item["role"] != role or item["basename"] != expected_basenames[role]:
            raise ValueError(f"{label}.{role} identity drift")
        if not _hex(item["sha256"]) or not _hex(item["version_sha256"]):
            raise ValueError(f"{label}.{role} hash drift")
        if type(item["version_exit"]) is not int or item["version_exit"] != 0:
            raise ValueError(f"{label}.{role} version drift")
        if item["path_redacted"] is not True:
            raise ValueError(f"{label}.{role} path disclosure")


def _dependency(value: object, label: str) -> None:
    _exact(value, ("files", "bytes", "sha256", "path_redacted"), label)
    if type(value["files"]) is not int or value["files"] < 1:
        raise ValueError(f"{label} file count drift")
    if type(value["bytes"]) is not int or value["bytes"] < 1:
        raise ValueError(f"{label} byte count drift")
    if not _hex(value["sha256"]) or value["path_redacted"] is not True:
        raise ValueError(f"{label} inventory drift")


def _load_json(path: Path) -> tuple[dict, bytes, str]:
    raw = path.read_bytes()
    if len(raw) > MAX_RECORD:
        raise ValueError("record exceeds size budget")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_json_pairs, parse_constant=_json_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid JSON record: {path.name}") from exc
    if type(value) is not dict:
        raise ValueError("record root is not an object")
    _finite(value)
    _no_absolute_paths(value)
    return value, raw, hashlib.sha256(raw).hexdigest()


def _validate_report(value: dict, expected_run: dict | None = None) -> dict:
    root_keys = (
        "schema",
        "status",
        "run_id",
        "caller_challenge",
        "fresh_run_nonce",
        "runner_sha256",
        "candidate",
        "upstream",
        "toolchain_pre",
        "toolchain_post",
        "binary_pre",
        "binary_post",
        "dependency_pre",
        "dependency_post",
        "environment",
        "source_map",
        "inputs",
        "physical",
        "canonical",
        "result",
        "claims",
    )
    _exact(value, root_keys, "report")
    if value["schema"] != REPORT_SCHEMA or value["status"] != "passed":
        raise ValueError("report header drift")
    if value["candidate"] != CANDIDATE or value["upstream"] != UPSTREAM:
        raise ValueError("report archive binding drift")
    if value["inputs"] != INPUTS or value["claims"] != CLAIMS or value["result"] != RESULT:
        raise ValueError("report semantic binding drift")
    if not _hex(value["caller_challenge"]) or not _hex(value["fresh_run_nonce"]):
        raise ValueError("report nonce/challenge drift")
    if not _hex(value["runner_sha256"]):
        raise ValueError("report runner hash drift")
    if value["runner_sha256"] != RUNNER["sha256"]:
        raise ValueError("report runner binding drift")
    if expected_run is not None:
        for key in ("run_id", "caller_challenge", "fresh_run_nonce"):
            if value[key] != expected_run[key]:
                raise ValueError(f"report {key} drift")

    _toolchain(value["toolchain_pre"], "toolchain_pre")
    _toolchain(value["toolchain_post"], "toolchain_post")
    if value["toolchain_pre"] != value["toolchain_post"]:
        raise ValueError("toolchain changed during replay")
    if value["toolchain_pre"]["ngspice"]["sha256"] != INPUTS["ngspice_sha256"]:
        raise ValueError("ngspice binding drift")

    _receipt(value["binary_pre"], "binary_pre", "sipi-agent-spice-run-rfm.exe")
    _receipt(value["binary_post"], "binary_post", "sipi-agent-spice-run-rfm.exe")
    if value["binary_pre"] != value["binary_post"]:
        raise ValueError("binary changed during replay")
    _dependency(value["dependency_pre"], "dependency_pre")
    _dependency(value["dependency_post"], "dependency_post")
    if value["dependency_pre"] != value["dependency_post"]:
        raise ValueError("dependency inventory changed during replay")

    if value["environment"] != {
        "policy": "cargo_rust_python_uv_pip_spice_prefixes_removed",
        "cargo_target_fresh": True,
    }:
        raise ValueError("environment policy drift")
    if value["source_map"] != SOURCE_MAP:
        raise ValueError("source-map binding drift")

    _exact(value["physical"], (
        "rust_waveform", "upstream_waveform", "rust_manifest", "upstream_manifest",
        "rust_stdout", "upstream_stdout",
    ), "physical")
    expected = {
        "rust_waveform": "waveform.csv",
        "upstream_waveform": "waveform.csv",
        "rust_manifest": "rfm_run_manifest.json",
        "upstream_manifest": "rfm_run_manifest.json",
        "rust_stdout": "stdout.log",
        "upstream_stdout": "stdout.log",
    }
    for key, basename in expected.items():
        _receipt(value["physical"][key], f"physical.{key}", basename)
    _exact(value["canonical"], ("rust_f64_sha256", "upstream_f64_sha256"), "canonical")
    if (
        not _hex(value["canonical"]["rust_f64_sha256"])
        or value["canonical"]["rust_f64_sha256"] != value["canonical"]["upstream_f64_sha256"]
    ):
        raise ValueError("canonical digest drift")
    return value


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _relative(path: str) -> None:
    candidate = Path(path)
    if not path or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("formal path is not repository-relative")
    if "\\" in path:
        raise ValueError("formal path must use forward slashes")


def _aggregate_documents(paths: tuple[Path, Path]) -> dict:
    loaded = []
    for index, path in enumerate(paths):
        value, raw, raw_sha = _load_json(path)
        _validate_report(value, RUNS[index])
        loaded.append((value, raw, raw_sha))
    values = [item[0] for item in loaded]
    if len({value["run_id"] for value in values}) != 2:
        raise ValueError("run IDs are not distinct")
    if len({value["caller_challenge"] for value in values}) != 2:
        raise ValueError("caller challenges are not distinct")
    if len({value["fresh_run_nonce"] for value in values}) != 2:
        raise ValueError("fresh nonces are not distinct")
    stable = (
        "runner_sha256", "candidate", "upstream", "toolchain_pre", "toolchain_post",
        "environment", "source_map", "inputs", "canonical", "result", "claims",
    )
    for key in stable:
        if values[0][key] != values[1][key]:
            raise ValueError(f"cross-run {key} drift")
    records = [
        {
            "path": REPORTS[index],
            "bytes": len(item[1]),
            "sha256": item[2],
            "run_id": item[0]["run_id"],
            "caller_challenge": item[0]["caller_challenge"],
            "fresh_run_nonce": item[0]["fresh_run_nonce"],
        }
        for index, item in enumerate(loaded)
    ]
    integrity = [
        {
            "binary_pre": item[0]["binary_pre"],
            "binary_post": item[0]["binary_post"],
            "dependency_pre": item[0]["dependency_pre"],
            "dependency_post": item[0]["dependency_post"],
            "physical": item[0]["physical"],
        }
        for item in loaded
    ]
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": STATUS,
        "reports": records,
        "candidate": CANDIDATE,
        "upstream": UPSTREAM,
        "runner_sha256": RUNNER["sha256"],
        "toolchain": values[0]["toolchain_pre"],
        "environment": values[0]["environment"],
        "source_map": SOURCE_MAP,
        "inputs": INPUTS,
        "canonical": values[0]["canonical"],
        "result": RESULT,
        "claims": CLAIMS,
        "integrity": integrity,
    }


def _git_raw(repository: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        timeout=180,
    ).stdout


def _git(repository: Path, *args: str) -> str:
    return _git_raw(repository, *args).decode("ascii").strip()


def _archive_identity(repository: Path, expected: dict) -> None:
    if _git(repository, "rev-parse", expected["commit"]) != expected["commit"]:
        raise ValueError("Git commit identity drift")
    if _git(repository, "show", "-s", "--format=%T", expected["commit"]) != expected["tree"]:
        raise ValueError("Git tree identity drift")
    process = subprocess.run(
        ["git", "-C", str(repository), "archive", "--format=tar", expected["commit"]],
        check=True,
        capture_output=True,
        timeout=240,
    )
    payload = process.stdout
    if len(payload) > MAX_ARCHIVE:
        raise ValueError("Git archive exceeds budget")
    if len(payload) != expected["bytes"] or _sha_bytes(payload) != expected["sha256"]:
        raise ValueError("Git archive content drift")


def _candidate_source_bindings(repository: Path) -> None:
    runner_blob = _git(repository, "rev-parse", f"{RUNNER['commit']}:{RUNNER['path']}")
    if runner_blob != RUNNER["blob"]:
        raise ValueError("runner Git blob drift")
    if _git(repository, "show", "-s", "--format=%T", RUNNER["commit"]) != RUNNER["tree"]:
        raise ValueError("runner commit tree drift")
    candidate_blob = _git(repository, "rev-parse", f"{CANDIDATE['commit']}:{RUNNER['path']}")
    if candidate_blob != RUNNER["blob"]:
        raise ValueError("candidate runner blob drift")
    if _sha_bytes(_git_raw(repository, "show", f"{CANDIDATE['commit']}:{RUNNER['path']}")) != RUNNER["sha256"]:
        raise ValueError("candidate runner content drift")
    source_blob = _git_raw(repository, "show", f"{CANDIDATE['commit']}:{SOURCE_MAP['path']}")
    if _sha_bytes(source_blob) != SOURCE_MAP["sha256"]:
        raise ValueError("candidate source-map content drift")


def _upstream_input_bindings(repository: Path) -> None:
    expected = {
        DECK: INPUTS["deck_sha256"],
        RFM: INPUTS["rfm_sha256"],
        MODEL: INPUTS["code_model_sha256"],
    }
    # `git archive` applies the committed export attributes.  The replay reads
    # that materialized archive, so bind its bytes rather than raw Git blobs.
    payload = _git_raw(repository, "archive", "--format=tar", UPSTREAM["commit"])
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for relative, wanted in expected.items():
            member = archive.getmember(relative)
            stream = archive.extractfile(member)
            if stream is None or _sha_bytes(stream.read()) != wanted:
                raise ValueError(f"upstream input drift: {relative}")


def _audit_text() -> str:
    return (
        "# AS-06 current-candidate ngspice parity\n\n"
        "Status: `passed_scoped_external_observation`.\n\n"
        "Candidate archive: `a9543da167895a04077bb796c4942feec95e9b89` "
        "(`d0863f62973ba02a28c6fbe10718292bc0ab3f2dc5a2f43794c2edceab33385b`, "
        "59975680 bytes).\n"
        "Pinned upstream archive: `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` "
        "(`a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144`, "
        "120238080 bytes).\n"
        "Replay runner: `tools/run_as_06_ngspice_current_candidate.py`, committed at "
        "`36621b76ff400aad406575dc9b392cc794d2e593`, content SHA-256 "
        "`cafd4b98898dbac7a5b229aa0ed2ff2a38759679161c573dd0f9784a37ea4191`.\n\n"
        "Two fresh immutable replays were copied from validated temporary outputs:\n\n"
        f"- `{REPORTS[0]}`: `c4005814660f0cfaaaaaac90f9c84defd77e4117606d90a0671d5a4f25b7cfe6`\n"
        f"- `{REPORTS[1]}`: `3b1c15eaaf6e415ad843d19409b4d1c1661bc618a021fe9d8cb1c96151e4bd5b`\n"
        f"- `{AGGREGATE}`: `59647b791187c9d36676c9cf39cfa8ecec27ef04b3bb821b8043d38c7f572953`\n"
        "\nBoth reports passed the runner's bounded comparison: 1029 waveform rows, "
        "headers `time/v(src)/v(out)`, zero maximum absolute error, bit-exact canonical "
        "float payloads, equal logical manifests, and equal runtime reconstruction "
        "semantics. Toolchain, input, source-map, and pre/post integrity receipts are "
        "validated by the formal verifier.\n\n"
        "This is an external ngspice observation for the named candidate and pinned "
        "upstream Git archives only. It does not claim solver correctness, release "
        "acceptance, hostile-writer resistance, environment-injection resistance, "
        "S-parameter fitting, or AS-05 Xyce/XDM support.\n"
    )


def _verify_manifest_shape(manifest: dict) -> None:
    _exact(
        manifest,
        (
            "schema", "status", "scope", "harness", "candidate", "upstream", "inputs",
            "records", "audit", "verification", "result", "claims",
        ),
        "manifest",
    )
    if manifest["schema"] != MANIFEST_SCHEMA or manifest["status"] != STATUS:
        raise ValueError("manifest header drift")
    _exact(manifest["scope"], ("workflow", "backend", "evidence_class", "comparison"), "scope")
    if manifest["scope"] != {
        "workflow": "AS-06",
        "backend": "ngspice",
        "evidence_class": "current_candidate_immutable_external_observation",
        "comparison": "Rust direct RFM workflow versus pinned Agent-Spice ngspice workflow",
    }:
        raise ValueError("scope drift")
    _exact(manifest["harness"], ("runner",), "harness")
    if manifest["harness"]["runner"] != RUNNER:
        raise ValueError("harness binding drift")
    if manifest["candidate"] != CANDIDATE or manifest["upstream"] != UPSTREAM:
        raise ValueError("manifest archive binding drift")
    if manifest["inputs"] != INPUTS or manifest["result"] != RESULT or manifest["claims"] != CLAIMS:
        raise ValueError("manifest semantic binding drift")
    _exact(manifest["records"], (*REPORTS, AGGREGATE), "records")
    for index, path in enumerate(REPORTS):
        record = manifest["records"][path]
        _exact(record, ("sha256", "bytes", "run_id", "caller_challenge", "fresh_run_nonce"), f"records.{index}")
        if (
            not _hex(record["sha256"])
            or type(record["bytes"]) is not int
            or record["bytes"] <= 0
            or record["run_id"] != RUNS[index]["run_id"]
            or record["caller_challenge"] != RUNS[index]["caller_challenge"]
            or record["fresh_run_nonce"] != RUNS[index]["fresh_run_nonce"]
        ):
            raise ValueError("report record binding drift")
    aggregate_record = manifest["records"][AGGREGATE]
    _exact(aggregate_record, ("sha256", "bytes"), "records.aggregate")
    if not _hex(aggregate_record["sha256"]) or type(aggregate_record["bytes"]) is not int or aggregate_record["bytes"] <= 0:
        raise ValueError("aggregate record binding drift")
    _exact(manifest["audit"], ("path", "sha256", "bytes"), "audit")
    if manifest["audit"]["path"] != AUDIT or not _hex(manifest["audit"]["sha256"]):
        raise ValueError("audit binding drift")
    if type(manifest["audit"]["bytes"]) is not int or manifest["audit"]["bytes"] <= 0:
        raise ValueError("audit byte binding drift")
    _exact(manifest["verification"], ("verifier", "tests"), "verification")
    for key, path in (("verifier", VERIFIER), ("tests", TESTS)):
        item = manifest["verification"][key]
        _exact(item, ("path", "sha256", "bytes"), f"verification.{key}")
        if item["path"] != path or not _hex(item["sha256"]):
            raise ValueError(f"verification.{key} binding drift")
        if type(item["bytes"]) is not int or item["bytes"] <= 0:
            raise ValueError(f"verification.{key} byte drift")


def _verify_file_binding(repository: Path, path: str, expected: dict) -> bytes:
    _relative(path)
    target = repository / path
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"formal file missing or symlink: {path}")
    raw = target.read_bytes()
    if len(raw) != expected["bytes"] or _sha_bytes(raw) != expected["sha256"]:
        raise ValueError(f"formal file hash drift: {path}")
    return raw


def verify(repository: Path, upstream_repository: Path) -> dict:
    manifest_path = repository / MANIFEST
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = yaml.load(manifest_text, Loader=StrictLoader)
    if type(manifest) is not dict:
        raise ValueError("manifest is not a mapping")
    _finite(manifest)
    _no_absolute_paths(manifest)
    _verify_manifest_shape(manifest)

    for key, path in (("verifier", VERIFIER), ("tests", TESTS)):
        _verify_file_binding(repository, path, manifest["verification"][key])
    for path in REPORTS:
        _relative(path)
    _relative(AGGREGATE)
    _relative(AUDIT)

    _archive_identity(repository, CANDIDATE)
    _candidate_source_bindings(repository)
    _archive_identity(upstream_repository, UPSTREAM)
    _upstream_input_bindings(upstream_repository)

    report_paths = []
    for index, path in enumerate(REPORTS):
        raw = _verify_file_binding(repository, path, manifest["records"][path])
        value, parsed_raw, raw_sha = _load_json(repository / path)
        if raw != parsed_raw or raw_sha != _sha_bytes(raw):
            raise ValueError("report read inconsistency")
        _validate_report(value, RUNS[index])
        report_paths.append(repository / path)

    aggregate_raw = _verify_file_binding(repository, AGGREGATE, manifest["records"][AGGREGATE])
    stored_aggregate, parsed_aggregate, _ = _load_json(repository / AGGREGATE)
    if aggregate_raw != parsed_aggregate:
        raise ValueError("aggregate read inconsistency")
    expected_aggregate = _aggregate_documents((report_paths[0], report_paths[1]))
    if not _typed_equal(stored_aggregate, expected_aggregate):
        raise ValueError("aggregate semantic drift")

    audit_raw = _verify_file_binding(repository, AUDIT, manifest["audit"])
    if audit_raw.decode("utf-8") != _audit_text():
        raise ValueError("audit text drift")
    return {
        "valid": True,
        "status": STATUS,
        "candidate": CANDIDATE,
        "upstream": UPSTREAM,
        "reports": [
            {"path": path, "sha256": manifest["records"][path]["sha256"]} for path in REPORTS
        ],
        "aggregate": manifest["records"][AGGREGATE]["sha256"],
        "claims": CLAIMS,
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--upstream-repository", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.repository.resolve(), args.upstream_repository.resolve()), sort_keys=True))
        return 0
    except Exception as exc:  # pragma: no cover - CLI failure path
        print(f"blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
