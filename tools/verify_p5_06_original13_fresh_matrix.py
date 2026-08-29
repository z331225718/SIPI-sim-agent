"""Strict schema verifier for pre-formal original-13 replay reports."""
import json,math,re
from pathlib import Path
try: from .run_p5_06_original13_fresh_matrix import ADAPTER, CANDIDATE, CHANNELS, CONFIG_PATHS, METRICS, PROJECTION_SOURCES, UPSTREAM
except ImportError: from run_p5_06_original13_fresh_matrix import ADAPTER, CANDIDATE, CHANNELS, CONFIG_PATHS, METRICS, PROJECTION_SOURCES, UPSTREAM
HEX=re.compile(r"^[0-9a-f]{64}$")
WORKBOOKS=dict(zip(CONFIG_PATHS,((67151,"54562fa2bbe856f1fb6e96b7c1c873d2b399555b1fb38e50cd6f4ad3ddc69f0a"),(67087,"e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925"),(63311,"f2c4c92f9549e720fff2843df6dc861aca7a503d59b2208898c2b67fa6fc0fc9"),(67009,"3c95f728ba03442ac11b4b3834c0ee426a8a5b41eef6f7acd8390dc4b813c8c2"),(67208,"bebc7cbb9701fcbd6b6645e0a5d9b68a8ee05ded305dfde2720042ce3823df0b"),(67022,"7512e0dba337e881a4b27db9e3f8119e1642e6f29db0b69b4f188c17ccc8b66d"),(67030,"06a62ad17fcaf51fffb2060e9d37e7192cd0fd5a95cf5920b0aba46786ad4b53"),(67620,"8247d4c950009293187b82999e780c5aa4bca1c21c448fd1b5557fd185b5e989"),(45881,"17cda9b0fa4aed850b9534631d4fe7f65950517392edc19407b1668dba8c2482"),(45859,"b259c3c647bbb5d1fd136703d8d47e2e818a2ce70aa965fc9819013954ac3548"),(45883,"4b9a7157652bdbfd2df199f2424d6ec8e0f257ebb49b51d728eb10d1b0377b06"),(45800,"49983d6cae96220b983bdc0b47ac5994bb3c7aac097798b94e18f327e97b2cd9"),(45894,"15b2b454d0c8a305628e04b579b47cedcdb315ff57981c6e2284c57d15c0ce5f"))))
class Error(RuntimeError):pass
def finite(v):
    if isinstance(v,float) and not math.isfinite(v):raise Error("nonfinite JSON")
    if isinstance(v,dict):
        for x in v.values():finite(x)
    elif isinstance(v,list):
        for x in v:finite(x)
def no_abs(v):
    if isinstance(v,str) and (v.startswith(("/","\\")) or re.match(r"^[A-Za-z]:[\\/]",v)):raise Error("absolute path")
    if isinstance(v,dict):
        for x in v.values():no_abs(x)
    elif isinstance(v,list):
        for x in v:no_abs(x)
