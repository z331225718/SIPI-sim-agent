"""Verify that M1 baseline conversion is lossless and cannot advertise capabilities."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from jsonschema import Draft202012Validator
from pathlib import Path
R=Path(__file__).resolve().parents[1]
SRC=R/'docs/baselines/capability-inventory.yaml'; OUT=R/'docs/baselines/capabilities.baseline.v1.json'; SCHEMA=R/'schemas/capabilities-baseline.v1.schema.json'
KEYS=["operation","payload_schema","engine_instance","behavior_profile","platform.os","platform.architecture","execution_mode"]
CAPABILITY_FIELDS={"id", "operation", "payload_schema", "engine_instance", "behavior_profile", "platform", "execution_mode", "role", "implementation_state", "evidence_state", "release_channel", "enforcement", "required_fixtures", "optional_fixtures", "evidence", "blockers"}
def q(v,m):
 if not v: raise ValueError(m)
def main():
 subprocess.run([sys.executable,'-B','tools/verify_m0_capability_inventory.py'],cwd=R,check=True)
 raw=json.loads(SRC.read_text()); out=json.loads(OUT.read_text())
 Draft202012Validator(json.loads(SCHEMA.read_text())).validate(out)
 q(out['schema']=='sipi.capabilities-baseline.v1' and out['status']=='baseline_nonpublic','schema/status')
 q(not out['runtime_consumable'] and not out['advertise'] and not out['default_auto_eligible'],'baseline promotion')
 q(out['source']['sha256']==hashlib.sha256(SRC.read_bytes()).hexdigest().upper(),'source hash')
 q(out['capability_key_fields']==KEYS,'capability key fields')
 q(out['source']['observed_metadata']=={k:raw[k] for k in ('status','schema_frozen','runtime_consumable','advertise','policy')},'metadata loss')
 q(out['catalogs']=={k:raw[k] for k in ('sources','environments','legacy_artifacts','instances')},'catalog loss')
 q(out['unmapped_capability_gaps']==raw['unmapped_capability_gaps'] and out['non_claims']==raw['non_claims'],'gap/non-claim loss')
 q(len(out['capabilities'])==len(raw['capabilities']),'capability count')
 seen=set()
 for old,new in zip(raw['capabilities'],out['capabilities']):
  q(set(old)==CAPABILITY_FIELDS,'source capability fields')
  q(new['source_inventory_id']==old['id'],'id mapping')
  q(new['key']=={'operation':old['operation'],'payload_schema':old['payload_schema'],'engine_instance':old['engine_instance'],'behavior_profile':old['behavior_profile'],'platform':{'os':'windows','architecture':'x86_64','source_literal':old['platform']},'execution_mode':old['execution_mode']},'key mapping')
  q((new['role'],new['implementation_state'],new['evidence_state'],new['release_channel'],new['enforcement_state'])==(old['role'],old['implementation_state'],old['evidence_state'],old['release_channel'],old['enforcement']),'state loss')
  q(new['fixtures']=={'required':old['required_fixtures'],'optional':old['optional_fixtures']} and new['evidence_refs']==[old['evidence']] and new['blockers']==old['blockers'],'evidence loss')
  q(new['key']['platform']=={'os':'windows','architecture':'x86_64','source_literal':'windows-x86_64'},'platform mapping')
  key=tuple(new['key'][x] if x in new['key'] else new['key']['platform'][x.split('.')[1]] for x in KEYS); q(key not in seen,'duplicate key'); seen.add(key)
  q(new['evidence_state']!='certified' and new['release_channel']!='stable' and new['enforcement_state']!='hard','capability promotion')
 print('capabilities.baseline.v1.json: valid nonpublic lossless baseline')
if __name__=='__main__':
 try: main()
 except (KeyError,TypeError,ValueError,subprocess.CalledProcessError) as e: print(f'baseline invalid: {e}',file=sys.stderr);raise SystemExit(1)
