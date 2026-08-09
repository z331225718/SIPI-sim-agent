"""Fail closed on any drift from the user-authorized, external AMI fixture."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def blob(repo: Path, commit: str, path: str) -> tuple[str, bytes]:
    object_id = subprocess.check_output(["git", "-C", str(repo), "rev-parse", f"{commit}:{path}"], text=True).strip()
    data = subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{path}"])
    return object_id, data

def verify(document: dict, repo: Path) -> dict:
    assert document["schema"] == "sipi.m5b-ami-vendor-fixture-preflight.v1"
    assert document["status"] == "authorized_restricted_runtime_only"
    source, fixture, authorization = document["source"], document["fixture"], document["authorization"]
    assert authorization["distributionStatus"] == "authorized_private"
    assert fixture["runtimeInvoked"] is False and fixture["assetCopied"] is False and fixture["promotion"] is False
    required = {"ibs", "ami", "dll"}
    assert {asset["kind"] for asset in fixture["assets"]} == required
    resolved = []
    for asset in fixture["assets"]:
        object_id, data = blob(repo, source["commit"], asset["path"])
        assert object_id == asset["blob"]
        assert len(data) == asset["byteLength"]
        assert hashlib.sha256(data).hexdigest() == asset["sha256"]
        resolved.append({"kind": asset["kind"], "blob": object_id, "sha256": asset["sha256"]})
    return {"authorizedRuntimeOnly": True, "promotion": False, "assets": resolved}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pybert-repo", type=Path, required=True)
    parser.add_argument("--document", type=Path, default=ROOT / "docs/baselines/m5b-ami-vendor-fixture-preflight.v1.json")
    args = parser.parse_args(argv)
    try:
        report = verify(json.loads(args.document.read_text(encoding="utf-8")), args.pybert_repo)
    except (AssertionError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"vendor fixture preflight rejected: {error}", file=sys.stderr); return 2
    print(json.dumps(report, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
