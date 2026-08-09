from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
TOOL = ROOT / "tools" / "replay_m5b_ami_authorized_runtime.py"
SPEC = importlib.util.spec_from_file_location("m5b_runtime_replay", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_exact_request_is_versioned_and_not_caller_configurable():
    model = {key: {"path": f"{key}.bin", "sha256": "a" * 64, "byteLength": 1} for key in ("ibis", "ami", "dll")}
    sidecar = {"path": "input.f64le", "sha256": "b" * 64, "byteLength": 16, "elementCount": 2, "encoding": "f64le", "endianness": "little"}
    request = MODULE.request_document(model, sidecar, sidecar)
    assert request["schema"] == MODULE.REQUEST_SCHEMA
    assert request["amiParametersIn"] == "(example_rx)"
    assert request["getWave"]["clockCapacity"] == 8
    assert request["sampleIntervalSeconds"] == 1e-12


def test_result_rejects_sidecar_escape_and_partial_output():
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        (output / "result.json").write_text("{}", encoding="utf-8")
        escaped = {"path": "../outside.f64le", "sha256": "a" * 64, "byteLength": 0, "elementCount": 0, "encoding": "f64le", "endianness": "little"}
        try:
            MODULE.verify_f64_descriptor(escaped, output)
        except ValueError as error:
            assert "sidecar basename" in str(error)
        else:
            raise AssertionError("sidecar escape was accepted")


def test_report_serialization_has_no_absolute_path():
    value = {"schema": MODULE.REPORT_SCHEMA, "fixture": {"sourceCommit": "f6ba031"}}
    assert ":\\" not in json.dumps(value, sort_keys=True)
