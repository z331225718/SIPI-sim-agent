"""Run one sanitized original-13 MATLAB or Rust matrix replay.

Inputs must be separately materialized immutable archives. The report never
serializes host paths or external asset bytes.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, secrets, subprocess, sys, tarfile, tempfile, time
from pathlib import Path
from types import SimpleNamespace

METRICS = ("COM_dB", "CTLE_DC_gain_dB", "ERL", "FOM", "ICN_mV", "IL_dB_channel_only_at_Fnq", "Peak_ISI_XTK_and_Noise_interference_at_BER_mV", "VEC_dB", "VEO_mV", "fitted_IL_dB_at_Fnq", "g_DC_HP", "itick")
CONFIG_PATHS = ('matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA _TP0V_08_17_2022.xlsx', 'matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx', 'matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx', 'matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120G_ERL_HOST_10_26_2022.xlsx', 'matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120G_ERL_MODULE_10_26_2022.xlsx', 'matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_162_ERL_HOST_10_26_2022 .xlsx', 'matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_CR_CA_08_17_2022.xlsx', 'matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_KR_08_17_2022.xlsx', 'matlab_src/Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_fr55_C2M_TP1a_11_2022.xlsx', 'matlab_src/Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_C2C_11_2022.xlsx', 'matlab_src/Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_C2M_TP1a_11_2022.xlsx', 'matlab_src/Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_CAKR_11_2022.xlsx', 'matlab_src/Config_spreadsheets_200G_exploratory/config_com_ieee8023_93a=df_200G_PAM4_RCos_Txpre_C2M_TP1a_11_2022.xlsx')
UPSTREAM=("5272ffe74702cd585054d975559b06f8afae7b6e","7094ab6e84989b218730c52432c70da10261f8ea","a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",43694080)
CANDIDATE=("82db91bd7a2c1f6384ed160467934d415f48b9cc","cf617632a793bae9d8be945d4ef7931001c1f341","2137ca349bd7ac1837611494e84a4e6c694521734398abb258bdc1e8d02367ee",56698880)
CHANNELS=(
    ("THRU","fixtures/synthetic/thru_10db_at_26p56ghz.s4p",6393177,"fcbcce086dbae6bbb9a1f8ca5df775073ebb6303f80a9f062caf1f2ab5607361"),
    ("FEXT","fixtures/synthetic/fext_m40db_at_26p56ghz.s4p",6393140,"cc5968bacd5bd40d6ccd7db4927dbb1dd3f20d82f4d3ad5a3193ad86e0e9ca04"),
    ("NEXT","fixtures/synthetic/next_m40db_at_26p56ghz.s4p",6392860,"882819542f43b8fb5f174c7e984b418ceb0f56e068654c9be362a84547b93e65"),
)
MAX_ARCHIVE_MEMBERS=20000
MAX_ARCHIVE_BYTES=256*1024*1024
ADAPTER=("src/agent_com/config/excel.py",12218,"2886e9986b9c3a7c1fbdc6179878679ae26bb92f511c6b0689644f9a6c053c4d","1cce4365b64f3bb0ef1f7617107d2df4c929afc7")
PROJECTION_SOURCES=(("src/agent_com/config/consumption.py",210466,"c6202e42b5e5ccb7fa1f78c780b9ecf031af5400b35cd23f20ef7348207d28a7","50fc02d837a67f3b503a73672ec4fbcc40d39b73"),("src/agent_com/equalization/search.py",53859,"924930c43332f169ce1d66048d3f70610c8bf459af2f0210d6995533c277003d","58f6e5e3f8f36b94faddf0248f3df2ff11e1e3cd"))
SCALAR_BROADCAST_SWEEPS=("CTLE_fp1","CTLE_fp2","CTLE_fz","f_HP","f_HP_P","f_HP_Z")

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def bounded(command,cwd,timeout,env=None):
    try: return subprocess.run(command,cwd=cwd,capture_output=True,timeout=timeout,check=False,env=env)
    except subprocess.TimeoutExpired as error: return SimpleNamespace(returncode=124,stdout=error.stdout or b"",stderr=error.stderr or b"",timed_out=True)
def materialize(archive,destination):
    destination.mkdir(parents=True)
    total=0
    with tarfile.open(archive,"r:*") as tar:
        members=tar.getmembers()
        if len(members)>MAX_ARCHIVE_MEMBERS: raise RuntimeError("archive member budget")
        for member in members:
            name=member.name.replace("\\","/")
            parts=Path(name).parts
            if not name or name.startswith("/") or ".." in parts or not (member.isdir() or member.isfile()): raise RuntimeError("unsafe archive member")
            target=(destination/Path(*parts)).resolve()
            if destination.resolve() not in target.parents and target!=destination.resolve(): raise RuntimeError("archive escape")
            if member.isdir(): target.mkdir(parents=True,exist_ok=True); continue
            total+=member.size
            if total>MAX_ARCHIVE_BYTES: raise RuntimeError("archive byte budget")
            target.parent.mkdir(parents=True,exist_ok=True)
            source=tar.extractfile(member)
            if source is None: raise RuntimeError("archive file missing")
            with source,target.open("xb") as output:
                remaining=member.size
                while remaining:
                    chunk=source.read(min(1024*1024,remaining))
                    if not chunk: raise RuntimeError("short archive member")
                    output.write(chunk);remaining-=len(chunk)
                if source.read(1): raise RuntimeError("long archive member")
def inventory(root):
    result={}
    for path in sorted(root.rglob("*")):
        if path.is_symlink(): raise RuntimeError("source link")
        if path.is_file():
            relative=path.relative_to(root).as_posix(); result[relative]=(path.stat().st_size,digest(path))
    return result
def canonical(value): return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
def normalize(value):
    try:import numpy as np
    except ModuleNotFoundError:np=None
    if np is not None and isinstance(value,np.ndarray):return normalize(value.tolist())
    if np is not None and isinstance(value,(np.integer,np.floating)):value=value.item()
    if isinstance(value,int) and not isinstance(value,bool):value=float(value)
    if isinstance(value,float) and not math.isfinite(value):return {"$special_float":"Infinity" if value>0 else "-Infinity" if value<0 else "NaN"}
    if isinstance(value,dict):return {str(k):normalize(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalize(v) for v in value]
    return value
def first_difference(left,right,path=""):
    if type(left) is not type(right):return path or "$"
    if isinstance(left,dict):
        if set(left)!=set(right):return path or "$"
        for key in sorted(left):
            found=first_difference(left[key],right[key],f"{path}.{key}" if path else key)
            if found:return found
        return None
    if isinstance(left,list):
        if len(left)!=len(right):return path or "$"
        for index,(a,b) in enumerate(zip(left,right)):
            found=first_difference(a,b,f"{path}[{index}]")
            if found:return found
        return None
    return None if left==right else (path or "$")
def runtime_projection(document,parameter_names,option_names):
    projected=normalize({"parameters":{key:document["parameters"][key] for key in sorted(parameter_names)},"options":{key:document["options"][key] for key in sorted(option_names)}})
    for key in SCALAR_BROADCAST_SWEEPS:
        value=projected["parameters"].get(key)
        if value is not None:projected["parameters"][key]=flatten_numeric_sweep(value,key)
    return projected
def flatten_numeric_sweep(value,name):
    if isinstance(value,list):
        result=[]
        for item in value:result.extend(flatten_numeric_sweep(item,name))
        return result
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(f"{name} sweep must contain finite numeric values")
    return [float(value)]
def worker_environment(upstream_root,matlab):
    preference_dir=upstream_root.parent/f"{upstream_root.name}-matlab-pref";preference_dir.mkdir()
    env=os.environ.copy();env["PYTHONDONTWRITEBYTECODE"]="1";env["PYTHONPATH"]=os.pathsep.join((str(upstream_root/"src"),str(matlab.parent.parent/"extern/engines/python/dist")));env["MATLAB_PREFDIR"]=str(preference_dir);env["MW_DISABLE_CONNECTOR"]="1";return env
def engine_worker(spec_path):
    import numpy as np
    from scipy.io import savemat
    import matlab.engine
    from agent_com.config import ComConfig,ComSettings
    from agent_com.config.consumption import _IMPLEMENTED_OPTIONS,_IMPLEMENTED_PARAMETERS
    spec=json.loads(Path(spec_path).read_text(encoding="utf-8")); config=Path(spec["config"]); mat=Path(spec["mat"]); output=Path(spec["output"])
    settings=ComSettings.from_xlsx(config);rows=settings.rows;columns=max(len(row) for row in rows);parameter=np.empty((len(rows),columns),dtype=object);slots=[]
    for row_index,row in enumerate(rows):
        for column_index in range(columns):
            raw=row[column_index].value if column_index<len(row) else None
            if raw is None:value="";kind="blank"
            elif isinstance(raw,(bool,int,float,np.integer,np.floating)):value=float(raw);kind="number"
            elif isinstance(raw,str):value=raw;kind="string"
            else:raise TypeError(f"unsupported workbook cell type: {type(raw).__name__}")
            parameter[row_index,column_index]=value;slots.append({"row":row_index,"column":column_index,"kind":kind,"value":value})
    logical={"shape":[len(rows),columns],"slots":slots};savemat(mat,{"parameter":parameter},do_compression=False,oned_as="row")
    materialized=ComConfig.from_xlsx(config).materialize();raw={"parameters":dict(materialized.parameters),"options":dict(materialized.options)};pinned=runtime_projection(raw,_IMPLEMENTED_PARAMETERS,_IMPLEMENTED_OPTIONS)
    engine=matlab.engine.start_matlab("-noFigureWindows -singleCompThread")
    try:
        engine.cd(str(output.parent),nargout=0)
        engine.addpath(str(Path(spec["upstream"])/"tools/matlab_oracle"),nargout=0)
        engine.run_com_oracle(spec["upstream"],str(mat),str(output),float(26560000000),float(1),float(1),*spec["channels"],nargout=0)
    finally:engine.quit()
    result={"parameter_shape":logical["shape"],"parameter_slot_digest":hashlib.sha256(canonical(logical)).hexdigest(),"parameter_mat_bytes":mat.stat().st_size,"parameter_mat_sha256":digest(mat),"projection_parameters":sorted(_IMPLEMENTED_PARAMETERS),"projection_options":sorted(_IMPLEMENTED_OPTIONS),"pinned_materialized":pinned,"pinned_materialized_sha256":hashlib.sha256(canonical(pinned)).hexdigest()}
    Path(spec["worker_result"]).write_text(json.dumps(result,sort_keys=True),encoding="utf-8")
def tool_receipt(path,role):
    if not path.is_file(): raise RuntimeError("tool missing")
    run=bounded([str(path),"--version" if role in ("python","uv") else "-Vv"],path.parent,30)
    if run.returncode: raise RuntimeError("tool version failed")
    return {"role":role,"executable":path.name,"file_sha256":digest(path),"version_sha256":hashlib.sha256(run.stdout+run.stderr).hexdigest(),"path_redacted":True}
def matlab_receipt(path,python):
    if not path.is_file(): raise RuntimeError("MATLAB missing")
    with tempfile.TemporaryDirectory(prefix="sipi-matlab-pref-") as preference_dir:
        env=os.environ.copy();env["PYTHONPATH"]=str(path.parent.parent/"extern/engines/python/dist");env["MATLAB_PREFDIR"]=preference_dir;env["MW_DISABLE_CONNECTOR"]="1"
        script="import matlab.engine;e=matlab.engine.start_matlab('-noFigureWindows -singleCompThread');print(e.version());e.quit()"
        run=bounded([str(python),"-c",script],path.parent,120,env)
    if run.returncode: raise RuntimeError("MATLAB identity failed")
    return {"role":"matlab","executable":path.name,"file_sha256":digest(path),"version_sha256":hashlib.sha256(run.stdout+run.stderr).hexdigest(),"path_redacted":True,"release":"R2026a"}
def configs(root):
    paths=[root/path for path in CONFIG_PATHS]
    if any(not path.is_file() for path in paths): raise RuntimeError("exact workbook corpus missing")
    return paths
def channels(root): return [(role,root/"fixtures/synthetic"/name) for role,name in (("THRU","thru_10db_at_26p56ghz.s4p"),("FEXT","fext_m40db_at_26p56ghz.s4p"),("NEXT","next_m40db_at_26p56ghz.s4p"))]
def decode(value):
    if isinstance(value,dict) and value.get("kind")=="finite": return value.get("value")
    if isinstance(value,dict) and value.get("kind") in ("inf","-inf","nan"): return {"inf":"+Inf","-inf":"-Inf","nan":"NaN"}[value["kind"]]
    if isinstance(value,str) and value.lower() in ("inf","+inf","infinity","+infinity"): return "+Inf"
    if isinstance(value,str) and value.lower() in ("-inf","-infinity"): return "-Inf"
    return value
def matlab_metrics(case_dir):
    summary=json.loads((case_dir/"summary.json").read_text(encoding="utf-8")); source=summary.get("case_metrics",[]); source=source if isinstance(source,list) else [source]
    return [{name:decode(value) for name,value in item.get("output_metrics",{}).items() if name in METRICS} for item in source]
def rust_metrics(result): return [{name:decode(value) for name,value in item.get("metrics",{}).items() if name in METRICS} for item in result.get("cases",[])]
def matlab_string(path): return str(Path(path).resolve()).replace("'", "''")
def main():
    p=argparse.ArgumentParser();p.add_argument("--engine",choices=("matlab","rust"),required=True);p.add_argument("--upstream-archive",type=Path,required=True);p.add_argument("--candidate-archive",type=Path,required=True);p.add_argument("--output-root",type=Path,required=True);p.add_argument("--report",type=Path,required=True);p.add_argument("--cargo",type=Path,required=True);p.add_argument("--rustc",type=Path,required=True);p.add_argument("--uv",type=Path,required=True);p.add_argument("--matlab",type=Path,required=True);p.add_argument("--python",type=Path,required=True);p.add_argument("--only");p.add_argument("--timeout",type=int,default=1800);a=p.parse_args()
    if a.report.exists(): raise FileExistsError(a.report)
    for archive,identity in ((a.upstream_archive,UPSTREAM),(a.candidate_archive,CANDIDATE)):
        if not archive.is_file() or archive.stat().st_size!=identity[3] or digest(archive)!=identity[2]: raise RuntimeError("archive identity drift")
    toolchain={"cargo":tool_receipt(a.cargo,"cargo"),"rustc":tool_receipt(a.rustc,"rustc"),"uv":tool_receipt(a.uv,"uv"),"matlab":matlab_receipt(a.matlab,a.python),"python":tool_receipt(a.python,"python")}
    toolchain["matlab"]["launch_mode"]="python_engine_noFigureWindows_singleCompThread"
    nonce=secrets.token_hex(32); run_id=f"original13-{a.engine}-{nonce}"; root=a.output_root/"run";root.mkdir(parents=True)
    candidate_root=root/"candidate-source";materialize(a.candidate_archive,candidate_root)
    candidate_before=inventory(candidate_root);target=root/"candidate-target"
    env=os.environ.copy();env["CARGO_TARGET_DIR"]=str(target);env["RUSTC"]=str(a.rustc);env.pop("RUSTC_WRAPPER",None);env.pop("RUSTC_WORKSPACE_WRAPPER",None)
    build=bounded([str(a.cargo),"build","--release","--locked","--manifest-path",str(candidate_root/"crates/sipi-agent-com-direct/Cargo.toml"),"--bin","sipi-com-direct-run","--bin","sipi-com-direct-config-validate"],candidate_root,1800,env)
    if build.returncode: raise RuntimeError("candidate archive build failed: "+build.stderr[-2000:].decode("utf-8","replace"))
    if inventory(candidate_root)!=candidate_before: raise RuntimeError("candidate archive build drifted")
    rust_binary=target/"release/sipi-com-direct-run.exe"
    rust_config=target/"release/sipi-com-direct-config-validate.exe"
    if not rust_binary.is_file() or not rust_config.is_file(): raise RuntimeError("candidate binary missing")
    probe=root/"upstream-probe";materialize(a.upstream_archive,probe)
    python_env=root/"python-env";uv_env=os.environ.copy();uv_env["UV_PROJECT_ENVIRONMENT"]=str(python_env)
    sync=bounded([str(a.uv),"sync","--frozen","--offline","--no-install-project","--python",str(a.python)],probe,300,uv_env)
    worker_python=python_env/"Scripts/python.exe"
    if sync.returncode or not worker_python.is_file():raise RuntimeError("pinned Python environment failed")
    all_configs=configs(probe);selected_indices=[i for i,x in enumerate(all_configs) if not a.only or a.only.casefold() in x.name.casefold()]
    if not selected_indices: raise RuntimeError("empty selection")
    expected_channels=[{"role":role,"path":path,"bytes":size,"sha256":sha} for role,path,size,sha in CHANNELS]
    for item in expected_channels:
        path=probe/item["path"]
        if path.stat().st_size!=item["bytes"] or digest(path)!=item["sha256"]: raise RuntimeError("archived channel identity drift")
    adapter_path=probe/ADAPTER[0]
    if adapter_path.stat().st_size!=ADAPTER[1] or digest(adapter_path)!=ADAPTER[2]:raise RuntimeError("adapter source drift")
    for path,size,sha,_blob in PROJECTION_SOURCES:
        source=probe/path
        if source.stat().st_size!=size or digest(source)!=sha:raise RuntimeError("projection source drift")
    records=[]; started=time.time()
    for ordinal,index in enumerate(selected_indices):
        case_root=root/f"case-{ordinal:02d}";case_root.mkdir(); upstream_root=case_root/"upstream-source";materialize(a.upstream_archive,upstream_root)
        config=configs(upstream_root)[index]; rel=CONFIG_PATHS[index]; chan=channels(upstream_root); source_before=inventory(upstream_root)
        if a.engine=="rust":
            out=case_root/"rust"; cmd=[str(rust_binary),"run","--config",str(config),"--thru",str(chan[0][1]),"--fext",str(chan[1][1]),"--next",str(chan[2][1]),"--output-dir",str(out)]
            run=bounded(cmd,upstream_root,a.timeout); result_path=out/"result.json"; metrics=rust_metrics(json.loads(result_path.read_text())) if run.returncode==0 and result_path.is_file() else []
            status="passed" if run.returncode==0 else ("candidate_timeout" if getattr(run,"timed_out",False) else "candidate_branch_missing"); detail_sha=hashlib.sha256(run.stderr).hexdigest()
            config_materialization={"comparison":"not_run_for_rust_result_replay"}
        else:
            out=case_root/"matlab";out.mkdir();spec_path=case_root/"engine-spec.json";worker_result=case_root/"engine-result.json";mat=case_root/"parameter.mat"
            spec={"upstream":str(upstream_root),"config":str(config),"mat":str(mat),"output":str(out),"channels":[str(x[1]) for x in chan],"worker_result":str(worker_result)};spec_path.write_text(json.dumps(spec),encoding="utf-8")
            worker_env=worker_environment(upstream_root,a.matlab)
            run=bounded([str(worker_python),str(Path(__file__).resolve()),"--engine-worker",str(spec_path)],case_root,a.timeout,worker_env); metrics=matlab_metrics(out) if run.returncode==0 and (out/"summary.json").is_file() and worker_result.is_file() else []
            status="passed" if run.returncode==0 and metrics else "matlab_failed"; detail_sha=hashlib.sha256(run.stdout+run.stderr).hexdigest()
            config_materialization={"comparison":"worker_failed"}
            if worker_result.is_file():
                worker=json.loads(worker_result.read_text(encoding="utf-8"));rust_run=bounded([str(rust_config),"config","validate",str(config),"--materialized-json"],upstream_root,120)
                if rust_run.returncode:raise RuntimeError("Rust config materialization failed")
                rust_document=json.loads(rust_run.stdout);rust_materialized=runtime_projection(rust_document["materialized"],worker["projection_parameters"],worker["projection_options"]);rust_sha=hashlib.sha256(canonical(rust_materialized)).hexdigest();equal=rust_sha==worker["pinned_materialized_sha256"]
                config_materialization={"comparison":"equal" if equal else "drift","first_difference":first_difference(worker["pinned_materialized"],rust_materialized),"pinned_sha256":worker["pinned_materialized_sha256"],"rust_sha256":rust_sha,"parameter_shape":worker["parameter_shape"],"parameter_slot_digest":worker["parameter_slot_digest"],"parameter_mat_bytes":worker["parameter_mat_bytes"],"parameter_mat_sha256":worker["parameter_mat_sha256"]}
                if not equal:status="config_materialization_drift"
        source_unchanged=inventory(upstream_root)==source_before
        if not source_unchanged: status="source_inventory_drift"
        records.append({"workbook_index":index,"workbook":{"path":rel,"bytes":source_before[rel][0],"sha256":source_before[rel][1]},"status":status,"exit_code":run.returncode,"detail_sha256":detail_sha,"source_inventory_unchanged":source_unchanged,"config_materialization":config_materialization,"case_count":len(metrics),"metrics":metrics})
    binary={"path":"target/release/sipi-com-direct-run.exe","bytes":rust_binary.stat().st_size,"sha256":digest(rust_binary)}
    payload={"schema":"sipi.p5-06.original13-fresh-run.v1","engine":a.engine,"run_id":run_id,"nonce":nonce,"status":"diagnostic" if len(selected_indices)!=13 else "fresh_matrix_run","duration_seconds":time.time()-started,"selection_count":len(selected_indices),"source":{"upstream":{"commit":UPSTREAM[0],"tree":UPSTREAM[1],"archive_sha256":UPSTREAM[2],"archive_bytes":UPSTREAM[3]},"candidate":{"commit":CANDIDATE[0],"tree":CANDIDATE[1],"archive_sha256":CANDIDATE[2],"archive_bytes":CANDIDATE[3]},"adapter":{"path":ADAPTER[0],"bytes":ADAPTER[1],"sha256":ADAPTER[2],"git_blob":ADAPTER[3]},"projection_sources":[{"path":p,"bytes":b,"sha256":s,"git_blob":g} for p,b,s,g in PROJECTION_SOURCES],"rust_binary":binary,"toolchain":toolchain},"channels":expected_channels,"records":records,"claims":{"acceptance":False,"historical_python_used":False,"s_parameter_fit":False,"one_final_fd_to_td_impulse":True}}
    a.report.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n");print(json.dumps({"run_id":run_id,"report_sha256":digest(a.report),"statuses":[x["status"] for x in records]}))
if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--engine-worker":engine_worker(sys.argv[2])
    else:main()
