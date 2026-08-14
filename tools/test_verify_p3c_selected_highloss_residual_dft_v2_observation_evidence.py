from __future__ import annotations
import copy, importlib.util, unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("dft", ROOT / "tools/verify_p3c_selected_highloss_residual_dft_v2_observation_evidence.py")
assert SPEC and SPEC.loader
V=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(V)
class Tests(unittest.TestCase):
 def test_valid_and_mutations(self):
  doc=yaml.safe_load((ROOT / "docs/baselines/p3c-selected-highloss-residual-dft-v2-observation-evidence.v1.yaml").read_text(encoding="utf-8")); self.assertTrue(V.verify(doc)["valid"])
  for path, value in ((["admission", "selected_highloss_waveform_only_profile_accepted"], True), (["external_observation", "fixed_dft", "window"], "hann"), (["external_observation", "frequency_nrmse_bits"], "0"*16)):
   changed=copy.deepcopy(doc); cursor=changed
   for key in path[:-1]: cursor=cursor[key]
   cursor[path[-1]]=value
   with self.assertRaises(V.VerificationError): V.verify(changed, current=False)
if __name__ == "__main__": unittest.main()
