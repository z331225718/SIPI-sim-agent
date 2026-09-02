import copy, importlib.util, unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('v3',Path(__file__).with_name('verify_com_tp0v_current_asset_v3.py')); v=importlib.util.module_from_spec(s); s.loader.exec_module(v)
class Tests(unittest.TestCase):
 def setUp(self): self.d=__import__('yaml').safe_load(v.MANIFEST.read_text())
 def bad(self,f):
  d=copy.deepcopy(self.d); f(d)
  with self.assertRaises(ValueError): v.validate(d)
 def test_valid(self): v.validate(self.d)
 def test_prefix_rejected(self): self.bad(lambda d:d['matlab'].update(required_release='R2024'))
 def test_raw_rejected(self): self.bad(lambda d:d['matlab'].update(required_release_raw='2026a'))
 def test_path_fallback_rejected(self): self.bad(lambda d:d['matlab'].update(executable_mode='path'))
 def test_candidate_rejected(self): self.bad(lambda d:d['candidate'].update(commit='0'*40))
 def test_unknown_status_rejected(self): self.bad(lambda d:d.update(status='candidate_bound_pending_r2024b_smoke'))
if __name__=='__main__': unittest.main()
