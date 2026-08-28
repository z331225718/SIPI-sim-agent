"""Mutation tests for the AS-06 ngspice parity harness."""
from __future__ import annotations
import copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parent))
import aggregate_as_06_ngspice_result_parity as aggregate
import run_as_06_ngspice_result_parity as runner
import verify_as_06_ngspice_result_parity as verifier

def receipt(name="artifact"):
 return {"basename":name,"bytes":1,"sha256":"1"*64,"nlink":1,"path_redacted":True}
def report(challenge,nonce,run_id):
 def tool(role,sha="1"*64):return {"role":role,"basename":role+".exe","sha256":sha,"version_exit":0,"version_sha256":"8"*64,"path_redacted":True}
 tools={"cargo":tool("cargo"),"rustc":tool("rustc"),"ngspice":tool("ngspice",aggregate.INPUTS["ngspice_sha256"]),"python":tool("python")}
 names={"rust_waveform":"waveform.csv","upstream_waveform":"waveform.csv","rust_manifest":"rfm_run_manifest.json","upstream_manifest":"rfm_run_manifest.json","rust_stdout":"stdout.log","upstream_stdout":"stdout.log"}
 runner_sha=__import__("hashlib").sha256((Path(__file__).resolve().parent/"run_as_06_ngspice_result_parity.py").read_bytes()).hexdigest()
 dependency={"files":2,"bytes":2,"sha256":"a"*64,"path_redacted":True}
 return {"schema":"sipi.as-06-ngspice-result-parity.v2","status":"passed","run_id":run_id,"caller_challenge":challenge,"fresh_run_nonce":nonce,"runner_sha256":runner_sha,"candidate":copy.deepcopy(aggregate.CANDIDATE),"upstream":copy.deepcopy(aggregate.UPSTREAM),"toolchain_pre":tools,"toolchain_post":copy.deepcopy(tools),"binary_pre":receipt("sipi-agent-spice-run-rfm.exe"),"binary_post":receipt("sipi-agent-spice-run-rfm.exe"),"dependency_pre":dependency,"dependency_post":copy.deepcopy(dependency),"environment":{"policy":"cargo_rust_python_uv_pip_spice_prefixes_removed","cargo_target_fresh":True},"source_map":{"path":"docs/baselines/as-06-run-rfm-source-map.v4.yaml","sha256":"9c96655e08fce504ae936b4e0c0cfb93a53ceafee7f0a3a9f848e1add0239304"},"inputs":copy.deepcopy(aggregate.INPUTS),"physical":{key:receipt(name) for key,name in names.items()},"canonical":{"rust_f64_sha256":"3"*64,"upstream_f64_sha256":"3"*64},"result":copy.deepcopy(aggregate.RESULT),"claims":copy.deepcopy(aggregate.CLAIMS)}

