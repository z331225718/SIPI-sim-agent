from __future__ import annotations
import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_com_td_crosstalk_stage_replay_v1 import VerificationError,verify_manifest,verify_report,verify_aggregate,aggregate_hash
from aggregate_com_td_crosstalk_stage_replay_v1 import main as aggregate_main
def h(c):return c*64
def ident(n):return {"role":n,"basename":n,"file_sha256":h("1"),"version_output_sha256":h("2"),"version_exit":0,"status":"ok","path_redacted":True}
def make_manifest():
    m={"schema":"sipi.com.td-crosstalk-stage-replay.v1","mode":"prep","candidate":{"commit":h("a")[:40],"tree":h("b")[:40],"archive_sha256":h("c")},"upstream":{"commit":h("d")[:40],"tree":h("e")[:40],"archive_sha256":h("f")},"f2_values_hz":[50000000000.0,13000000000.0],"stage":{"short_count":8,"full_count":64},"run_ids":["com-td-crosstalk-stage-v1-run1","com-td-crosstalk-stage-v1-run2"],"runner":{"path":"tools/run.py","sha256":h("6")},"helper":{"path":"tools/helper.py","sha256":h("7")},"tools":{"verifier":{"path":"tools/verify.py","sha256":h("3")},"aggregator":{"path":"tools/aggregate.py","sha256":h("4")},"tests":{"path":"tools/test.py","sha256":h("5")}},"fixture_paths":["fixtures/synthetic/td_thru_pulse.csv","fixtures/synthetic/td_fext_pulse.csv","fixtures/synthetic/td_next_pulse.csv"],"fixture_sha256":{"fixtures/synthetic/td_thru_pulse.csv":h("c"),"fixtures/synthetic/td_fext_pulse.csv":h("d"),"fixtures/synthetic/td_next_pulse.csv":h("e")}}
    import hashlib
    files={"runner":"tools/run_com_td_crosstalk_stage_replay_v1.py","helper":"tools/com_erl_exact_profile_replay_v3_support.py","pe_helper":"tools/pb_03_replay_common.py","verifier":"tools/verify_com_td_crosstalk_stage_replay_v1.py","aggregator":"tools/aggregate_com_td_crosstalk_stage_replay_v1.py","tests":"tools/test_verify_com_td_crosstalk_stage_replay_v1.py"}
    m["runner"]={"path":files["runner"],"sha256":hashlib.sha256(Path(files["runner"]).read_bytes()).hexdigest()};m["helper"]={"path":files["helper"],"sha256":hashlib.sha256(Path(files["helper"]).read_bytes()).hexdigest()};m["pe_helper"]={"path":files["pe_helper"],"sha256":hashlib.sha256(Path(files["pe_helper"]).read_bytes()).hexdigest()}
    m["tools"]={key:{"path":files[key],"sha256":hashlib.sha256(Path(files[key]).read_bytes()).hexdigest()} for key in ("verifier","aggregator","tests")}
    m["harness"]={"path":files["runner"],"sha256":m["runner"]["sha256"]}
    verify_manifest(m);return m
