"""Verify the AS-06 ngspice result-parity harness preparation gate."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from pathlib import Path

AS_CANDIDATE="aea546510d345cd7e280e55897c027be872d759a"
AS_CANDIDATE_TREE="df99e5bb1c2381bb52fe0037b7b8fbb38b7c6cb9"
PREP_PARENT="0d57b36f965588bed3393d2a0a529e4d573a493c"
ORIGINAL_GATE="7e4adf14f453710c9b66a51d21ef2bf2e20ec192"
ORIGINAL_GATE_TREE="91c40ab332582c5c438768595392842ac3e54cee"
INTERPOSED=(
 "M\tcrates/sipi-agent-com-direct/src/package_vtf_v1.rs",
 "M\tcrates/sipi-agent-com-direct/src/run_v1.rs",
 "M\tcrates/sipi-com/src/search_loop_v1.rs",
 "M\tcrates/sipi-pybert-direct/src/legacy_runtime.rs",
 "M\tcrates/sipi-pybert-direct/src/simulation.rs",
 "M\tcrates/sipi-pybert-direct/tests/legacy_runtime.rs",
 "A\tdocs/baselines/audits/2026-08-29-com-02-04-result-surface.md",
)
PATHS=("tools/aggregate_as_06_ngspice_result_parity.py","tools/run_as_06_ngspice_result_parity.py","tools/test_verify_as_06_ngspice_result_parity.py","tools/verify_as_06_ngspice_result_parity.py")
FORMAL=("docs/baselines/as-06-ngspice-result-parity-run-01.v2.json","docs/baselines/as-06-ngspice-result-parity-run-02.v2.json","docs/baselines/as-06-ngspice-result-parity-aggregate.v2.json","docs/baselines/as-06-ngspice-result-parity.v2.yaml","docs/baselines/audits/2026-08-29-as-06-ngspice-result-parity-v2.md")
HARDENING_PATHS=("tools/run_as_06_ngspice_result_parity.py","tools/test_verify_as_06_ngspice_result_parity.py","tools/verify_as_06_ngspice_result_parity.py")

def git(repo,*args,raw=False):
 r=subprocess.run(["git","-C",str(repo),*args],check=True,capture_output=True)
 return r.stdout if raw else r.stdout.decode("ascii").strip()
def verify_gate(repo:Path,commit:str,require_live=True):
 resolved=git(repo,"rev-parse",commit);parents=git(repo,"show","-s","--format=%P",resolved).split()
 if git(repo,"rev-parse",f"{ORIGINAL_GATE}^{{tree}}")!=ORIGINAL_GATE_TREE or git(repo,"show","-s","--format=%P",ORIGINAL_GATE).split()!=[PREP_PARENT]: raise ValueError("original Stage1 gate identity drift")
 if git(repo,"merge-base",AS_CANDIDATE,PREP_PARENT)!=AS_CANDIDATE or git(repo,"rev-parse",f"{AS_CANDIDATE}^{{tree}}")!=AS_CANDIDATE_TREE: raise ValueError("AS candidate ancestry or tree drift")
 interposed=git(repo,"diff","--name-status","--no-renames",AS_CANDIDATE,PREP_PARENT).splitlines()
 if sorted(interposed)!=sorted(INTERPOSED): raise ValueError("interposed COM/PB path-status drift")
 if parents!=[ORIGINAL_GATE]: raise ValueError("hardening gate must directly follow original Stage1 gate")
 changed=git(repo,"diff-tree","--no-commit-id","--name-status","--no-renames","-r",ORIGINAL_GATE,resolved).splitlines()
 if sorted(changed)!=sorted(f"M\t{path}" for path in HARDENING_PATHS): raise ValueError("hardening gate changes are not exact three modifications")
 files=[]
 for path in PATHS:
  original=git(repo,"ls-tree",ORIGINAL_GATE,"--",path)
  if not original.startswith("100644 blob "): raise ValueError("original harness identity drift")
  entry=git(repo,"ls-tree",resolved,"--",path)
  if not entry.startswith("100644 blob "): raise ValueError("harness Git mode must be 100644")
  raw=git(repo,"show",f"{resolved}:{path}",raw=True);blob=git(repo,"rev-parse",f"{resolved}:{path}")
  if require_live and (repo/path).read_bytes()!=raw: raise ValueError("live harness differs from Git blob")
  files.append({"path":path,"blob":blob,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
 for path in FORMAL:
  if git(repo,"ls-tree",resolved,"--",path): raise ValueError("formal artifact entered prep gate")
 return {"valid":True,"commit":resolved,"tree":git(repo,"rev-parse",f"{resolved}^{{tree}}"),"candidate":{"commit":AS_CANDIDATE,"tree":AS_CANDIDATE_TREE},"prep_parent":PREP_PARENT,"original_gate":{"commit":ORIGINAL_GATE,"tree":ORIGINAL_GATE_TREE},"interposed":list(INTERPOSED),"as_production_drift":False,"changed_paths":list(HARDENING_PATHS),"original_first_introduction":True,"formal_absent":True,"files":files}
def main():
 p=argparse.ArgumentParser();p.add_argument("--repository",type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument("--prep-commit",required=True);a=p.parse_args()
 try: print(json.dumps(verify_gate(a.repository,a.prep_commit),sort_keys=True))
 except Exception as e: print(f"blocked: {e}",file=sys.stderr);return 1
 return 0
if __name__=="__main__":raise SystemExit(main())
