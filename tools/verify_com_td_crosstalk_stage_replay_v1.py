"""Fail-closed COM TDMODE replay verifier."""
from __future__ import annotations
import hashlib,json,math,re
from pathlib import Path
from typing import Any
from com_erl_exact_profile_replay_v3_support import path_free
SCHEMA="sipi.com.td-crosstalk-stage-replay.v1"
MANIFEST=Path("docs/baselines/com-td-crosstalk-stage-replay-v1.manifest.json")
class VerificationError(ValueError): pass
def digest(v:bytes)->str:return hashlib.sha256(v).hexdigest()
def check(v:Any)->None:
    if not isinstance(v,str) or not re.fullmatch(r"[0-9a-f]{64}",v):raise VerificationError("sha256")
EXPECTED_FIXTURES=["fixtures/synthetic/td_thru_pulse.csv","fixtures/synthetic/td_fext_pulse.csv","fixtures/synthetic/td_next_pulse.csv"]
def verify_manifest(m:dict[str,Any], require_outputs:bool=True)->None:
    if m.get("schema")!=SCHEMA:raise VerificationError("manifest schema")
    for side in ("candidate","upstream"):
        x=m.get(side,{})
        if not re.fullmatch(r"[0-9a-f]{40}",x.get("commit","")) or not re.fullmatch(r"[0-9a-f]{40}",x.get("tree","")):raise VerificationError("source")
        check(x.get("archive_sha256"))
    if m.get("f2_values_hz")!=[50000000000.0,13000000000.0] or m.get("stage")!={"short_count":8,"full_count":64} or m.get("fixture_paths")!=EXPECTED_FIXTURES or set(m.get("fixture_sha256",{}))!=set(EXPECTED_FIXTURES):raise VerificationError("controls/fixtures")
    for fixture_sha in m["fixture_sha256"].values():check(fixture_sha)
    if m.get("run_ids")!=["com-td-crosstalk-stage-v1-run1","com-td-crosstalk-stage-v1-run2"]:raise VerificationError("run order")
    if set(m.get("candidate",{}))!={"commit","tree","archive_sha256"} or set(m.get("upstream",{}))!={"commit","tree","archive_sha256"}:raise VerificationError("source key set")
    if set(m.get("runner",{}))!={"path","sha256"} or set(m.get("helper",{}))!={"path","sha256"} or set(m.get("pe_helper",{}))!={"path","sha256"}:raise VerificationError("harness key set")
    if set(m.get("tools",{}))!={"verifier","aggregator","tests"}:raise VerificationError("tool key set")
    for x in [m.get("runner",{}),m.get("helper",{}),m.get("pe_helper",{}),*m.get("tools",{}).values()]:
        if not isinstance(x,dict) or not x.get("path") or Path(x["path"]).is_absolute() or ".." in Path(x["path"]).parts:raise VerificationError("tool path")
        check(x.get("sha256"))
        tool_path=Path(x["path"])
        if not tool_path.is_file() or digest(tool_path.read_bytes())!=x["sha256"]:raise VerificationError("tool file binding")
    if m.get("mode")=="prep":
        if set(m)!={"schema","mode","candidate","upstream","f2_values_hz","stage","run_ids","runner","helper","pe_helper","tools","fixture_paths","fixture_sha256","harness"}:raise VerificationError("prep key set")
        forbidden={"reports","report_sha256","aggregate","audit"}
        if forbidden & set(m):raise VerificationError("prep formal fields")
        h=m.get("harness",{}); p=Path(h.get("path",""))
        if not h or p.is_absolute() or ".." in p.parts or not p.is_file():raise VerificationError("prep harness path")
        if digest(p.read_bytes())!=h.get("sha256"):raise VerificationError("prep harness sha")
        return
    if set(m)!={"schema","candidate","upstream","f2_values_hz","stage","run_ids","runner","helper","pe_helper","tools","fixture_paths","fixture_sha256","reports","report_sha256","aggregate","audit"}:raise VerificationError("formal key set")
    if len(m.get("reports",[]))!=2 or any(Path(x).is_absolute() or ".." in Path(x).parts for x in m["reports"]):raise VerificationError("reports")
    for p in m["reports"]:check(m.get("report_sha256",{}).get(p))
    if Path(m.get("aggregate",{}).get("path","/")).is_absolute() or ".." in Path(m.get("aggregate",{}).get("path","")).parts:raise VerificationError("aggregate path")
    check(m.get("aggregate",{}).get("sha256"))
    aggregate_path=Path(m["aggregate"]["path"])
    if require_outputs and (not aggregate_path.is_file() or digest(aggregate_path.read_bytes())!=m["aggregate"]["sha256"]):raise VerificationError("aggregate file binding")
    if Path(m.get("audit",{}).get("path","/")).is_absolute() or ".." in Path(m.get("audit",{}).get("path","")).parts:raise VerificationError("audit path")
    check(m.get("audit",{}).get("sha256"))
    audit_path=Path(m["audit"]["path"])
    if require_outputs and (not audit_path.is_file() or digest(audit_path.read_bytes())!=m["audit"]["sha256"]):raise VerificationError("audit file binding")
