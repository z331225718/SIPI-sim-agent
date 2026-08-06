"""Machine-check the M2 real-bundle external gate.

The M2 platform side is complete and audited; the real-bundle dual-run
equivalence additionally requires, per engine repository:
  - an annotated clean tag ``sipi-baseline/<engine>/<YYYYMMDD>.<n>`` with HEAD
    pointing at that tag and a clean worktree;
  - a license-manifest subject for that engine that is not ``blocked_unknown``;
  - required fixtures (per ``fixtures/manifest.v1.json``) not missing/partial.

Exit code 0 means ready for real-bundle M2 completion; 1 means not ready and
prints a JSON readiness report with blockers.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOS = {
    "agent-spice": ROOT.parent / "agent-spice",
    "pybert": ROOT.parent / "Py-bert-agent",
    "agent-com": ROOT.parent / "COM",
}


def git(args: list[str], repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def latest_baseline_tag(repo: Path, engine: str) -> str | None:
    tags = git(["tag", "-l", f"sipi-baseline/{engine}/*"], repo).stdout.splitlines()
    if not tags:
        return None
    return sorted(tags)[-1]


def is_annotated(repo: Path, tag: str) -> bool:
    result = git(["for-each-ref", f"refs/tags/{tag}", "--format=%(objecttype)"], repo)
    return result.stdout.strip() == "tag"


def worktree_clean(repo: Path) -> bool:
    return not git(["status", "--porcelain"], repo).stdout.strip()


def head_at_tag(repo: Path, tag: str) -> bool:
    return git(["rev-parse", "HEAD"], repo).stdout.strip() == git(["rev-parse", f"tags/{tag}^{{commit}}"], repo).stdout.strip()


def license_ready(manifest_text: str, engine: str) -> tuple[bool, list[str]]:
    """Line-based YAML block scan: subjects whose scope root_ref matches engine."""
    blockers: list[str] = []
    current_root: str | None = None
    found_subject = False
    for line in manifest_text.splitlines():
        match = re.search(r"root_ref:\s*([A-Za-z0-9_-]+)", line)
        if match:
            current_root = match.group(1)
            continue
        status = re.search(r"distribution_status:\s*([A-Za-z_]+)", line)
        if status is not None and current_root == engine:
            found_subject = True
            if status.group(1) == "blocked_unknown":
                blockers.append("license blocked_unknown")
            else:
                return True, []
    if not found_subject:
        blockers.append("no license subject for engine")
    return not blockers, blockers


def fixtures_ready(manifest: dict, engine: str) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    for asset in manifest.get("assets", []):
        if asset.get("source_ref") != engine:
            continue
        required = [entry.get("requirement") for entry in asset.get("required_by", [])]
        if "required" not in required:
            continue
        availability = asset.get("availability")
        if availability not in {"present", "present_unscanned"}:
            blockers.append(f"required fixture {asset.get('id')} availability={availability}")
    return not blockers, blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repos", type=json.loads, default=DEFAULT_REPOS)
    parser.add_argument("--license-manifest", type=Path, default=ROOT / "license-manifest.v1.yaml")
    parser.add_argument("--fixtures", type=Path, default=ROOT / "fixtures" / "manifest.v1.json")
    args = parser.parse_args()
    manifest_text = args.license_manifest.read_text(encoding="utf-8")
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    engines: list[dict] = []
    for engine, path in args.repos.items():
        repo = Path(path)
        blockers: list[str] = []
        tag = latest_baseline_tag(repo, engine) if repo.is_dir() else None
        if tag is None:
            blockers.append("no sipi-baseline tag")
        else:
            if not is_annotated(repo, tag):
                blockers.append("baseline tag is not annotated")
            if not worktree_clean(repo):
                blockers.append("worktree not clean")
            if not head_at_tag(repo, tag):
                blockers.append("HEAD does not point at baseline tag")
        license_ok, license_blockers = license_ready(manifest_text, engine)
        fixtures_ok, fixture_blockers = fixtures_ready(fixtures, engine)
        blockers.extend(license_blockers)
        blockers.extend(fixture_blockers)
        engines.append(
            {
                "engine": engine,
                "tag": tag,
                "license_ready": license_ok,
                "fixtures_ready": fixtures_ok,
                "ready": not blockers,
                "blockers": blockers,
            }
        )
    report = {"ready": all(item["ready"] for item in engines), "engines": engines}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
