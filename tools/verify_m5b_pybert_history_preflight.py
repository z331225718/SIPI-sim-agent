"""Recreate and fail-close the M5B PyBERT history-import preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "b3d072e6d425fd1ea1254c61400971b750e10d9b"
SOURCE_TREE = "6428fa66c9735f2a5482a02c1988d778bb3416ea"


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=text)


def classify(path: str) -> tuple[str, str, str | None, str]:
    """Return decision, reason, future target, and license evidence status."""
    if path.startswith("PyAMI/"):
        return "drop", "legacy PyAMI is replaced by M5A-09 clean-room Rust", None, "not-applicable"
    if path.startswith((".agents/", ".claude/", ".codegraph/", ".reasonix/", ".tmp_", "user_input/")):
        return "drop", "local-agent, cache, experiment, or user-input artifact", None, "not-applicable"
    if path in {"AGENTS.md", "CLAUDE.md", "reasonix.toml"}:
        return "drop", "local-agent configuration is not product source", None, "not-applicable"
    if path.startswith("models/ibisami/") or path.endswith(".dll"):
        return "external-reference", "vendor AMI fixture must remain external", None, "authorized-restricted-or-unknown"
    if path.startswith("docs/") and path.endswith((".docx", ".html")):
        return "drop", "generated or office-document artifact", None, "not-applicable"
    if path.startswith("docs/") and path.endswith((".png", ".npz")):
        return "drop", "generated documentation artifact", None, "not-applicable"
    retained_prefixes = (".github/", "benchmarks/", "docs/", "models/sp_file/", "native/", "scripts/", "src/", "tests/")
    retained_roots = {
        ".gitignore", "ISSUES_2026-06-03.md", "LICENSE", "NOTICE", "PROJECT_RESTORE.md",
        "README.md", "de_sim.cfg", "hpeesofsim.cfg", "pyproject.toml", "requirements-wheelhouse.txt",
        "requirements.txt", "uv.lock",
    }
    if path.startswith(retained_prefixes) or path in retained_roots:
        target = f"engines/py-bert-agent/{path}"
        license_status = "BSD-3-Clause-root-evidence"
        if path.startswith("native/pybert-core/"):
            license_status = "BSD-derived-attribution-required; Cargo-MIT-consistency-pending"
        return "retain", "Python reference, compatibility, test, or clean-room Rust source", target, license_status
    return "drop", "not in candidate migration allowlist", None, "not-applicable"


def entries(repo: Path) -> list[dict[str, str | int | None]]:
    raw = git(repo, "ls-tree", "-r", "-z", SOURCE_COMMIT, text=False)
    result = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        header, encoded_path = item.split(b"\t", 1)
        mode, object_type, blob = header.decode("ascii").split()
        assert object_type == "blob"
        path = encoded_path.decode("utf-8")
        decision, reason, target, license_status = classify(path)
        entry: dict[str, str | int | None] = {
            "path": path,
            "mode": mode,
            "blob": blob,
            "decision": decision,
            "reason": reason,
            "owner": "PyBERT maintainers",
            "licenseStatus": license_status,
            "importTarget": target,
            "finalTarget": (
                f"native/crates/sipi-link/{path.removeprefix('native/pybert-core/')}"
                if path.startswith("native/pybert-core/") and decision == "retain"
                else target
            ),
        }
        result.append(entry)
    return sorted(result, key=lambda entry: str(entry["path"]))


def digest(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def verify_document(document: dict, repo: Path) -> dict:
    assert document["schema"] == "sipi.m5b.pybert-history-preflight.v1"
    assert document["mode"] == "preflight_only"
    assert document["migrationEligible"] is False
    source = document["source"]
    assert source == {
        "repository": "https://github.com/z331225718/Py-bert-agent.git",
        "objectFormat": "sha1",
        "ref": "pybert-core-rust-migration",
        "commit": SOURCE_COMMIT,
        "tree": SOURCE_TREE,
        "anchorStatus": "candidate",
    }
    assert document["dependencies"]["M5B-01"] == "pending"
    assert document["dependencies"]["M5B-02"] == "accepted"
    assert document["historyMapStatus"] == "pending"
    assert document["operation"] == {"filterRepoExecuted": False, "destinationCopyCreated": False}
    assert document["futureFilterRepo"]["status"] == "must-pin-at-execution"
    assert document["forbiddenArtifacts"] == [".git/filter-repo", "engines/py-bert-agent", "native/crates/sipi-link"]
    assert git(repo, "rev-parse", "HEAD").strip() == SOURCE_COMMIT
    assert git(repo, "rev-parse", "HEAD^{tree}").strip() == SOURCE_TREE
    assert not git(repo, "status", "--porcelain").strip()
    assert subprocess.run(["git", "-C", str(repo), "symbolic-ref", "-q", "HEAD"], stdout=subprocess.DEVNULL).returncode != 0
    assert not (repo / ".git" / "filter-repo").exists()
    assert not (ROOT / "engines" / "py-bert-agent").exists()
    assert not (ROOT / "native" / "crates" / "sipi-link").exists()
    observed = entries(repo)
    counts = dict(sorted(Counter(str(entry["decision"]) for entry in observed).items()))
    assert len(observed) == document["expandedPolicy"]["entryCount"]
    assert counts == document["expandedPolicy"]["decisionCounts"]
    assert digest(observed) == document["expandedPolicy"]["entryDigestSha256"]
    assert all(entry["owner"] and entry["licenseStatus"] for entry in observed)
    assert not any(entry["decision"] == "retain" and (str(entry["path"]).endswith(".dll") or str(entry["path"]).startswith(("PyAMI/", "models/ibisami/"))) for entry in observed)
    return {
        "mode": "preflight_only",
        "migrationEligible": False,
        "historyMapStatus": "pending",
        "source": source,
        "expandedPolicy": {"entryCount": len(observed), "decisionCounts": counts, "entryDigestSha256": digest(observed)},
        "entries": observed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--document", type=Path, default=ROOT / "docs/baselines/m5b-pybert-history-preflight.v1.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = verify_document(json.loads(args.document.read_text(encoding="utf-8")), args.source_repo)
    except (AssertionError, OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"PyBERT history preflight rejected: {error}", file=sys.stderr)
        return 2
    encoded = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
