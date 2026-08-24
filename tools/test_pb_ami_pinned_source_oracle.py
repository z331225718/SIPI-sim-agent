import ast
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
class PinnedSourceOracleTests(unittest.TestCase):
    def test_importlib_wrapper_module_path_mutation_is_rejected(self):
        from tools import pb_ami_pinned_source_oracle as oracle

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "archive"
            root.mkdir()
            forged = Path(temp) / "forged_parser.py"
            forged.write_bytes(b"forged")
            with self.assertRaisesRegex(RuntimeError, "module archive path mismatch"):
                oracle._validate_imported_modules(
                    root,
                    {"parser": ("PyAMI/src/pyibisami/ami/parser.py", types.SimpleNamespace(__file__=str(forged)))},
                )

    def test_clean_pinned_source_oracle_uses_caller_runtime(self):
        root = Path(__file__).resolve().parents[1]
        pinned = root.parent / "Py-bert-agent" / ".venv" / "Scripts" / "python.exe"
        if not pinned.is_file():
            self.skipTest("pinned PyBERT venv unavailable")
        process = subprocess.run(
            [str(pinned), str(Path(__file__).with_name("pb_ami_pinned_source_oracle.py"))],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=60,
            check=True,
        )
        result = ast.literal_eval(process.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "passed_external_python_oracle")
        self.assertEqual(result["pinned_commit"], "5bf6d7ea0ace261891aaeb611ffc1c267e160afe")
        self.assertEqual(result["pinned_tree"], "5faef6bdb341d444ad65d82a11c0018b15805e24")
        self.assertEqual(result["process_policy"], {"timeout_seconds": 30, "timeout_action": "kill_and_reap"})
        self.assertEqual(result["archive_sha256"], "ee8ff82477f38e5d119d4c6e037b34243fae7ef942e5ed46f13e6b80843a839b")
        self.assertEqual(result["archive_bytes"], 3041280)
        self.assertEqual(
            result["archive_source_sha256"]["models/ibisami/example_rx.ami"],
            "876c9653d2d038781ece3167646c642623cfa49f8a0aa32edd1f3b10eff21904",
        )
        self.assertEqual(
            result["bytes"],
            "(example_rx (AMI_Version \"5.1\")(Init_Returns_Impulse True)(GetWave_Exists True)(ctle_mode 1)(ctle_freq 5000000000.0)(ctle_mag 0.0)(ctle_bandwidth 12000000000.0)(ctle_dcgain 0.0)(dfe_mode 0)(dfe_ntaps 5)(dfe_tap1 0.0)(dfe_tap2 0.0)(dfe_tap3 0.0)(dfe_tap4 0.0)(dfe_tap5 0.0)(dfe_vout 1.0)(dfe_gain 0.1)(debug (dbg_enable False) (dump_dfe_adaptation False) (dump_adaptation_input False)))",
        )
        self.assertEqual(result["stage_values"]["Init_Returns_Impulse"], True)
        self.assertEqual(result["git_version"], "git version 2.54.0.windows.1")
        self.assertEqual(result["git_executable"], r"C:\Program Files\Git\cmd\git.exe")
        self.assertEqual(result["git_executable_pre"], result["git_executable_post"])
        self.assertEqual(result["python_executable"], r"C:\Users\z3312\code\Py-bert-agent\.venv\Scripts\python.exe")
        self.assertEqual(result["python_executable_pre"], result["python_executable_post"])
        self.assertEqual(
            {name: (item["version"], item["bytes"], item["sha256"]) for name, item in result["dependencies"].items()},
            {
                "parsec": ("3.17", 29999, "d9fe03a63fb2e6e24d687ea939c9147de65377644105e59e45ac5ee96b88c8e2"),
                "numpy": ("2.2.6", 23016, "ad238e76e8c6fbd56a19e6c894864cf466bd2ed76004cac89e78c019fa625607"),
                "scipy": ("1.15.3", 4614, "68d789d0eea2912c40cb75119b50579aac07ab30814f551c8ab24876bb3d724a"),
            },
        )
        self.assertEqual(
            {name: (item["path"], item["bytes"], item["git_blob"], item["git_source_sha256"], item["archive_present"])
             for name, item in result["module_files"].items()},
            {
                "parser": ("PyAMI/src/pyibisami/ami/parser.py", 30072, "23389fa558291ef2a06dff1c7cb5ebcaa864a0a4", "7ab52c1e03893cdd496a4db7672b3213a0d1eec5d2b746a98e9011aa03bf3a7c", True),
                "parameter": ("PyAMI/src/pyibisami/ami/parameter.py", 11749, "201ed14ef561392d46f385d80e0d3954b0dc67d8", "95bc003de3a5abd73bfa32f4b5a1db1c0c7d511c5f8cea11d92a967e54c76908", True),
                "model": ("PyAMI/src/pyibisami/ami/model.py", 29122, "4cfa4ec87aed1f5caece871271aa3a587bcae21f", "bf24cff1140e83ec46a8a6c9a5482151cffa90d516dfa056f639893b280e3787", True),
                "ibisami": ("src/pybert/utility/ibisami.py", 5694, "9f1fb3b1496fd192b77207ffcecc4b2478d5f64e", "14e1ac37c9673c21bc3bb6c75cf67d1483f658fb6d668b9dd1066693c6613c79", True),
            },
        )
        for name, relative in {
            "parser": "PyAMI/src/pyibisami/ami/parser.py",
            "parameter": "PyAMI/src/pyibisami/ami/parameter.py",
            "model": "PyAMI/src/pyibisami/ami/model.py",
            "ibisami": "src/pybert/utility/ibisami.py",
        }.items():
            module_file = result["module_files"][name]["module_file"].replace("\\", "/")
            self.assertIn("/archive/", module_file)
            self.assertTrue(module_file.endswith(relative))


if __name__ == "__main__":
    unittest.main()
