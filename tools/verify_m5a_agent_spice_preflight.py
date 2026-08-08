"""Verify the exact source and path policy before the M5A history rewrite."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(f"{root}/")


def _kept(path: str, include: list[str], drop: list[str]) -> bool:
    return any(_within(path, root) for root in include) and not any(_within(path, root) for root in drop)


def _file_sha256(source: Path, commit: str, path: str) -> str:
    result = subprocess.run(["git", "-C", str(source), "show", f"{commit}:{path}"], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or f"missing {path}")
    return hashlib.sha256(result.stdout).hexdigest().upper()


def verify(document: dict, source: Path) -> dict:
    blockers: list[str] = []
    if document.get("schema") != "sipi.history-migration-preflight.v1":
        return {"ready": False, "blockers": ["schema mismatch"]}
    source_data = document.get("source")
    filter_data = document.get("filter")
    target = document.get("target")
    if not isinstance(source_data, dict) or not isinstance(filter_data, dict) or not isinstance(target, dict):
        return {"ready": False, "blockers": ["source, filter, and target are required"]}
    include = filter_data.get("include_paths")
    drop = filter_data.get("drop_paths")
    if not isinstance(include, list) or not include or not isinstance(drop, list):
        return {"ready": False, "blockers": ["filter paths are malformed"]}
    if any(not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts for path in [*include, *drop]):
        return {"ready": False, "blockers": ["filter paths must be non-empty relative paths"]}
    if not isinstance(target.get("prefix"), str) or not target["prefix"]:
        blockers.append("target prefix is required")
    for restricted in document.get("restricted_paths", []):
        path = restricted.get("path") if isinstance(restricted, dict) else None
        if not isinstance(path, str) or not any(_within(path, root) for root in drop):
            blockers.append(f"restricted path is not dropped: {path}")
    try:
        commit = _git(source, "rev-parse", "--verify", f"{source_data['commit']}^{{commit}}")
        if commit != source_data.get("commit"):
            blockers.append("source commit does not resolve exactly")
        tree = _git(source, "rev-parse", f"{commit}^{{tree}}")
        if tree != source_data.get("tree"):
            blockers.append("source tree mismatch")
        baseline = source_data.get("baseline")
        if not isinstance(baseline, dict):
            blockers.append("baseline is required")
        else:
            tag_commit = _git(source, "rev-parse", "--verify", f"{baseline.get('tag')}^{{commit}}")
            if tag_commit != baseline.get("commit"):
                blockers.append("baseline commit mismatch")
            if _git(source, "rev-parse", f"{tag_commit}^{{tree}}") != baseline.get("tree"):
                blockers.append("baseline tree mismatch")
            if subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor", tag_commit, commit]).returncode:
                blockers.append("baseline is not an ancestor of source commit")
        for evidence in source_data.get("evidence", []):
            if not isinstance(evidence, dict):
                blockers.append("malformed evidence")
                continue
            if _file_sha256(source, commit, str(evidence.get("path", ""))) != evidence.get("sha256"):
                blockers.append(f"evidence hash mismatch: {evidence.get('path')}")
        paths = _git(source, "ls-tree", "-r", "--name-only", commit).splitlines()
        retained = [path for path in paths if _kept(path, include, drop)]
        for required in filter_data.get("required_retained_paths", []):
            if not any(_within(path, required) for path in retained):
                blockers.append(f"required path is not retained: {required}")
        for restricted in document.get("restricted_paths", []):
            path = restricted.get("path") if isinstance(restricted, dict) else ""
            if any(_within(retained_path, path) for retained_path in retained):
                blockers.append(f"restricted path would be retained: {path}")
    except (KeyError, RuntimeError) as error:
        blockers.append(str(error))
        retained = []
        paths = []
    return {
        "ready": not blockers,
        "blockers": blockers,
        "source_commit": source_data.get("commit"),
        "retained_path_count": len(retained),
        "dropped_path_count": max(0, len(paths) - len(retained)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--preflight",
        type=Path,
        default=ROOT / "docs" / "baselines" / "migrations" / "m5a-agent-spice-preflight.v1.json",
    )
    args = parser.parse_args()
    try:
        document = json.loads(args.preflight.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"ready": False, "blockers": [f"preflight unreadable: {error}"]}))
        return 2
    report = verify(document, args.source)
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