def identity(x:Any)->None:
    if not isinstance(x,dict) or x.get("path_redacted") is not True or x.get("status")!="ok" or x.get("version_exit")!=0:raise VerificationError("tool identity")
    for key in ("basename","file_sha256","version_output_sha256"):
        if not x.get(key):raise VerificationError("tool identity field")
        if key!="basename":check(x[key])
def verify_report(r:dict[str,Any],m:dict[str,Any])->None:
    verify_manifest(m, require_outputs=False)
    if set(r)!={"schema","run_id","fresh_run_nonce","status","path_policy","candidate","upstream","input","stages","stage_observation","upstream_output","candidate_output","parity","toolchain","execution","non_claims"}:raise VerificationError("report key set")
    if r.get("schema")!=SCHEMA or not re.fullmatch(r"com-td-crosstalk-stage-v1-run[12]",r.get("run_id","")) or not re.fullmatch(r"[0-9a-f]{64}",r.get("fresh_run_nonce","")):raise VerificationError("schema/run")
    if not path_free(r) or r.get("path_policy",{}).get("absolute_paths_emitted") is not False:raise VerificationError("path")
    if r.get("upstream",{}).get("oracle_role")!="pinned_agent_com_pure_leaf" or r.get("upstream",{}).get("oracle")!="agent_com.equalization.search._td_source_crosstalk_noise" or r.get("candidate",{}).get("oracle"):raise VerificationError("oracle binding")
    for side in ("candidate","upstream"):
        if any(r.get(side,{}).get(k)!=m[side][k] for k in ("commit","tree","archive_sha256")):raise VerificationError("source binding")
        if r[side].get("materialization")!="git archive; no working-tree overlay":raise VerificationError("archive boundary")
    if r["candidate"]["commit"]==r["upstream"]["commit"] or r["candidate"]["tree"]==r["upstream"]["tree"]:raise VerificationError("self compare")
    check(r.get("candidate",{}).get("binary_sha256"))
    custody=r.get("candidate",{}).get("binary_custody",{})
    if custody.get("raw_sha256")!=r["candidate"]["binary_sha256"] or custody.get("schema")!="sipi.windows-pe-replay-custody.v1" or custody.get("canonical_helper")!=m["pe_helper"]:raise VerificationError("PE custody")
    check(custody.get("canonical_sha256"))
    inv=r.get("candidate",{}).get("source_inventory",{})
    if not isinstance(inv.get("count"),int) or inv["count"]<=0:raise VerificationError("inventory")
    check(inv.get("combined_sha256"))
    inp=r.get("input",{})
    if inp.get("fixture_paths")!=m["fixture_paths"] or inp.get("independent_read_only") is not True or inp.get("channel_policy")!="TD pulse-derived; no S-parameter fit" or inp.get("fixture_source_archive_sha256")!=m["upstream"]["archive_sha256"] or inp.get("fixture_sha256")!=m.get("fixture_sha256",inp.get("fixture_sha256")):raise VerificationError("fixture policy")
    for fixture_sha in inp.get("fixture_sha256",{}).values():check(fixture_sha)
    for f2 in m["f2_values_hz"]:
        pair=inp.get("f2_copy_sha256",{}).get(str(f2),{})
        if pair.get("candidate")!=pair.get("upstream"):raise VerificationError("fixture custody")
        check(pair.get("candidate"))
    s=r.get("stages",{});o=s.get("outer_product",{})
    if s.get("short_response",{}).get("count")!=8 or s.get("full_noise_axis",{}).get("count")!=64 or o.get("rows")*o.get("columns")!=o.get("elements") or o.get("order")!="column-major-linear":raise VerificationError("stage")
    for x in (s.get("short_response",{}).get("sha256"),s.get("full_noise_axis",{}).get("sha256"),o.get("role_sum",{}).get("FEXT"),o.get("role_sum",{}).get("NEXT")):check(x)
    up,ca=r.get("upstream_output",{}),r.get("candidate_output",{})
    if set(up)!=set(ca) or set(up)!={str(x) for x in m["f2_values_hz"]}:raise VerificationError("outputs")
    if any(not math.isfinite(float(up[k]["noise"])) or not math.isfinite(float(ca[k])) for k in up):raise VerificationError("nonfinite")
    if any(not math.isclose(float(up[k]["noise"]),float(ca[k]),rel_tol=1e-12,abs_tol=1e-12) for k in up):raise VerificationError("numeric")
    policy=r.get("parity",{}).get("numeric_policy",{})
    if policy!={"f2_values_hz":[50000000000.0,13000000000.0],"atol":1e-12,"rtol":1e-12}:raise VerificationError("numeric policy")
    if r.get("parity",{}).get("differences") or r.get("parity",{}).get("matched") is not True or r.get("status")!="matched":raise VerificationError("parity")
    e=r.get("execution",{})
    if e.get("runner")!=m["runner"] or e.get("helper")!=m["helper"] or e.get("pe_helper")!=m["pe_helper"] or e.get("wrappers")!={"RUSTC_WRAPPER":"","RUSTC_WORKSPACE_WRAPPER":"","CARGO_BUILD_RUSTC_WRAPPER":""}:raise VerificationError("execution")
    if set(r.get("toolchain",{}))!={"git","cargo","rustc","linker","python","numpy","uv"}:raise VerificationError("tool roles")
    for role in ("git","cargo","rustc","linker","python","numpy","uv"):
        identity(r.get("toolchain",{}).get(role)); x=r["toolchain"][role]
        if x.get("role",role)!=role or not isinstance(x.get("version_exit",0),int):raise VerificationError("tool role/exit")
    numpy=r["toolchain"]["numpy"]
    if not numpy.get("core_basename") or not re.fullmatch(r"[0-9a-f]{64}",numpy.get("core_binary_sha256","")):raise VerificationError("numpy core")
    for output in r.get("upstream_output",{}).values():
        if output.get("numpy_version") is None or digest(output["numpy_version"].encode())!=output.get("numpy_version_sha256") or output.get("numpy_version_sha256")!=numpy.get("version_output_sha256") or output.get("numpy_module_sha256")!=numpy.get("file_sha256") or output.get("numpy_core_sha256")!=numpy.get("core_binary_sha256") or output.get("numpy_core_basename")!=numpy.get("core_basename"):raise VerificationError("numpy cross binding")
    e=r.get("execution",{})
    if e.get("upstream_runtime","").split()[:3]!=["uv","run","--frozen"] or e.get("uv_actual_execution") is not True:raise VerificationError("uv execution")
    be=e.get("build_environment",{})
    if set(be)!={"RUSTC","CARGO_BUILD_RUSTC","LINKER","RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS","LIB","INCLUDE","PATH"} or be["RUSTFLAGS"]!="" or be["CARGO_ENCODED_RUSTFLAGS"]!="":raise VerificationError("build env")
    if be["RUSTC"].get("sha256")!=r["toolchain"]["rustc"]["file_sha256"] or be["CARGO_BUILD_RUSTC"].get("sha256")!=r["toolchain"]["rustc"]["file_sha256"] or be["LINKER"].get("sha256")!=r["toolchain"]["linker"]["file_sha256"]:raise VerificationError("compiler env binding")
    for key in ("LIB","INCLUDE"): 
        if set(be[key])!={"count","combined_sha256"} or not isinstance(be[key]["count"],int):raise VerificationError("directory inventory")
        check(be[key]["combined_sha256"])
    if set(be["PATH"])!={"inventory","tool_basenames"} or be["PATH"]["tool_basenames"]!=[r["toolchain"][x]["basename"] for x in ("cargo","rustc","linker")]:raise VerificationError("path binding")
    if set(be["PATH"]["inventory"])!={"count","combined_sha256"}:raise VerificationError("path inventory")
    check(be["PATH"]["inventory"]["combined_sha256"])
