"""Focused PB-03 replay payload tests."""

from __future__ import annotations

import copy
import io
import os
import sys
import tarfile
import tempfile
from types import SimpleNamespace
from unittest import mock
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pb_03_replay_common as replay_common  # noqa: E402
from pb_03_replay_common import (  # noqa: E402
    PB03_PARITY_ARRAYS,
    _extract_archive_payload,
    _validate_external_replay_root,
    _validate_fixture_path,
    _validate_materialized_root,
    payload_digest,
    run_command,
    run_main,
)


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


def test_pb03_run_command_is_offline_and_clears_compiler_overrides() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        cargo = root / "cargo.exe"
        rustc = root / "rustc.exe"
        cargo.write_bytes(b"cargo")
        rustc.write_bytes(b"rustc")
        captured = {}

        def fake_run(command, *, cwd, env, stdout, stderr, timeout, check):
            captured.update(command=command, cwd=cwd, env=env, timeout=timeout)
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with mock.patch.dict(
            os.environ,
            {
                "RUSTC_WRAPPER": "bad",
                "CARGO_BUILD_RUSTC_WRAPPER": "bad",
                "RUSTFLAGS": "bad",
                "CARGO_ENCODED_RUSTFLAGS": "bad",
            },
            clear=False,
        ), mock.patch.object(__import__("pb_03_replay_common").subprocess, "run", side_effect=fake_run):
            result = run_command(["cargo", "build", "--offline"], root, 2, {"cargo": cargo, "rustc": rustc})
        assert result["exit_code"] == 0
        assert captured["command"][0] == str(cargo)
        assert captured["env"]["CARGO_NET_OFFLINE"] == "true"
        assert captured["env"]["CARGO"] == str(cargo)
        assert captured["env"]["RUSTC"] == str(rustc)
        assert captured["env"]["CARGO_BUILD_RUSTC"] == str(rustc)
        for name in ("RUSTC_WRAPPER", "CARGO_BUILD_RUSTC_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
            assert name not in captured["env"]


def test_pb03_archive_links_fail_closed() -> None:
    for member_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
        with tempfile.TemporaryDirectory() as temporary:
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode="w") as archive:
                member = tarfile.TarInfo("link")
                member.type = member_type
                member.linkname = "outside"
                archive.addfile(member)
            destination = Path(temporary) / "archive"
            with pytest.raises(RuntimeError, match="archive links"):
                _extract_archive_payload(payload.getvalue(), destination)


def test_pb03_fixture_path_rejects_windows_and_parent_forms() -> None:
    for fixture in (r"nested\fixture.yaml", r"C:\fixture.yaml", r"\\server\share\fixture.yaml", "/fixture.yaml", "../fixture.yaml"):
        with pytest.raises(RuntimeError, match="fixture"):
            _validate_fixture_path(fixture)
    assert _validate_fixture_path("fixtures/input.yaml") == "fixtures/input.yaml"


def test_pb03_replay_root_requires_distinct_fresh_external_directory(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    upstream = tmp_path / "upstream"
    work = tmp_path / "work"
    candidate.mkdir()
    upstream.mkdir()
    work.mkdir()
    custody = _validate_external_replay_root(work, candidate, upstream)
    assert custody["work_root_created_new"] is True
    (work / "stale.json").write_text("stale", encoding="utf-8")
    with pytest.raises(RuntimeError, match="empty"):
        _validate_external_replay_root(work, candidate, upstream)
    with pytest.raises(RuntimeError, match="distinct"):
        _validate_external_replay_root(tmp_path / "fresh", candidate, candidate)
    nested = candidate / "nested"
    nested.mkdir()
    with pytest.raises(RuntimeError, match="outside"):
        _validate_external_replay_root(nested, candidate, upstream)
    nondir = tmp_path / "nondir"
    nondir.write_text("not a directory", encoding="utf-8")
    with pytest.raises(RuntimeError):
        _validate_external_replay_root(nondir, candidate, upstream)


def test_pb03_replay_root_reparse_and_access_errors_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "root"
    path.mkdir()
    with mock.patch.object(replay_common.Path, "lstat", return_value=SimpleNamespace(st_file_attributes=0x400)):
        assert replay_common._has_reparse_component(path) is True
    with mock.patch.object(replay_common.Path, "is_symlink", side_effect=PermissionError("denied")):
        with pytest.raises(RuntimeError, match="replay-root"):
            replay_common._has_reparse_component(path)


def test_pb03_materialized_root_must_remain_direct_child(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    escaped = tmp_path / "escaped"
    escaped.mkdir()
    with pytest.raises(RuntimeError, match="escaped"):
        _validate_materialized_root(escaped, work)


def test_pb03_tmp_root_inside_candidate_is_rejected_before_archive(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    upstream = tmp_path / "upstream"
    candidate.mkdir()
    upstream.mkdir()
    inside = candidate / "tmp"
    inside.mkdir()

    class FakeTemporaryDirectory:
        def __enter__(self):
            return str(inside)

        def __exit__(self, *_args):
            return False

    with mock.patch.object(replay_common.tempfile, "TemporaryDirectory", return_value=FakeTemporaryDirectory()), mock.patch.object(replay_common, "resolve_toolchain", return_value=({}, {})):
        with pytest.raises(RuntimeError, match="outside"):
            replay_common.run_once("PB-03", candidate, upstream, "fixture.yaml", "commit", "tree", "0" * 64, "run", 1)


def test_pb03_run_main_rejects_stale_report_without_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    output.write_text('{"status":"old"}\n', encoding="utf-8")
    args = SimpleNamespace(
        row="PB-03",
        candidate_repo=tmp_path,
        upstream_repo=tmp_path,
        fixture="fixture.yaml",
        candidate_commit="commit",
        candidate_tree="tree",
        candidate_archive_sha256="0" * 64,
        run_id="run",
        timeout_seconds=1,
        output=output,
    )
    with mock.patch.object(replay_common, "run_once") as run_once_mock:
        assert run_main(args) == 2
    run_once_mock.assert_not_called()
    assert output.read_text(encoding="utf-8") == '{"status":"old"}\n'