def make_report(m,i):
    stages={"short_response":{"count":8,"sha256":h("1")},"full_noise_axis":{"count":64,"sha256":h("2")},"outer_product":{"rows":8,"columns":64,"elements":512,"order":"column-major-linear","role_sum":{"FEXT":h("3"),"NEXT":h("4")}}}
    tools={k:ident(k) for k in ("git","cargo","rustc","linker","python","numpy","uv")}
    tools["numpy"].update({"core_basename":"numpy_core.dll","core_binary_sha256":h("8"),"version_output_sha256":hashlib.sha256(b"1").hexdigest()})
    outputs={str(v):{"noise":1.0,"numpy_version":"1","numpy_version_sha256":tools["numpy"]["version_output_sha256"],"numpy_module_sha256":tools["numpy"]["file_sha256"],"numpy_core_basename":"numpy_core.dll","numpy_core_sha256":h("8")} for v in m["f2_values_hz"]}
    inv={"count":1,"combined_sha256":h("1")};env={"RUSTC":{"basename":"rustc","sha256":h("1")},"CARGO_BUILD_RUSTC":{"basename":"rustc","sha256":h("1")},"LINKER":{"basename":"linker","sha256":h("1")},"RUSTFLAGS":"","CARGO_ENCODED_RUSTFLAGS":"","LIB":inv,"INCLUDE":inv,"PATH":{"inventory":inv,"tool_basenames":["cargo","rustc","linker"]}}
    custody={"schema":"sipi.windows-pe-replay-custody.v1","raw_sha256":h("5"),"canonical_sha256":h("9"),"canonical_helper":m["pe_helper"]}
    return {"schema":m["schema"],"run_id":m["run_ids"][i],"fresh_run_nonce":str(i+1)*64,"path_policy":{"absolute_paths_emitted":False},"candidate":{**m["candidate"],"materialization":"git archive; no working-tree overlay","binary_sha256":h("5"),"binary_custody":custody,"source_inventory":{"count":1,"combined_sha256":h("6")}},"upstream":{**m["upstream"],"materialization":"git archive; no working-tree overlay","oracle_role":"pinned_agent_com_pure_leaf","oracle":"agent_com.equalization.search._td_source_crosstalk_noise"},"input":{"fixture_paths":m["fixture_paths"],"fixture_source_archive_sha256":m["upstream"]["archive_sha256"],"fixture_sha256":m["fixture_sha256"],"independent_read_only":True,"channel_policy":"TD pulse-derived; no S-parameter fit","f2_copy_sha256":{str(v):{"candidate":h("7"),"upstream":h("7")} for v in m["f2_values_hz"]}},"stages":stages,"stage_observation":"shared exact scoped stage","upstream_output":outputs,"candidate_output":{str(v):1.0 for v in m["f2_values_hz"]},"parity":{"numeric_policy":{"f2_values_hz":[50000000000.0,13000000000.0],"atol":1e-12,"rtol":1e-12},"differences":{},"matched":True},"status":"matched","execution":{"runner":m["runner"],"helper":m["helper"],"pe_helper":m["pe_helper"],"upstream_runtime":"uv run --frozen --offline --project . --python <pinned-python> python -c <pinned-pure-leaf>","uv_actual_execution":True,"wrappers":{"RUSTC_WRAPPER":"","RUSTC_WORKSPACE_WRAPPER":"","CARGO_BUILD_RUSTC_WRAPPER":""},"build_environment":env},"toolchain":tools,"non_claims":["scoped TDMODE crosstalk stage only"]}