def verify_report_file(p:Path,m:dict[str,Any])->dict[str,Any]:
    if p.as_posix() not in m["reports"] or digest(p.read_bytes())!=m["report_sha256"][p.as_posix()]:raise VerificationError("report path/hash")
    r=json.loads(p.read_text(encoding="utf-8"));
    if r.get("run_id")!=m["run_ids"][m["reports"].index(p.as_posix())]:raise VerificationError("report slot/run")
    verify_report(r,m);return r
verify_report_path = verify_report_file
def verify_reports_for_aggregation(paths:list[Path],m:dict[str,Any])->list[dict[str,Any]]:
    verify_manifest(m, require_outputs=False)
    if [p.as_posix() for p in paths]!=m["reports"]:raise VerificationError("report slots")
    return [verify_report_file(p,m) for p in paths]
def aggregate_hash(a:dict[str,Any])->str:return digest(json.dumps({k:v for k,v in a.items() if k!="aggregate_sha256"},sort_keys=True,separators=(",",":")).encode())
def verify_aggregate(a:dict[str,Any],paths:list[Path],reports:list[dict[str,Any]],m:dict[str,Any],ap:Path)->None:
    verify_manifest(m)
    if m.get("mode")=="prep":raise VerificationError("aggregate unavailable in prep")
    if set(a)!={"schema","status","matched","report_sha256","run_ids","candidate","upstream","aggregate_sha256"}:raise VerificationError("aggregate key set")
    if a.get("schema")!=SCHEMA+".aggregate" or a.get("status")!="matched" or a.get("matched") is not True or [p.as_posix() for p in paths]!=m["reports"] or any(p.is_absolute() or ".." in p.parts for p in paths) or a.get("run_ids")!=m["run_ids"]:raise VerificationError("aggregate")
    for side in ("candidate","upstream"):
        if a.get(side)!={k:m[side][k] for k in ("commit","tree","archive_sha256")}:raise VerificationError("aggregate source")
    if a.get("report_sha256")!=[m["report_sha256"][p] for p in m["reports"]] or len({r["fresh_run_nonce"] for r in reports})!=2:raise VerificationError("aggregate custody")
    if any(reports[i]["candidate"][k]!=reports[0]["candidate"][k] for i in (1,) for k in ("commit","tree","archive_sha256","source_inventory")) or reports[0]["upstream"]!=reports[1]["upstream"] or reports[0]["toolchain"]!=reports[1]["toolchain"] or reports[0]["execution"].get("build_environment")!=reports[1]["execution"].get("build_environment"):raise VerificationError("cross-run identity")
    if reports[0]["candidate"]["binary_custody"]["canonical_sha256"]!=reports[1]["candidate"]["binary_custody"]["canonical_sha256"]:raise VerificationError("PE canonical drift")
    for p in paths:verify_report_file(p,m)
    if ap.as_posix()!=m["aggregate"]["path"] or a.get("aggregate_sha256")!=aggregate_hash(a) or digest(ap.read_bytes())!=m["aggregate"]["sha256"]:raise VerificationError("aggregate hash")
def main()->int:
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--manifest",type=Path,required=True);p.add_argument("--aggregate",type=Path);a=p.parse_args();m=json.loads(a.manifest.read_text(encoding="utf-8"));verify_manifest(m);paths=[Path(x) for x in m["reports"]];reports=[verify_report_file(x,m) for x in paths]
    if a.aggregate:verify_aggregate(json.loads(a.aggregate.read_text(encoding="utf-8")),paths,reports,m,a.aggregate)
    print(json.dumps({"verified":len(reports),"aggregate":bool(a.aggregate)},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
