"""Fail closed on P4B-05c static PE loader-declaration evidence."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/p4b-dual-ami-pe-loader-declarations.v1.yaml"
P4B05B = ROOT / "docs/baselines/p4b-ads-pcie-gen5-dual-ami-asset-preflight.v1.yaml"
SCHEMA = "sipi.p4b-dual-ami-pe-loader-declarations.v1"
P4B05B_SHA256 = "7e9281833b13a38be8d523619afc5f4e163e330a314325e8ff3ea4f3faa13dcd"
REPORT_SHA256 = "d748193ab62a2f91f1ab6c14f8697658209210b0c5a15052d777554254aa9df4"
CANONICAL_SHA256 = "330874cb653d6d472dd279794e55d1e48df5bf115e0a7287985a2220d06979a5"

class GateError(RuntimeError): pass
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def exact(value: object, expected: object, reason: str) -> None:
    if value != expected: raise GateError(reason)
def tracked_hashes(root: Path) -> set[str]:
    import subprocess
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], check=True, capture_output=True).stdout
    return {hashlib.sha256((root / item.decode("utf-8")).read_bytes()).hexdigest() for item in out.split(b"\0") if item}

def verify(document: object, *, root: Path = ROOT, hashes: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA or document.get("status") != "external_only_static_loader_declarations_observed_dynamic_runtime_closure_and_worker_admission_blocked": raise GateError("schema_or_status_invalid")
    exact(document.get("authority"), {"actor": "user", "decision_ref": "user-approved-2026-08-12-p4b-static-loader-declarations", "scope": "external_oracle_candidate_static_pe_declarations_only"}, "authority_invalid")
    exact(document.get("binding"), {"p4b05b_baseline_sha256": P4B05B_SHA256, "external_report_sha256": REPORT_SHA256, "canonical_payload_sha256": CANONICAL_SHA256, "custody": "external_only", "report_path_retained": False, "fresh_materializations": 2}, "binding_invalid")
    if sha(root / P4B05B.relative_to(ROOT)) != P4B05B_SHA256: raise GateError("p4b05b_source_drift")
    expected = {
      "pcie-tx-dll": {"byte_length":370045,"sha256":"05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea","machine":"windows-x86_64","is_dll":True,"normal_import_modules":["kernel32.dll","msvcrt.dll","user32.dll"],"normal_import_symbol_count":120,"normal_import_symbol_manifest_sha256":"469f3d78f21a24f7788f925f01ce0e8778ccf9e70567442aacf751ea1690c040","delay_imports":[],"bound_imports":[],"export_forwarders":[],"embedded_manifests":[],"tls_directory":"present","clr_directory":"absent","dynamic_loader_capability_indicators":[]},
      "pcie-rx-dll": {"byte_length":8850494,"sha256":"88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63","machine":"windows-x86_64","is_dll":True,"normal_import_modules":["kernel32.dll","msvcrt.dll","user32.dll"],"normal_import_symbol_count":126,"normal_import_symbol_manifest_sha256":"1009c13ac574a286de77d1d5685f312be86f239d81633eddc2d0ab2f4dfe74ab","delay_imports":[],"bound_imports":[],"export_forwarders":[],"embedded_manifests":[],"tls_directory":"present","clr_directory":"absent","dynamic_loader_capability_indicators":[]}}
    exact(document.get("dlls"), expected, "dll_static_declaration_drift")
    exact(document.get("gates"), {"dynamic_dependency_closure":"blocked_not_assessed","worker_admission":"blocked_unverified_rights_and_runtime_closure","p4b_ami_runtime_invoked":False,"product_runtime_invoked":False,"release_ledger_promoted":False}, "gate_promotion")
    exact(document.get("non_claims"), ["Static declarations do not establish complete static or dynamic dependency closure.","No DLL load, ADS invocation, AMI worker, or GetWave action occurred.","No sidecar file is admitted by this observation.","Not rights, packaging, release, default-route, compatibility, composition, or parity evidence."], "non_claims_invalid")
    source = (root / "tools/observe_p4b_dual_ami_pe_loader_declarations.py").read_text(encoding="utf-8")
    if any(token not in source for token in ("private_copy", "fresh_observation_source_drift", "bound_imports", "embedded_manifests", "dynamic_loader_capability_indicators", "ctypes", "not_worker_admission_or_dll_load")): raise GateError("observer_binding_drift")
    if "import ctypes" in source or "\nimport subprocess" in source or "\nfrom subprocess" in source: raise GateError("observer_load_surface_detected")
    actual = tracked_hashes(root) if hashes is None else hashes
    if actual & {REPORT_SHA256, CANONICAL_SHA256, *(row["sha256"] for row in expected.values())}: raise GateError("external_asset_or_report_leak")
    return {"schema": SCHEMA, "status": document["status"], "worker_admitted": False, "runtime_invoked": False, "dynamic_closure": "blocked_not_assessed"}

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--record", type=Path, default=DEFAULT); args=parser.parse_args(argv)
    try: result=verify(yaml.safe_load(args.record.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError, GateError) as error: print(json.dumps({"schema":SCHEMA,"status":"rejected","reason":str(error)},sort_keys=True)); return 2
    print(json.dumps(result,sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
