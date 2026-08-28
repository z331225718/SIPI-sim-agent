from __future__ import annotations
import copy,hashlib,json,subprocess,tempfile,unittest
from unittest import mock
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_as_06_ngspice_result_parity_formal as verifier
import test_verify_as_06_ngspice_result_parity as stage1

def write_bundle(root:Path):
 for path in (*verifier.REPORTS,verifier.AGGREGATE,verifier.MANIFEST,verifier.AUDIT):
  (root/path).parent.mkdir(parents=True,exist_ok=True)
 reports=[]
 for index,(run_id,challenge) in enumerate(verifier.RUNS):
  item=stage1.report(challenge,("a" if index==0 else "b")*64,run_id)
  item["candidate"]=copy.deepcopy(verifier.CANDIDATE);item["upstream"]=copy.deepcopy(verifier.UPSTREAM)
  path=root/verifier.REPORTS[index];path.write_text(json.dumps(item),encoding="utf-8");reports.append(path)
 stored=verifier.aggregate.aggregate(reports);(root/verifier.AGGREGATE).write_text(json.dumps(stored),encoding="utf-8")
 records={path:hashlib.sha256((root/path).read_bytes()).hexdigest() for path in (*verifier.REPORTS,verifier.AGGREGATE)}
 audit=verifier.audit_text(records);(root/verifier.AUDIT).write_text(audit,encoding="utf-8")
 formal={"commit":"formal","tree":"formal-tree","files":{path:{"blob":"b"*40,"sha256":"c"*64,"bytes":1} for path in verifier.GATE_PATHS}}
 manifest={"schema":"sipi.as-06-ngspice-result-parity-evidence.v2","status":"passed_scoped_external_observation","harness_gate":{"commit":verifier.GATE,"tree":verifier.GATE_TREE,"files":copy.deepcopy(verifier.HARNESS)},"formal_gate":formal,"candidate":copy.deepcopy(verifier.CANDIDATE),"upstream":copy.deepcopy(verifier.UPSTREAM),"records":records,"audit":{"path":verifier.AUDIT,"sha256":hashlib.sha256((root/verifier.AUDIT).read_bytes()).hexdigest()},"result":copy.deepcopy(verifier.RESULT),"claims":copy.deepcopy(verifier.CLAIMS)}
 (root/verifier.MANIFEST).write_text(verifier.yaml.safe_dump(manifest,sort_keys=False),encoding="utf-8")
 return manifest

def verify_synthetic(root:Path,patch_records=True):
 workspace=Path(__file__).resolve().parents[1]
 def raw(repo,*args):
  spec=args[-1]
  return subprocess.run(["git","-C",workspace,"show",spec],check=True,capture_output=True).stdout
 manifest=verifier.yaml.load((root/verifier.MANIFEST).read_text(),Loader=verifier.StrictLoader)
 patches=[mock.patch.object(verifier,"verify_record_commit",return_value={"formal_gate":"formal"}),mock.patch.object(verifier,"gate_binding",return_value=manifest["formal_gate"]),mock.patch.object(verifier,"archive"),mock.patch.object(verifier,"git",return_value=verifier.GATE_TREE),mock.patch.object(verifier,"git_raw",side_effect=raw)]
 if patch_records:patches.append(mock.patch.object(verifier,"RECORDS",manifest["records"]))
 with patches[0],patches[1],patches[2],patches[3],patches[4]:
  if patch_records:
   with patches[5]:return verifier.verify(root,root,"formal","record")
  return verifier.verify(root,root,"formal","record")

