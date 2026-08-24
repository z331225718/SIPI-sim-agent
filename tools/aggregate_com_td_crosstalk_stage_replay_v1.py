"""Aggregate two independent scoped TDMODE stage reports."""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from verify_com_td_crosstalk_stage_replay_v1 import verify_reports_for_aggregation, verify_aggregate, aggregate_hash
from com_erl_exact_profile_replay_v3_support import sha256_file
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    m=json.loads(a.manifest.read_text(encoding="utf-8")); paths=[Path(x) for x in m["reports"]]; reports=verify_reports_for_aggregation(paths,m)
    aggregate={"schema":m["schema"]+".aggregate","status":"matched","matched":True,"report_sha256":[sha256_file(x) for x in paths],"run_ids":[r["run_id"] for r in reports],"candidate":{k:m["candidate"][k] for k in ("commit","tree","archive_sha256")},"upstream":{k:m["upstream"][k] for k in ("commit","tree","archive_sha256")}}
    aggregate["aggregate_sha256"]=aggregate_hash(aggregate); a.output.parent.mkdir(parents=True,exist_ok=True); temporary=a.output.with_name(a.output.name+".tmp"); temporary.write_text(json.dumps(aggregate,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(temporary,a.output); m["aggregate"]["sha256"]=sha256_file(a.output); manifest_tmp=a.manifest.with_name(a.manifest.name+".tmp"); manifest_tmp.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n",encoding="utf-8"); os.replace(manifest_tmp,a.manifest); verify_aggregate(aggregate,paths,reports,m,a.output); print(json.dumps({"status":"matched","aggregate_sha256":sha256_file(a.output)},sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(main())
