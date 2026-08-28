"""Verify a future immutable AS-06 ngspice parity record."""
from __future__ import annotations
import argparse,hashlib,json,math,subprocess,sys,tempfile
from pathlib import Path
import yaml
import aggregate_as_06_ngspice_result_parity as aggregate
MANIFEST="docs/baselines/as-06-ngspice-result-parity.v2.yaml";REPORTS=("docs/baselines/as-06-ngspice-result-parity-run-01.v2.json","docs/baselines/as-06-ngspice-result-parity-run-02.v2.json");AGGREGATE="docs/baselines/as-06-ngspice-result-parity-aggregate.v2.json";AUDIT="docs/baselines/audits/2026-08-29-as-06-ngspice-result-parity-v2.md"
GATE="927d9047315c6a88ec9497c452a5f6d5197210a0";GATE_TREE="edc20977b556ed9e88c1ac0feaa1cbcfd6254208"
PREP_PARENT="90dea971a1661cf6ae0b7f71aab12b84f6eb241c"
INTERPOSED=("M\tdocs/baselines/audits/2026-08-29-com-02-04-result-surface.md","M\ttools/com_direct_semantic_replay.py","M\ttools/com_direct_semantic_replay_v2.py","A\ttools/test_com_direct_semantic_replay_prep.py")
CANDIDATE={"commit":"aea546510d345cd7e280e55897c027be872d759a","tree":"df99e5bb1c2381bb52fe0037b7b8fbb38b7c6cb9","sha256":"4da4772366c49330679c85626b63eeccd3234643303d04bcd9b657c0d9eff326","bytes":54640640}
UPSTREAM={"commit":"2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5","tree":"b6bde97128030d6cea0d68b2f0a35d807be8c402","sha256":"a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144","bytes":120238080}
RUNS=(("as06-formal-01","d413891862a3e7a7cefaec7a3a974e8d865d314e305d3371b650ce0f4d6ee836"),("as06-formal-02","fd0e621383bd9ad5b316125eeceb283eee8f9bd86894368a548a7d7cd6047056"))
RECORDS={REPORTS[0]:"0e5d9b118335e2e7bf00d04d0650bd5b03e1d9499c1b0738045795d4dff0563d",REPORTS[1]:"1d8fa1d937c8f9ba21e40bf8b1feeb2307aee72e21b980344fee6929365b7713",AGGREGATE:"aafa363f0745dcdb2a17f4ae97214db64935f7d256575547e606bc45772ce7f5"}
HARNESS={"tools/run_as_06_ngspice_result_parity.py":"84d4b30e9af34d00ecea411757465966529812721ce3b493a19f1b04a9b1adef","tools/aggregate_as_06_ngspice_result_parity.py":"252393ca3dc69b33c73e83a0c11b84765992c00117e0689725bbd5ca8e6a7107","tools/verify_as_06_ngspice_result_parity.py":"b76be5005000fa228a78c80741151088ef833f3867a2789c519acd845d9a60e7","tools/test_verify_as_06_ngspice_result_parity.py":"7d567b384a7652f51378968bfdf3b12d62aa0e21d05dadccebd24f6bb1f22bb0"}
CLAIMS={"external_solver_scoped_observation":True,"solver_correctness":False,"release_acceptance":False,"s_parameter_fit":False,"as05_xyce_xdm":False,"environment_injection_resistance":False,"hostile_writer_resistance":False}
RESULT={"headers":["time","v(src)","v(out)"],"waveform_rows":1029,"float_bit_exact":True,"max_abs_error":0.0,"logical_manifest_equal":True,"runtime_semantics_equal":True,"rust_reconstruction_rms":0.0,"upstream_reconstruction_rms":0.0,"rust_reconstruction_max":0.0,"upstream_reconstruction_max":0.0}
MARKERS=(GATE,"passed_scoped_external_observation","does not claim solver correctness","does not claim release acceptance","does not claim hostile-writer resistance","does not claim environment-injection resistance","does not claim S-parameter fitting","does not claim AS-05 Xyce/XDM support")
GATE_PATHS=("tools/verify_as_06_ngspice_result_parity_formal.py","tools/test_verify_as_06_ngspice_result_parity_formal.py")
FORMAL=(*REPORTS,AGGREGATE,MANIFEST,AUDIT)
class StrictLoader(yaml.SafeLoader):pass
def _mapping(loader,node,deep=False):
 out={}
 for kn,vn in node.value:
  key=loader.construct_object(kn,deep=deep)
  if key in out:raise ValueError(f"duplicate YAML key: {key}")
  out[key]=loader.construct_object(vn,deep=deep)
 return out
StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,_mapping)
def exact(value,keys,label):
 if type(value) is not dict or set(value)!=set(keys):raise ValueError(f"{label} keyset drift")
def typed_equal(left,right):
 if type(left) is not type(right):return False
 if isinstance(left,dict):return set(left)==set(right) and all(typed_equal(left[key],right[key]) for key in left)
 if isinstance(left,list):return len(left)==len(right) and all(typed_equal(a,b) for a,b in zip(left,right))
 return left==right
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):return digest(path.read_bytes())
def finite(value):
 if isinstance(value,bool):return
 if isinstance(value,float) and not math.isfinite(value):raise ValueError("non-finite")
 if isinstance(value,dict):
  for child in value.values():finite(child)
 if isinstance(value,list):
  for child in value:finite(child)
