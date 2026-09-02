"""Future R2024b-only TP0V runner; records are forbidden until a clean v3 candidate."""
from pathlib import Path
import hashlib, os, subprocess, tarfile
from verify_com_tp0v_current_asset_v3 import require
def safe_materialize(archive: Path, dest: Path, max_members=20000, max_bytes=100_000_000):
 raw=archive.read_bytes(); total=0; dest.mkdir(parents=True,exist_ok=False)
 with tarfile.open(archive) as t:
  members=t.getmembers(); require(len(members)<=max_members,'archive member budget')
  for m in members:
   p=Path(m.name); require(not p.is_absolute() and '..' not in p.parts and not m.issym() and not m.islnk(),'unsafe archive member')
   if m.isfile():
    total+=m.size; require(total<=max_bytes,'archive byte budget'); out=dest/p; out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(t.extractfile(m).read())
 return {'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'path_redacted':True}
def r2024b_identity(exe: Path, prefdir: Path) -> dict:
    require(exe.is_file(),'explicit MATLAB executable required')
    prefdir.mkdir(parents=True,exist_ok=False)
    p=subprocess.run([str(exe),'-batch',"disp(version('-release')); disp(version); disp(computer('arch'));"],capture_output=True,text=True,timeout=60,env={**os.environ,'MATLAB_PREFDIR':str(prefdir),'MW_DISABLE_CONNECTOR':'1'})
    lines=[x.strip() for x in p.stdout.splitlines() if x.strip()]
    require(p.returncode==0 and lines and lines[0]=='2024b','MATLAB release/runtime drift')
    b=exe.read_bytes(); return {'release':'R2024b','release_raw':'2024b','arch':lines[-1],'exe_bytes':len(b),'exe_sha256':hashlib.sha256(b).hexdigest(),'full_version_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'start_flags':['-batch'],'mw_disable_connector':'1','matlab_prefdir_isolated':True,'path_redacted':True}