class Tests(unittest.TestCase):
 def test_valid_twofresh_and_coordinated_mutations(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);paths=[]
   for index,value in enumerate((report("4"*64,"5"*64,"run-1"),report("6"*64,"7"*64,"run-2"))):
    path=root/f"run-{index}.json";path.write_text(json.dumps(value));paths.append(path)
   self.assertEqual(aggregate.aggregate(paths)["result"],aggregate.RESULT)
   mutations=[("candidate","commit"),("inputs","ngspice_sha256"),("claims","solver_correctness"),("canonical","upstream_f64_sha256")]
   for outer,inner in mutations:
    changed=json.loads(paths[0].read_text());changed[outer][inner]=True if inner=="solver_correctness" else "0"*64;paths[0].write_text(json.dumps(changed))
    with self.assertRaises(ValueError):aggregate.aggregate(paths)
    paths[0].write_text(json.dumps(report("4"*64,"5"*64,"run-1")))
   changed=report("4"*64,"5"*64,"run-1");changed["toolchain_pre"]={"ngspice":changed["toolchain_pre"]["ngspice"]};changed["toolchain_post"]=copy.deepcopy(changed["toolchain_pre"]);paths[0].write_text(json.dumps(changed))
   with self.assertRaises(ValueError):aggregate.aggregate(paths)
   changed=report("4"*64,"5"*64,"run-1");changed["result"]["rust_reconstruction_rms"]=False;paths[0].write_text(json.dumps(changed))
   with self.assertRaises(ValueError):aggregate.aggregate(paths)
   changed=report("4"*64,"5"*64,"run-1");changed["result"]["runtime_semantics_equal"]=False;paths[0].write_text(json.dumps(changed))
   with self.assertRaises(ValueError):aggregate.aggregate(paths)
 def test_duplicate_challenge_nonce_and_report_digest_rejected(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);a=report("4"*64,"5"*64,"run-1");b=report("4"*64,"5"*64,"run-2")
   paths=[root/"a.json",root/"b.json"]
   for path,value in zip(paths,(a,b)):path.write_text(json.dumps(value))
   with self.assertRaises(ValueError):aggregate.aggregate(paths)
 def test_csv_nonfinite_and_schema_fail_closed(self):
  with tempfile.TemporaryDirectory() as raw:
   path=Path(raw)/"waveform.csv";path.write_text("time,v(src),v(out)\n0,0,nan\n",encoding="ascii")
   with self.assertRaises(RuntimeError):runner.load_csv(path)
   path.write_text("time,v(src),v(out)\n0,0,inf\n",encoding="ascii")
   with self.assertRaises(RuntimeError):runner.load_csv(path)
 def test_gate_requires_fixed_parent_exact_four_first_introduction(self):
  payloads={path:(path+"\n").encode() for path in verifier.PATHS}
  def fake_git(repo,*args,raw=False):
   if args[:2]==("rev-parse","gate"):return "gate"
   if args[:3]==("show","-s","--format=%P"):return verifier.PREP_PARENT
   if args[:1]==("merge-base",):return verifier.AS_CANDIDATE
   if args[:2]==("rev-parse",f"{verifier.AS_CANDIDATE}^{{tree}}"):return verifier.AS_CANDIDATE_TREE
   if args[:4]==("diff","--name-status","--no-renames",verifier.AS_CANDIDATE):return "\n".join(verifier.INTERPOSED)
   if args[0]=="diff-tree":return "\n".join(f"A\t{path}" for path in verifier.PATHS)
   if args[0]=="ls-tree":
    if args[1]==verifier.PREP_PARENT:return ""
    path=args[-1]
    if path in verifier.FORMAL:return ""
    return f"100644 blob {'9'*40}\t{path}"
   if args[0]=="show":return payloads[args[1].split(":",1)[1]]
   if args[0]=="rev-parse" and args[1].endswith("^{tree}"):return "8"*40
   if args[0]=="rev-parse":return "9"*40
   raise AssertionError(args)
  with mock.patch.object(verifier,"git",side_effect=fake_git):
   self.assertTrue(verifier.verify_gate(Path("."),"gate",require_live=False)["valid"])
  with mock.patch.object(verifier,"git",side_effect=lambda repo,*args,**kwargs: "wrong" if args[:3]==("show","-s","--format=%P") else fake_git(repo,*args,**kwargs)):
   with self.assertRaises(ValueError):verifier.verify_gate(Path("."),"gate",require_live=False)
  cases=(
   lambda args,value: value+"\nextra" if args and args[0]=="diff-tree" else value,
   lambda args,value: "100644 blob dead\tpath" if args and args[0]=="ls-tree" and args[1]==verifier.PREP_PARENT and args[-1] in verifier.PATHS else value,
   lambda args,value: "100644 blob dead\tformal" if args and args[0]=="ls-tree" and args[-1] in verifier.FORMAL else value,
   lambda args,value: value.replace("100644 blob","100755 blob") if args and args[0]=="ls-tree" and args[1]=="gate" and args[-1] in verifier.PATHS else value,
   lambda args,value: "wrong" if args and args[0]=="merge-base" else value,
   lambda args,value: "0"*40 if args[:2]==("rev-parse",f"{verifier.AS_CANDIDATE}^{{tree}}") else value,
   lambda args,value: value+"\nM\textra" if args[:4]==("diff","--name-status","--no-renames",verifier.AS_CANDIDATE) else value,
   lambda args,value: value.replace("M\t","R100\t",1) if args[:4]==("diff","--name-status","--no-renames",verifier.AS_CANDIDATE) else value,
   lambda args,value: value.replace("A\t","M\t",1) if args and args[0]=="diff-tree" else value,
  )
  for mutate in cases:
   def altered(repo,*args,**kwargs):return mutate(args,fake_git(repo,*args,**kwargs))
   with mock.patch.object(verifier,"git",side_effect=altered):
    with self.assertRaises(ValueError):verifier.verify_gate(Path("."),"gate",require_live=False)

if __name__=="__main__":unittest.main()