def git_raw(repo,*args):return subprocess.run(["git","-C",str(repo),*args],check=True,capture_output=True,timeout=60).stdout
def git(repo,*args):return git_raw(repo,*args).decode("ascii").strip()
def archive(repo,identity):
 if git(repo,"rev-parse",identity["commit"])!=identity["commit"] or git(repo,"show","-s","--format=%T",identity["commit"])!=identity["tree"]:raise ValueError("Git identity drift")
 with tempfile.TemporaryFile() as output:
  subprocess.run(["git","-C",str(repo),"archive","--format=tar",identity["commit"]],check=True,stdout=output,stderr=subprocess.PIPE,timeout=120)
  size=output.tell()
  if size>128*1024*1024:raise ValueError("Git archive exceeds cap")
  output.seek(0);actual=hashlib.file_digest(output,"sha256").hexdigest()
 if size!=identity["bytes"] or actual!=identity["sha256"]:raise ValueError("Git archive drift")
def verify_gate(repo:Path,commit:str,require_live=True):
 resolved=git(repo,"rev-parse",commit)
 if git(repo,"merge-base",GATE,PREP_PARENT)!=GATE:raise ValueError("interposed prep ancestry drift")
 if git(repo,"rev-parse",f"{GATE}^{{tree}}")!=GATE_TREE:raise ValueError("Stage1 tree drift")
 if sorted(git(repo,"diff","--name-status","--no-renames",GATE,PREP_PARENT).splitlines())!=sorted(INTERPOSED):raise ValueError("interposed COM prep drift")
 for path in HARNESS:
  if git(repo,"rev-parse",f"{GATE}:{path}")!=git(repo,"rev-parse",f"{PREP_PARENT}:{path}"):raise ValueError("AS harness drift across interposed prep")
 if git(repo,"show","-s","--format=%P",resolved).split()!=[PREP_PARENT]:raise ValueError("Stage2 gate parent drift")
 changed=git(repo,"diff-tree","--no-commit-id","--name-status","--no-renames","-r",PREP_PARENT,resolved).splitlines()
 if sorted(changed)!=sorted(f"A\t{path}" for path in GATE_PATHS):raise ValueError("Stage2 gate must be exact two additions")
 for path in GATE_PATHS:
  if git(repo,"ls-tree",PREP_PARENT,"--",path):raise ValueError("Stage2 tools not first introduction")
  if not git(repo,"ls-tree",resolved,"--",path).startswith("100644 blob "):raise ValueError("Stage2 tool mode drift")
  raw=git_raw(repo,"show",f"{resolved}:{path}")
  if require_live and (repo/path).read_bytes()!=raw:raise ValueError("Stage2 live/blob drift")
 for path in FORMAL:
  if git(repo,"ls-tree",resolved,"--",path):raise ValueError("formal artifact entered Stage2 gate")
 return {"valid":True,"commit":resolved,"parent":PREP_PARENT,"stage1_gate":GATE,"interposed":list(INTERPOSED),"changed_paths":list(GATE_PATHS),"formal_absent":True}
def gate_binding(repo:Path,commit:str):
 files={}
 for path in GATE_PATHS:
  raw=git_raw(repo,"show",f"{commit}:{path}")
  files[path]={"blob":git(repo,"rev-parse",f"{commit}:{path}"),"sha256":digest(raw),"bytes":len(raw)}
  if Path(__file__).resolve().parents[1].joinpath(path).read_bytes()!=raw:raise ValueError("executing Stage2 tool bytes drift")
 return {"commit":commit,"tree":git(repo,"rev-parse",f"{commit}^{{tree}}"),"files":files}
def verify_record_commit(repo:Path,formal_gate_commit:str,record_commit:str,require_live=True):
 gate=verify_gate(repo,formal_gate_commit,require_live=False);resolved=git(repo,"rev-parse",record_commit)
 if git(repo,"show","-s","--format=%P",resolved).split()!=[gate["commit"]]:raise ValueError("record must directly follow formal gate")
 changed=git(repo,"diff-tree","--no-commit-id","--name-status","--no-renames","-r",gate["commit"],resolved).splitlines()
 if sorted(changed)!=sorted(f"A\t{path}" for path in FORMAL):raise ValueError("record must be exact five additions")
 for path in FORMAL:
  if git(repo,"ls-tree",gate["commit"],"--",path):raise ValueError("record is not first introduction")
  if not git(repo,"ls-tree",resolved,"--",path).startswith("100644 blob "):raise ValueError("record mode drift")
  raw=git_raw(repo,"show",f"{resolved}:{path}")
  if require_live and (repo/path).read_bytes()!=raw:raise ValueError("record live/blob drift")
 if require_live and subprocess.run(["git","-C",str(repo),"status","--porcelain"],check=True,capture_output=True,timeout=60).stdout:raise ValueError("record worktree is not clean")
 return {"valid":True,"commit":resolved,"formal_gate":gate["commit"],"changed_paths":list(FORMAL)}