class PrepTests(unittest.TestCase):
    def test_prep_schema_has_no_formal_outputs(self):
        m=make_manifest(); prep=copy.deepcopy(m); prep["mode"]="prep"; prep["harness"]={"path":"tools/run_com_td_crosstalk_stage_replay_v1.py","sha256":hashlib.sha256(Path("tools/run_com_td_crosstalk_stage_replay_v1.py").read_bytes()).hexdigest()}
        for key in ("reports","report_sha256","aggregate","audit"): prep.pop(key,None)
        verify_manifest(prep)
        forged=dict(prep); forged["reports"]=[]
        with self.assertRaises(VerificationError): verify_manifest(forged)
        forged=copy.deepcopy(prep);forged["fixture_sha256"][prep["fixture_paths"][0]]="bad"
        with self.assertRaises(VerificationError): verify_manifest(forged)
        forged=copy.deepcopy(prep);forged["tools"]["unexpected"]={"path":prep["runner"]["path"],"sha256":prep["runner"]["sha256"]}
        with self.assertRaises(VerificationError): verify_manifest(forged)
    def test_valid_and_mutations(self):
        m=make_manifest();r=make_report(m,0);verify_report(r,m)
        for path,value in ((("candidate","binary_sha256"),"bad"),(("candidate","commit"),m["upstream"]["commit"]),(("execution","runner","path"),"/opt/overlay.py"),(("execution","wrappers","RUSTC_WRAPPER"),"x"),(("toolchain","numpy"),{}),(("stages","outer_product","order"),"row-major"),(("upstream_output","50000000000.0","noise"),float("nan")),(("fresh_run_nonce",),"G"*64)):
            forged=copy.deepcopy(r);node=forged
            for key in path[:-1]:node=node[key]
            node[path[-1]]=value
            with self.assertRaises(VerificationError):verify_report(forged,m)
    def test_aggregate_forgery_rejected(self):
        m=make_manifest();a={"schema":m["schema"]+".aggregate","status":"matched","matched":True}
        with self.assertRaises(VerificationError):verify_aggregate(a,[],[],m,Path("aggregate.json"))
    def test_mock_aggregator_roundtrip_and_canonical_pe_gate(self):
        m=make_manifest(); m.pop("mode");m.pop("harness")
        with tempfile.TemporaryDirectory(dir="tools") as directory:
            root=Path(directory); rel=lambda p:p.relative_to(Path.cwd()).as_posix()
            first,second=make_report(m,0),make_report(m,1)
            p1,p2=root/"run1.json",root/"run2.json"; p1.write_text(json.dumps(first));p2.write_text(json.dumps(second))
            m["reports"]=[rel(p1),rel(p2)];m["report_sha256"]={rel(p1):hashlib.sha256(p1.read_bytes()).hexdigest(),rel(p2):hashlib.sha256(p2.read_bytes()).hexdigest()}
            audit=root/"audit.md";audit.write_text("prep");m["audit"]={"path":rel(audit),"sha256":hashlib.sha256(audit.read_bytes()).hexdigest()}
            aggregate={"schema":m["schema"]+".aggregate","status":"matched","matched":True,"report_sha256":[m["report_sha256"][rel(p1)],m["report_sha256"][rel(p2)]],"run_ids":m["run_ids"],"candidate":{k:m["candidate"][k] for k in ("commit","tree","archive_sha256")},"upstream":{k:m["upstream"][k] for k in ("commit","tree","archive_sha256")}}
            aggregate["aggregate_sha256"]=aggregate_hash(aggregate);ap=root/"aggregate.json";ap.write_text(json.dumps(aggregate,sort_keys=True));m["aggregate"]={"path":rel(ap),"sha256":hashlib.sha256(ap.read_bytes()).hexdigest()}
            manifest_path=root/"manifest.json";manifest_path.write_text(json.dumps(m,sort_keys=True));old_argv=sys.argv;sys.argv=["aggregate", "--manifest", str(manifest_path), "--output", m["aggregate"]["path"]]
            try:self.assertEqual(aggregate_main(),0)
            finally:sys.argv=old_argv
            m=json.loads(manifest_path.read_text());aggregate=json.loads(ap.read_text());verify_aggregate(aggregate,[Path(m["reports"][0]),Path(m["reports"][1])],[first,second],m,Path(m["aggregate"]["path"]))
            forged=copy.deepcopy(second);forged["candidate"]["binary_sha256"]=h("a");forged["candidate"]["binary_custody"]["raw_sha256"]=h("a");p2.write_text(json.dumps(forged));m["report_sha256"][rel(p2)]=hashlib.sha256(p2.read_bytes()).hexdigest();aggregate["report_sha256"][1]=m["report_sha256"][rel(p2)];aggregate["aggregate_sha256"]=aggregate_hash(aggregate);ap.write_text(json.dumps(aggregate,sort_keys=True));m["aggregate"]["sha256"]=hashlib.sha256(ap.read_bytes()).hexdigest();verify_aggregate(aggregate,[Path(m["reports"][0]),Path(m["reports"][1])],[first,forged],m,Path(m["aggregate"]["path"]))
            forged["candidate"]["binary_custody"]["canonical_sha256"]=h("b");p2.write_text(json.dumps(forged));m["report_sha256"][rel(p2)]=hashlib.sha256(p2.read_bytes()).hexdigest();aggregate["report_sha256"][1]=m["report_sha256"][rel(p2)];aggregate["aggregate_sha256"]=aggregate_hash(aggregate);ap.write_text(json.dumps(aggregate,sort_keys=True));m["aggregate"]["sha256"]=hashlib.sha256(ap.read_bytes()).hexdigest()
            with self.assertRaises(VerificationError):verify_aggregate(aggregate,[Path(m["reports"][0]),Path(m["reports"][1])],[first,forged],m,Path(m["aggregate"]["path"]))
if __name__=="__main__":unittest.main()
