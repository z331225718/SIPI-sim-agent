"""Machine-check the M2 real-bundle external gate.

The M2 platform side is complete and audited; the real-bundle dual-run
equivalence additionally requires, per engine repository:
  - an annotated clean tag ``sipi-baseline/<engine>/<YYYYMMDD>.<n>`` with HEAD
    of the default branch pointing at that tag (the tag names a committed
    snapshot; uncommitted local files in any checkout do not corrupt it);
  - a license-manifest subject for that engine that is not ``blocked_unknown``;
  - required fixtures (per ``fixtures/manifest.v1.json``) not missing/partial.

Exit code 0 means ready for real-bundle M2 completion; 1 means not ready and
prints a JSON readiness report with blockers.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in minimal environments
    yaml = None

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


def default_branch_commit(repo: Path) -> str | None:
    origin = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], repo)
    if origin.returncode == 0 and origin.stdout.strip():
        branch = origin.stdout.strip().rsplit("/", 1)[-1]
    else:
        head = git(["symbolic-ref", "--quiet", "--short", "HEAD"], repo).stdout.strip()
        branch = head.rsplit("/", 1)[-1] if head else ""
    if not branch:
        return None
    resolved = git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], repo)
    return resolved.stdout.strip() or None


def default_branch_at_tag(repo: Path, tag: str) -> bool:
    branch_commit = default_branch_commit(repo)
    if branch_commit is None:
        return False
    return branch_commit == git(["rev-parse", f"tags/{tag}^{{commit}}"], repo).stdout.strip()


def license_ready(manifest_text: str, engine: str) -> tuple[bool, list[str]]:
    """Structured YAML check: every subject for the engine must be authorized."""
    if yaml is None:
        return False, ["pyyaml is unavailable; license manifest cannot be parsed"]
    try:
        document = yaml.safe_load(manifest_text)
    except Exception as error:  # noqa: BLE001 - gate must fail closed on any parse error
        return False, [f"license manifest unparsable: {error}"]
    if not isinstance(document, dict) or not isinstance(document.get("subjects"), list):
        return False, ["license manifest missing subjects"]
    matched = [subject for subject in document["subjects"] if subject.get("scope", {}).get("root_ref") == engine]
    if not matched:
        return False, ["no license subject for engine"]
    authorized = {
        subject.get("distribution_status")
        for subject in matched
        if subject.get("distribution_status") in {"authorized_public", "authorized_private", "external_reference_only"}
    }
    blockers = [
        f"license blocked_unknown: {subject.get('id')}"
        for subject in matched
        if subject.get("distribution_status") == "blocked_unknown"
    ]
    if not authorized:
        blockers.append("no authorized license subject")
    return not blockers and bool(authorized), blockers


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
            if not default_branch_at_tag(repo, tag):
                blockers.append("default branch HEAD does not point at baseline tag")
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
    try:
        raise SystemExit(main())
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"external gate check failed: {error}", file=sys.stderr)
        raise SystemExit(2)