class Tests(unittest.TestCase):
 def test_complete_synthetic_future_bundle_and_field_mutations(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);write_bundle(root);self.assertTrue(verify_synthetic(root)["valid"])
  mutations=(
   lambda r:r.__setitem__("schema","wrong"),
   lambda r:r.__setitem__("run_id","wrong"),
   lambda r:r.__setitem__("caller_challenge","0"*64),
   lambda r:r.__setitem__("fresh_run_nonce",True),
   lambda r:r["toolchain_pre"]["cargo"].__setitem__("sha256","0"*64),
   lambda r:r["toolchain_post"]["cargo"].__setitem__("version_exit",True),
   lambda r:r["binary_pre"].__setitem__("bytes",True),
   lambda r:r["dependency_pre"].__setitem__("files",True),
   lambda r:r["physical"]["rust_waveform"].__setitem__("sha256","0"*64),
   lambda r:r["source_map"].__setitem__("sha256","0"*64),
   lambda r:r["inputs"].__setitem__("ngspice_sha256","0"*64),
   lambda r:r.__setitem__("candidate",{"commit":"coordinated"}),
   lambda r:r.__setitem__("upstream",{"commit":"coordinated"}),
  )
  for mutate in mutations:
   with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);manifest=write_bundle(root);path=root/verifier.REPORTS[0];item=json.loads(path.read_text());mutate(item);path.write_text(json.dumps(item))
    manifest["records"][verifier.REPORTS[0]]=hashlib.sha256(path.read_bytes()).hexdigest();(root/verifier.AUDIT).write_text(verifier.audit_text(manifest["records"]));manifest["audit"]["sha256"]=hashlib.sha256((root/verifier.AUDIT).read_bytes()).hexdigest();(root/verifier.MANIFEST).write_text(verifier.yaml.safe_dump(manifest,sort_keys=False))
    with self.assertRaises((ValueError,KeyError)):verify_synthetic(root)
 def test_coordinated_aggregate_manifest_and_audit_promotion_rejected(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);manifest=write_bundle(root);stored=json.loads((root/verifier.AGGREGATE).read_text());stored["claims"]["release_acceptance"]=True;(root/verifier.AGGREGATE).write_text(json.dumps(stored));manifest["records"][verifier.AGGREGATE]=hashlib.sha256((root/verifier.AGGREGATE).read_bytes()).hexdigest();(root/verifier.AUDIT).write_text(verifier.audit_text(manifest["records"])+"promoted\n");manifest["audit"]["sha256"]=hashlib.sha256((root/verifier.AUDIT).read_bytes()).hexdigest();(root/verifier.MANIFEST).write_text(verifier.yaml.safe_dump(manifest,sort_keys=False))
   with self.assertRaises(ValueError):verify_synthetic(root)
 def test_full_graph_rehash_rejected_without_record_constant_patch(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);write_bundle(root)
   with self.assertRaises(ValueError):verify_synthetic(root,patch_records=False)
 def test_duplicate_yaml_rejected(self):
  with self.assertRaises(ValueError):verifier.yaml.load("a: 1\na: 2\n",Loader=verifier.StrictLoader)
 def test_nonfinite_rejected(self):
  for value in (float("nan"),float("inf"),-float("inf")):
   with self.assertRaises(ValueError):verifier.finite({"x":value})
 def test_bool_is_not_integer_promotion(self):
  verifier.finite({"x":False})
  self.assertIs(type(verifier.CANDIDATE["bytes"]),int)
  self.assertIsNot(type(verifier.CANDIDATE["bytes"]),bool)
  self.assertFalse(verifier.typed_equal(True,1))
  self.assertFalse(verifier.typed_equal(0,0.0))
 def test_exact_keysets_reject_extra_missing(self):
  for value in ({"a":1,"b":2},{ }):
   with self.assertRaises(ValueError):verifier.exact(value,("a",),"fixture")
 def test_fixed_run_ids_and_challenges(self):
  self.assertEqual(verifier.RUNS,(("as06-formal-01","d413891862a3e7a7cefaec7a3a974e8d865d314e305d3371b650ce0f4d6ee836"),("as06-formal-02","fd0e621383bd9ad5b316125eeceb283eee8f9bd86894368a548a7d7cd6047056")))
 def test_gate_and_claims_are_closed(self):
  self.assertEqual(verifier.GATE,"927d9047315c6a88ec9497c452a5f6d5197210a0")
  self.assertTrue(verifier.CLAIMS["external_solver_scoped_observation"])
  self.assertFalse(any(value for key,value in verifier.CLAIMS.items() if key!="external_solver_scoped_observation"))
 def test_audit_requires_reciprocal_gate_and_nonclaims(self):
  self.assertIn(verifier.GATE,verifier.MARKERS)
  self.assertEqual(len(verifier.MARKERS),len(set(verifier.MARKERS)))
 def test_archive_identity_rejects_commit_tree_or_payload_drift(self):
  identity={"commit":"c","tree":"t","sha256":verifier.digest(b"archive"),"bytes":7}
  def git_identity(repo,*args):return b"c\n" if args[0]=="rev-parse" else b"t\n"
  def archive_run(*args,**kwargs):kwargs["stdout"].write(b"archive");return mock.Mock(returncode=0)
  with mock.patch.object(verifier,"git_raw",side_effect=git_identity),mock.patch.object(verifier.subprocess,"run",side_effect=archive_run):verifier.archive(Path("."),identity)
  bad=dict(identity);bad["sha256"]="0"*64
  with mock.patch.object(verifier,"git_raw",side_effect=git_identity),mock.patch.object(verifier.subprocess,"run",side_effect=archive_run):
   with self.assertRaises(ValueError):verifier.archive(Path("."),bad)
 def test_harness_and_source_map_are_fixed(self):
  self.assertEqual(set(verifier.HARNESS),{"tools/run_as_06_ngspice_result_parity.py","tools/aggregate_as_06_ngspice_result_parity.py","tools/verify_as_06_ngspice_result_parity.py","tools/test_verify_as_06_ngspice_result_parity.py"})
  self.assertTrue(all(len(value)==64 for value in verifier.HARNESS.values()))
 def test_nonce_is_not_fixed_but_aggregate_enforces_freshness(self):
  self.assertNotIn("nonce",repr(verifier.RUNS).lower())
  self.assertTrue(callable(verifier.aggregate.aggregate))
 def test_real_git_stage2_gate_positive_and_extra_path_negative(self):
  with tempfile.TemporaryDirectory() as raw:
   repo=Path(raw);subprocess.run(["git","init","-q",repo],check=True);subprocess.run(["git","-C",repo,"config","core.autocrlf","false"],check=True);subprocess.run(["git","-C",repo,"config","user.email","test@example.invalid"],check=True);subprocess.run(["git","-C",repo,"config","user.name","test"],check=True)
   (repo/"seed").write_text("seed\n")
   for path in verifier.HARNESS:
    target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(path+"\n")
   subprocess.run(["git","-C",repo,"add","."],check=True);subprocess.run(["git","-C",repo,"commit","-qm","stage1"],check=True)
   parent=subprocess.run(["git","-C",repo,"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip();tree=subprocess.run(["git","-C",repo,"show","-s","--format=%T",parent],check=True,capture_output=True,text=True).stdout.strip()
   prep_path="prep.txt";(repo/prep_path).write_text("prep\n");subprocess.run(["git","-C",repo,"add",prep_path],check=True);subprocess.run(["git","-C",repo,"commit","-qm","interposed"],check=True);prep=subprocess.run(["git","-C",repo,"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip();interposed=(f"A\t{prep_path}",)
   for path in verifier.GATE_PATHS:
    target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(__file__).resolve().parents[1].joinpath(path).read_bytes())
   subprocess.run(["git","-C",repo,"add",*verifier.GATE_PATHS],check=True);subprocess.run(["git","-C",repo,"commit","-qm","gate"],check=True);gate=subprocess.run(["git","-C",repo,"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
   with mock.patch.object(verifier,"GATE",parent),mock.patch.object(verifier,"GATE_TREE",tree),mock.patch.object(verifier,"PREP_PARENT",prep),mock.patch.object(verifier,"INTERPOSED",interposed):self.assertTrue(verifier.verify_gate(repo,gate)["valid"])
   for bad_parent,bad_interposed in ((prep,interposed+("A\textra",)),(prep,(f"M\t{prep_path}",)),(parent,interposed)):
    with mock.patch.object(verifier,"GATE",parent),mock.patch.object(verifier,"GATE_TREE",tree),mock.patch.object(verifier,"PREP_PARENT",bad_parent),mock.patch.object(verifier,"INTERPOSED",bad_interposed):
     with self.assertRaises(ValueError):verifier.verify_gate(repo,gate)
   self.assertEqual(verifier.gate_binding(repo,gate)["commit"],gate)
   for path in verifier.FORMAL:
    target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(path+"\n")
   subprocess.run(["git","-C",repo,"add",*verifier.FORMAL],check=True);subprocess.run(["git","-C",repo,"commit","-qm","record"],check=True);record=subprocess.run(["git","-C",repo,"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
   with mock.patch.object(verifier,"GATE",parent),mock.patch.object(verifier,"GATE_TREE",tree),mock.patch.object(verifier,"PREP_PARENT",prep),mock.patch.object(verifier,"INTERPOSED",interposed):self.assertTrue(verifier.verify_record_commit(repo,gate,record)["valid"])
   (repo/"extra").write_text("x\n");subprocess.run(["git","-C",repo,"add","extra"],check=True);subprocess.run(["git","-C",repo,"commit","-qm","extra"],check=True);bad=subprocess.run(["git","-C",repo,"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
   with mock.patch.object(verifier,"GATE",parent),mock.patch.object(verifier,"GATE_TREE",tree),mock.patch.object(verifier,"PREP_PARENT",prep),mock.patch.object(verifier,"INTERPOSED",interposed):
    with self.assertRaises(ValueError):verifier.verify_gate(repo,bad)
if __name__=="__main__":unittest.main()