def verify(report):
    finite(report);no_abs(report)
    keys={"schema","engine","run_id","nonce","status","duration_seconds","selection_count","source","channels","records","claims"}
    if set(report)!=keys or report["schema"]!="sipi.p5-06.original13-fresh-run.v1" or report["engine"] not in ("matlab","rust"):raise Error("envelope")
    if not HEX.fullmatch(report["nonce"]) or not report["run_id"].endswith(report["nonce"]):raise Error("identity")
    expected_channels=CHANNELS
    if report["channels"] != [{"role":r,"path":p,"bytes":b,"sha256":s} for r,p,b,s in expected_channels]:raise Error("roles/assets")
    source=report["source"]
    if set(source)!={"upstream","candidate","adapter","projection_sources","rust_binary","toolchain"} or source["upstream"]!={"commit":UPSTREAM[0],"tree":UPSTREAM[1],"archive_sha256":UPSTREAM[2],"archive_bytes":UPSTREAM[3]} or source["candidate"]!={"commit":CANDIDATE[0],"tree":CANDIDATE[1],"archive_sha256":CANDIDATE[2],"archive_bytes":CANDIDATE[3]}:raise Error("source")
    if source["adapter"]!={"path":ADAPTER[0],"bytes":ADAPTER[1],"sha256":ADAPTER[2],"git_blob":ADAPTER[3]}:raise Error("adapter")
    if source["projection_sources"]!=[{"path":p,"bytes":b,"sha256":s,"git_blob":g} for p,b,s,g in PROJECTION_SOURCES]:raise Error("projection sources")
    binary=source["rust_binary"]
    if set(binary)!={"path","bytes","sha256"} or binary["path"]!="target/release/sipi-com-direct-run.exe" or type(binary["bytes"]) is not int or binary["bytes"]<=0 or not HEX.fullmatch(binary["sha256"]):raise Error("binary")
    if set(source["toolchain"])!={"cargo","rustc","uv","matlab","python"}:raise Error("toolchain")
    for role,receipt in source["toolchain"].items():
        keys={"role","executable","file_sha256","version_sha256","path_redacted"}
        if role=="matlab":keys.update(("release","launch_mode"))
        if set(receipt)!=keys or receipt["role"]!=role or receipt["path_redacted"] is not True or not HEX.fullmatch(receipt["file_sha256"]) or not HEX.fullmatch(receipt["version_sha256"]):raise Error("tool receipt")
        if role=="matlab" and (receipt["executable"]!="matlab.exe" or receipt["release"]!="R2026a" or receipt["launch_mode"]!="python_engine_noFigureWindows_singleCompThread"):raise Error("matlab receipt")
    for asset in report["channels"]+[r["workbook"] for r in report["records"]]:
        if not HEX.fullmatch(asset["sha256"]) or type(asset["bytes"]) is not int or asset["bytes"]<=0:raise Error("asset")
    if type(report["selection_count"]) is not int or report["selection_count"]!=len(report["records"]) or not 1<=report["selection_count"]<=13:raise Error("selection")
    indices=[]
    for record in report["records"]:
        if set(record)!={"workbook_index","workbook","status","exit_code","detail_sha256","source_inventory_unchanged","config_materialization","case_count","metrics"}:raise Error("record schema")
        index=record["workbook_index"];indices.append(index)
        if type(index) is not int or not 0<=index<13 or record["workbook"]!={"path":CONFIG_PATHS[index],"bytes":WORKBOOKS[CONFIG_PATHS[index]][0],"sha256":WORKBOOKS[CONFIG_PATHS[index]][1]}:raise Error("record identity")
        if record["status"] not in ("passed","candidate_timeout","candidate_branch_missing","matlab_failed","source_inventory_drift","config_materialization_drift") or type(record["exit_code"]) is not int or not HEX.fullmatch(record["detail_sha256"]):raise Error("record status")
        if type(record["source_inventory_unchanged"]) is not bool or (record["status"]=="source_inventory_drift") == record["source_inventory_unchanged"]:raise Error("source inventory crossfield")
        materialization=record["config_materialization"]
        if report["engine"]=="rust":
            if materialization!={"comparison":"not_run_for_rust_result_replay"}:raise Error("rust materialization marker")
        elif materialization.get("comparison")=="worker_failed":
            if materialization!={"comparison":"worker_failed"}:raise Error("worker marker")
        else:
            expected={"comparison","first_difference","pinned_sha256","rust_sha256","parameter_shape","parameter_slot_digest","parameter_mat_bytes","parameter_mat_sha256"}
            shape=materialization.get("parameter_shape")
            if set(materialization)!=expected or materialization["comparison"] not in ("equal","drift") or any(not HEX.fullmatch(materialization[key]) for key in ("pinned_sha256","rust_sha256","parameter_slot_digest","parameter_mat_sha256")) or type(shape) is not list or len(shape)!=2 or any(type(x) is not int or x<=0 for x in shape) or type(materialization["parameter_mat_bytes"]) is not int or materialization["parameter_mat_bytes"]<=0:raise Error("materialization")
            if (materialization["comparison"]=="equal")!=(materialization["pinned_sha256"]==materialization["rust_sha256"]):raise Error("materialization comparison")
            if (materialization["comparison"]=="equal")!=(materialization["first_difference"] is None) or (materialization["first_difference"] is not None and (type(materialization["first_difference"]) is not str or not materialization["first_difference"])):raise Error("materialization difference")
        if type(record["case_count"]) is not int or record["case_count"]!=len(record["metrics"]):raise Error("case count")
        successful_process=record["exit_code"]==0 and record["case_count"]>0
        if record["status"] in ("passed","config_materialization_drift"):
            if not successful_process:raise Error("status crossfield")
        elif record["status"]!="source_inventory_drift" and successful_process:raise Error("status crossfield")
        if record["status"]=="config_materialization_drift" and record["config_materialization"].get("comparison")!="drift":raise Error("materialization status")
        if report["engine"]=="rust" and ((record["status"]=="candidate_timeout") != (record["exit_code"]==124)):raise Error("timeout crossfield")
        for case in record["metrics"]:
            if any(name not in METRICS for name in case):raise Error("metric name")
            for value in case.values():
                if isinstance(value,bool) or not (isinstance(value,(int,float)) or value in ("+Inf","-Inf","NaN")):raise Error("metric value")
    if len(set(indices))!=len(indices) or indices!=sorted(indices):raise Error("record order")
    if report["claims"]!={"acceptance":False,"historical_python_used":False,"s_parameter_fit":False,"one_final_fd_to_td_impulse":True}:raise Error("claims")
    return True
