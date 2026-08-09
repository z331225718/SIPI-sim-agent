"""Fail-closed verifier for an explicit M5B AMI host candidate bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from build_m5b_ami_candidate_bundle import REQUEST_SCHEMA, RESULT_SCHEMA, SCHEMA, sha256_file


ROOT = Path(__file__).resolve().parents[1]
VENDOR_SUFFIXES = {".dll", ".ami", ".ibs"}


def reject(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(bundle: Path, source_root: Path = ROOT) -> dict[str, Any]:
    manifest_path = bundle / "candidate-manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    reject(document.get("schema") == SCHEMA, "schema")
    reject(document.get("candidate") is True and document.get("productionResolvable") is False, "candidate flags")
    reject(document.get("platform") == "windows-x86_64", "platform")
    protocol = document.get("protocol")
    reject(protocol == {"requestSchema": REQUEST_SCHEMA, "resultSchema": RESULT_SCHEMA}, "protocol")
    executable = document.get("executable")
    reject(isinstance(executable, dict), "executable descriptor")
    bundle_path = executable.get("bundlePath")
    reject(isinstance(bundle_path, str) and Path(bundle_path).name == bundle_path, "executable bundle path")
    executable_path = bundle / bundle_path
    reject(executable_path.is_file(), "candidate executable missing")
    reject(executable.get("byteLength") == executable_path.stat().st_size, "candidate executable size")
    reject(executable.get("sha256") == sha256_file(executable_path), "candidate executable hash")
    capability = executable.get("buildInfo", {}).get("candidateCapabilities", {}).get("amiHostCandidate")
    reject(isinstance(capability, dict), "candidate build-info capability")
    reject(capability.get("requestSchema") == REQUEST_SCHEMA, "request capability schema")
    reject(capability.get("resultSchema") == RESULT_SCHEMA, "result capability schema")
    reject(capability.get("platform") == "windows-x86_64", "candidate capability platform")
    reject(capability.get("productionResolvable") is False, "candidate capability promotion")
    closure = document.get("dynamicDependencyClosure")
    reject(isinstance(closure, dict) and closure.get("thirdParty") == [], "third-party dynamic dependency")
    reject(closure.get("status") == "declared_system_only_not_release_authorized", "dependency closure status")
    system = closure.get("system")
    reject(isinstance(system, list) and system and all(isinstance(name, str) and name.endswith(".dll") for name in system), "system closure")
    assets = document.get("externalVendorAssets")
    reject(isinstance(assets, dict) and assets.get("bundlePolicy") == "forbidden", "vendor policy")
    required = assets.get("requiredAtInvocation")
    reject(
        isinstance(required, list)
        and required
        and all(isinstance(item, dict) and item.get("distributionStatus") == "blocked_unknown" for item in required),
        "vendor status",
    )
    vendor_files = [path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file() and path.suffix.lower() in VENDOR_SUFFIXES]
    reject(not vendor_files, f"vendor assets present in candidate bundle: {vendor_files}")
    lock_text = (source_root / "native" / "crates" / "sipi-circuit" / "engine.lock").read_text(encoding="utf-8")
    reject("ami-host-candidate" not in lock_text, "candidate referenced by engine.lock")
    reject(executable["sha256"] not in lock_text, "candidate executable promoted into engine.lock")
    license_evidence = document.get("agentSpiceLicenseEvidence")
    reject(isinstance(license_evidence, dict) and license_evidence.get("distributionStatus") == "authorized_public", "source license evidence")
    reject(all(isinstance(license_evidence.get(key), str) and len(license_evidence[key]) == 64 for key in ("licenseSha256", "classificationSha256")), "license hashes")
    return {
        "accepted": True,
        "manifestSha256": sha256_file(manifest_path),
        "candidateSha256": executable["sha256"],
        "productionResolvable": False,
        "vendorRuntime": "blocked_unknown",
        "reproducibility": document["build"]["reproducibility"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.bundle.resolve(), args.source_root.resolve()), sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"candidate bundle rejected: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
