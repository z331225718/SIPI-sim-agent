from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
TOOL = ROOT / "tools" / "compare_m5b_ami_exact_host_outputs.py"
SPEC = importlib.util.spec_from_file_location("m5b_ami_host_compare", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_text_observation_preserves_none_and_utf8_identity():
    assert MODULE.text_observation(None) == {"present": False, "sha256": None, "byteLength": 0}
    observed = MODULE.text_observation("(example_rx\n)\n")
    assert observed["present"] is True
    assert observed["byteLength"] == len("(example_rx\n)\n".encode("utf-8"))


def test_compare_sidecar_requires_exact_bytes_not_tolerance():
    descriptor = {"path": "samples.f64le", "sha256": "", "byteLength": 8, "elementCount": 1, "encoding": "f64le", "endianness": "little"}
    with tempfile.TemporaryDirectory() as left_name, tempfile.TemporaryDirectory() as right_name:
        left, right = Path(left_name), Path(right_name)
        (left / "samples.f64le").write_bytes(b"\x00\x00\x00\x00\x00\x00\xf0?")
        (right / "samples.f64le").write_bytes(b"\x01\x00\x00\x00\x00\x00\xf0?")
        descriptor["sha256"] = MODULE.sha256_bytes((left / "samples.f64le").read_bytes())
        other = dict(descriptor, sha256=MODULE.sha256_bytes((right / "samples.f64le").read_bytes()))
        try:
            MODULE.compare_sidecar(descriptor, other, left, right)
        except ValueError as error:
            assert "host output bytes differ" in str(error)
        else:
            raise AssertionError("nearby but non-identical f64 bytes were accepted")


def test_helper_has_strict_abi_status_and_single_clock_sentinel_contract():
    assert "init.restype = c_long" in MODULE.REFERENCE_HELPER
    assert "get_wave.restype = c_long" in MODULE.REFERENCE_HELPER
    assert "close.restype = c_long" in MODULE.REFERENCE_HELPER
    assert "if value == -1.0" in MODULE.REFERENCE_HELPER
