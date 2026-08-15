"""Run two clean-archive P3C delay-policy observations with verified cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OBSERVER_RELATIVE_PATH = Path("tools/observe_p3c_ads_transient_noncausal_delay_policy.py")
SCHEMA = "sipi.p3c-ads-transient-noncausal-delay-policy-fresh-observation.v1"
CHILD_SCHEMA = "sipi.p3c-ads-transient-noncausal-delay-policy-surface-observation.v1"


class FreshObservationError(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_external(path: Path, *, kind: str) -> Path:
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise FreshObservationError(f"{kind}_must_be_external")


def clean_archive_tree(commit: str) -> str:
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise FreshObservationError("clean_archive_commit_invalid")
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{commit}^{{tree}}"], check=True, capture_output=True, text=True, encoding="ascii").stdout.strip()
    except subprocess.CalledProcessError as error:
        raise FreshObservationError("clean_archive_commit_missing") from error


def safe_extract(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts or member.issym() or member.islnk() or not (member.isdir() or member.isfile()):
                raise FreshObservationError("clean_archive_member_rejected")
        archive.extractall(destination, members=members)


def materialize_clean_archive(*, commit: str, destination: Path) -> None:
    archive_path = destination.with_suffix(".tar")
    with archive_path.open("wb") as stream:
        try:
            subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", commit], check=True, stdout=stream, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as error:
            raise FreshObservationError("clean_archive_create_failed") from error
    destination.mkdir()
    safe_extract(archive_path, destination)


def assert_child_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema") != CHILD_SCHEMA:
        raise FreshObservationError("child_observation_schema_invalid")
    if value.get("runtime_invoked") is not False or value.get("custody") != "external_only_hash_only":
        raise FreshObservationError("child_observation_runtime_or_custody_invalid")
    conclusion = value.get("conclusion")
    if not isinstance(conclusion, dict) or conclusion.get("selected_run_delay_action_observed") is not False or conclusion.get("delay_seconds_derived") is not False:
        raise FreshObservationError("child_observation_delay_promotion")
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if any(token in serialized for token in ("\\\\", "://", "C:/", "C:\\\\")):
        raise FreshObservationError("child_observation_path_leak")
    return value


def observe_one(*, commit: str, s4p: Path, ads_document: Path, root: Path, ordinal: int) -> dict[str, object]:
    archive = root / f"archive-{ordinal}"
    materialize_clean_archive(commit=commit, destination=archive)
    report = root / f"report-{ordinal}.json"
    command = [sys.executable, "-B", str(archive / OBSERVER_RELATIVE_PATH), "--s4p", str(s4p), "--ads-document", str(ads_document), "--report", str(report)]
    result = subprocess.run(command, cwd=archive, check=False, capture_output=True, text=True, encoding="ascii", errors="strict")
    if result.returncode != 0 or result.stderr:
        raise FreshObservationError("child_observation_rejected")
    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise FreshObservationError("child_observation_envelope_invalid") from error
    if not isinstance(envelope, dict) or envelope.get("status") != "observed" or set(envelope) != {"status", "report_byte_length", "report_content_sha256"}:
        raise FreshObservationError("child_observation_envelope_invalid")
    payload = report.read_bytes()
    if envelope["report_byte_length"] != len(payload) or envelope["report_content_sha256"] != sha256_bytes(payload):
        raise FreshObservationError("child_observation_report_binding_invalid")
    try:
        return assert_child_result(json.loads(payload.decode("ascii")))
    except UnicodeDecodeError as error:
        raise FreshObservationError("child_observation_encoding_invalid") from error


def observe_fresh(*, commit: str, s4p: Path, ads_document: Path) -> dict[str, object]:
    source = require_external(s4p, kind="s4p")
    document = require_external(ads_document, kind="ads_document")
    tree = clean_archive_tree(commit)
    temporary = tempfile.TemporaryDirectory(prefix="sipi-p3c-delay-policy-")
    custody = Path(temporary.name)
    try:
        first = observe_one(commit=commit, s4p=source, ads_document=document, root=custody, ordinal=1)
        second = observe_one(commit=commit, s4p=source, ads_document=document, root=custody, ordinal=2)
        if first != second:
            raise FreshObservationError("fresh_observation_repeatability_rejected")
    finally:
        temporary.cleanup()
    if custody.exists():
        raise FreshObservationError("fresh_custody_cleanup_failed")
    return {
        "schema": SCHEMA,
        "clean_archive_commit": commit,
        "clean_archive_tree": tree,
        "fresh_observations": 2,
        "canonical_repeatability": "identical",
        "cleanup_status": "complete",
        "observation": first,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--s4p", required=True, type=Path)
    parser.add_argument("--ads-document", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(observe_fresh(commit=args.commit, s4p=args.s4p, ads_document=args.ads_document), sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