def audit_text(records):
 return ("# AS-06 ngspice result parity v2\n\n"
  f"Harness gate: `{GATE}`.\n"
  f"Run 01: `{records[REPORTS[0]]}`.\nRun 02: `{records[REPORTS[1]]}`.\nAggregate: `{records[AGGREGATE]}`.\n"
  "Status: `passed_scoped_external_observation`.\n"
  "This record does not claim solver correctness.\nThis record does not claim release acceptance.\n"
  "This record does not claim hostile-writer resistance.\nThis record does not claim environment-injection resistance.\n"
  "This record does not claim S-parameter fitting.\nThis record does not claim AS-05 Xyce/XDM support.\n")
def verify(repo:Path,upstream_repo:Path,formal_gate_commit:str,record_commit:str)->dict:
 custody=verify_record_commit(repo,formal_gate_commit,record_commit)
 manifest=yaml.load((repo/MANIFEST).read_text(encoding="utf-8"),Loader=StrictLoader);finite(manifest)
 exact(manifest,("schema","status","harness_gate","formal_gate","candidate","upstream","records","audit","result","claims"),"manifest")
 if manifest["schema"]!="sipi.as-06-ngspice-result-parity-evidence.v2" or manifest["status"]!="passed_scoped_external_observation":raise ValueError("manifest header drift")
 exact(manifest["harness_gate"],("commit","tree","files"),"gate");exact(manifest["records"],(*REPORTS,AGGREGATE),"records");exact(manifest["audit"],("path","sha256"),"audit")
 if not all((typed_equal(manifest["harness_gate"],{"commit":GATE,"tree":GATE_TREE,"files":HARNESS}),typed_equal(manifest["formal_gate"],gate_binding(repo,custody["formal_gate"])),typed_equal(manifest["candidate"],CANDIDATE),typed_equal(manifest["upstream"],UPSTREAM),typed_equal(manifest["records"],RECORDS),typed_equal(manifest["claims"],CLAIMS),typed_equal(manifest["result"],RESULT))) or manifest["audit"]["path"]!=AUDIT:raise ValueError("manifest binding drift")
 if git(repo,"rev-parse",f"{GATE}^{{tree}}")!=GATE_TREE:raise ValueError("gate tree drift")
 for path,want in HARNESS.items():
  if digest(git_raw(repo,"show",f"{GATE}:{path}"))!=want:raise ValueError("harness blob drift")
 archive(repo,CANDIDATE);archive(upstream_repo,UPSTREAM)
 source="docs/baselines/as-06-run-rfm-source-map.v4.yaml"
 if digest(git_raw(repo,"show",f"{CANDIDATE['commit']}:{source}"))!="9c96655e08fce504ae936b4e0c0cfb93a53ceafee7f0a3a9f848e1add0239304":raise ValueError("source-map drift")
 for path,want in manifest["records"].items():
  if sha(repo/path)!=want:raise ValueError("record hash drift")
 audit=(repo/AUDIT).read_text(encoding="utf-8")
 if sha(repo/AUDIT)!=manifest["audit"]["sha256"] or audit!=audit_text(manifest["records"]):raise ValueError("audit drift")
 reports=[]
 for index,path in enumerate(REPORTS):
  item=json.loads((repo/path).read_text(encoding="utf-8"));finite(item)
  if (item.get("run_id"),item.get("caller_challenge"))!=RUNS[index] or not typed_equal(item.get("candidate"),CANDIDATE) or not typed_equal(item.get("upstream"),UPSTREAM) or not typed_equal(item.get("claims"),CLAIMS):raise ValueError("report binding drift")
  reports.append(repo/path)
 stored=json.loads((repo/AGGREGATE).read_text(encoding="utf-8"));finite(stored)
 if not typed_equal(aggregate.aggregate(reports),stored) or not typed_equal(stored.get("result"),RESULT) or not typed_equal(stored.get("claims"),CLAIMS):raise ValueError("aggregate drift")
 return {"valid":True,"status":stored["status"],"reports":[sha(path) for path in reports],"aggregate":sha(repo/AGGREGATE)}
def main():
 p=argparse.ArgumentParser();p.add_argument("--repository",type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument("--upstream-repository",type=Path);p.add_argument("--gate-commit");p.add_argument("--formal-gate-commit");p.add_argument("--record-commit");a=p.parse_args()
 if a.gate_commit:
  try:print(json.dumps(verify_gate(a.repository,a.gate_commit),sort_keys=True));return 0
  except Exception as exc:print(f"blocked: {exc}",file=sys.stderr);return 1
 if a.upstream_repository is None:p.error("--upstream-repository is required for formal records")
 if not a.formal_gate_commit or not a.record_commit:p.error("--formal-gate-commit and --record-commit are required")
 try:print(json.dumps(verify(a.repository,a.upstream_repository,a.formal_gate_commit,a.record_commit),sort_keys=True));return 0
 except Exception as exc:print(f"blocked: {exc}",file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
