"""Aggregate two fresh MATLAB and two fresh Rust original-13 reports."""
import argparse, hashlib, json, math
from pathlib import Path
from run_p5_06_original13_rust_matlab_prep import scalar_equal
try:
    from .run_p5_06_original13_extended_scalar_matrix_v1 import METRICS
    from .verify_p5_06_original13_extended_scalar_matrix_v1 import verify
except ImportError:
    from run_p5_06_original13_extended_scalar_matrix_v1 import METRICS
    from verify_p5_06_original13_extended_scalar_matrix_v1 import verify

def load(path): return json.loads(Path(path).read_bytes(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def equal(a,b,tol,nan=False):
    if isinstance(a,str) or isinstance(b,str): return a==b and a in ("+Inf","-Inf")
    if isinstance(a,bool) or isinstance(b,bool): return False
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        if math.isnan(float(a)) or math.isnan(float(b)): return nan and math.isnan(float(a)) and math.isnan(float(b))
        if math.isinf(float(a)) or math.isinf(float(b)): return scalar_equal(a,b)
        return abs(float(a)-float(b))<=tol
    return False
def slots(report):
    return {(record["workbook_index"],case_index,name):value for record in report["records"] for case_index,case in enumerate(record["metrics"]) for name,value in case.items() if name in METRICS}
def comparable_source(report):
    source=dict(report["source"])
    # Two clean, locked builds of the same source can differ in PE metadata.
    # Keep each binary receipt in the aggregate, but do not confuse that
    # incidental build variation with candidate, toolchain, or input drift.
    source.pop("rust_binary")
    return source
def main():
    p=argparse.ArgumentParser();p.add_argument("--report",action="append",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if len(a.report)!=4 or a.output.exists():p.error("four reports and create-new output required")
    reports=[load(x) for x in a.report]
    for report in reports: verify(report)
    if [r.get("engine") for r in reports] != ["matlab","matlab","rust","rust"]:p.error("engine order")
    identities=[(r.get("run_id"),r.get("nonce")) for r in reports]
    if len({x[0] for x in identities})!=4 or len({x[1] for x in identities})!=4:p.error("fresh identity")
    for r in reports:
        if r["status"]!="fresh_matrix_run" or any(record["status"]!="passed" for record in r["records"]):p.error("non-passed input")
        if r.get("selection_count")!=13 or [x.get("workbook_index") for x in r.get("records",[])]!=list(range(13)):p.error("matrix order")
        if sum(x.get("case_count",0) for x in r["records"])!=28 or len(slots(r))<303:p.error("surface count")
    maps=[slots(x) for x in reports]
    if any(comparable_source(report)!=comparable_source(reports[0]) for report in reports[1:]):p.error("source drift")
    if any(report["channels"]!=reports[0]["channels"] for report in reports[1:]):p.error("channels drift")
    if any(set(x)!=set(maps[0]) for x in maps[1:]):p.error("slot identity")
    matlab_repeat=all(equal(maps[0][k],maps[1][k],1e-12) for k in maps[0]);rust_repeat=all(equal(maps[2][k],maps[3][k],0.0) for k in maps[2]);cross=all(equal(maps[0][k],maps[2][k],1e-9) and equal(maps[1][k],maps[3][k],1e-9) for k in maps[0])
    formal_runs=[{"path":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"engine":report["engine"],"run_id":report["run_id"],"nonce":report["nonce"]} for path,report in zip(a.report,reports)]
    if len({item["sha256"] for item in formal_runs})!=4:p.error("report hash duplicate")
    output={"schema":"sipi.p5-06.original13-extended-scalar-aggregate.v1","status":"accepted_stage1" if matlab_repeat and rust_repeat and cross else "blocked","formal_runs":formal_runs,"source":comparable_source(reports[0]),"binary_receipts":[{"engine":report["engine"],"run_id":report["run_id"],"rust_binary":report["source"]["rust_binary"]} for report in reports],"channels":reports[0]["channels"],"slot_count":len(maps[0]),"matlab_repeat_1e_12":matlab_repeat,"rust_repeat_exact":rust_repeat,"rust_vs_matlab_1e_9":cross,"stage2":{"status":"diagnostic_only","array_tolerances":"unset","instrumentation_equivalence":"unproven"},"claims":{"historical_python_used":False,"td_iln_required":False,"s_parameter_fit":False,"one_final_fd_to_td_impulse":True,"release":False}}
    a.output.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
if __name__=="__main__":main()
