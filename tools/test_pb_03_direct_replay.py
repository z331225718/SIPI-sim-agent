"""Focused PB-03 replay payload tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pb_03_replay_common import PB03_PARITY_ARRAYS, payload_digest  # noqa: E402


def test_pb03_digest_uses_stable_native_intersection() -> None:
    members = {name: {"count": 1, "dtype": "<f8", "shape": [1], "fortran_order": False, "f64_sha256": "0" * 64} for name in PB03_PARITY_ARRAYS}
    members["upstream_only.npy"] = copy.deepcopy(next(iter(members.values())))
    summary = {"arrays": {"logical_members": members}}
    original = payload_digest(summary, "PB-03")
    assert original is not None
    members[PB03_PARITY_ARRAYS[0]]["f64_sha256"] = "1" * 64
    assert payload_digest(summary, "PB-03") != original


def test_pb03_digest_fails_closed_when_stable_member_is_missing() -> None:
    members = {name: {"count": 1} for name in PB03_PARITY_ARRAYS[:-1]}
    assert payload_digest({"arrays": {"logical_members": members}}, "PB-03") is None
