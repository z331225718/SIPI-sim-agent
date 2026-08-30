import copy, io, json, subprocess, sys, tarfile, tempfile, unittest
from pathlib import Path
from tools.verify_p5_06_original13_fresh_matrix import Error, WORKBOOKS, verify
from tools.run_p5_06_original13_fresh_matrix import ADAPTER, CANDIDATE, CHANNELS, CONFIG_PATHS, PROJECTION_SOURCES, UPSTREAM, inventory, materialize, runtime_projection, worker_environment

def sample():
    n = "a" * 64
    channels = [{"role":role,"path":path,"bytes":size,"sha256":sha} for role,path,size,sha in CHANNELS]
    receipt = lambda role: {"role":role,"executable":role+".exe","file_sha256":n,"version_sha256":n,"path_redacted":True}
    matlab = receipt("matlab"); matlab.update({"release":"R2026a","launch_mode":"python_engine_noFigureWindows_singleCompThread"})
    source = {"upstream":{"commit":UPSTREAM[0],"tree":UPSTREAM[1],"archive_sha256":UPSTREAM[2],"archive_bytes":UPSTREAM[3]},"candidate":{"commit":CANDIDATE[0],"tree":CANDIDATE[1],"archive_sha256":CANDIDATE[2],"archive_bytes":CANDIDATE[3]},"adapter":{"path":ADAPTER[0],"bytes":ADAPTER[1],"sha256":ADAPTER[2],"git_blob":ADAPTER[3]},"projection_sources":[{"path":p,"bytes":b,"sha256":s,"git_blob":g} for p,b,s,g in PROJECTION_SOURCES],"rust_binary":{"path":"target/release/sipi-com-direct-run.exe","bytes":1,"sha256":n},"toolchain":{"cargo":receipt("cargo"),"rustc":receipt("rustc"),"uv":receipt("uv"),"matlab":matlab,"python":receipt("python")}}
    wb = WORKBOOKS[CONFIG_PATHS[0]]
    record = {"workbook_index":0,"workbook":{"path":CONFIG_PATHS[0],"bytes":wb[0],"sha256":wb[1]},"status":"candidate_timeout","exit_code":124,"detail_sha256":n,"source_inventory_unchanged":True,"config_materialization":{"comparison":"not_run_for_rust_result_replay"},"case_count":0,"metrics":[]}
    return {"schema":"sipi.p5-06.original13-fresh-run.v1","engine":"rust","run_id":"run-"+n,"nonce":n,"status":"diagnostic","duration_seconds":1.0,"selection_count":1,"source":source,"channels":channels,"records":[record],"claims":{"acceptance":False,"historical_python_used":False,"s_parameter_fit":False,"one_final_fd_to_td_impulse":True}}

class Tests(unittest.TestCase):
    def reject(self, mutate):
        value = sample(); mutate(value)
        with self.assertRaises(Error): verify(value)
    def test_baseline(self): self.assertTrue(verify(sample()))
    def test_materialize_rejects_links_and_traversal(self):
        for name,kind in (("link",tarfile.SYMTYPE),("../escape",tarfile.REGTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                archive=Path(directory)/"input.tar"
                with tarfile.open(archive,"w") as output:
                    item=tarfile.TarInfo(name);item.type=kind
                    if kind==tarfile.SYMTYPE:item.linkname="target"
                    else:item.size=1
                    output.addfile(item,io.BytesIO(b"x") if kind==tarfile.REGTYPE else None)
                with self.assertRaises(RuntimeError):materialize(archive,Path(directory)/"out")
    def test_worker_import_does_not_mutate_source_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"upstream-source";package=source/"src/pkg";package.mkdir(parents=True);(package/"__init__.py").write_text("VALUE=1\n",encoding="ascii")
            before=inventory(source/"src");env=worker_environment(source,Path(r"C:\Program Files\MATLAB\R2026a\bin\matlab.exe"));env["PYTHONPATH"]=str(source/"src")
            self.assertEqual(env["MW_DISABLE_CONNECTOR"],"1")
            self.assertTrue(Path(env["MATLAB_PREFDIR"]).is_dir())
            self.assertNotEqual(Path(env["MATLAB_PREFDIR"]).parent,source)
            subprocess.run([sys.executable,"-c","import pkg"],env=env,check=True,capture_output=True)
            self.assertEqual(inventory(source/"src"),before)
    def test_final_surface_matlab_harness_is_scalar_only_and_staged(self):
        harness=Path(__file__).with_name("sipi_com_final_surface_oracle_v3.m").read_text(encoding="ascii")
        runner=Path(__file__).with_name("run_p5_06_original13_fresh_matrix.py").read_text(encoding="utf-8")
        self.assertIn("'oracle_entered'",harness)
        self.assertIn("'core_returned'",harness)
        self.assertIn("'summary_written'",harness)
        self.assertIn("'oracle_exception'",harness)
        self.assertIn("com_ieee8023_480(config_path, num_fext, num_next, varargin{:});",harness)
        self.assertIn("final_scalar_metrics_from_csv",harness)
        self.assertNotIn("matlab_oracle.mat",harness)
        self.assertNotIn("save(",harness)
        self.assertIn("sipi_com_final_surface_oracle_v3",runner)
        self.assertIn('"run_nonce":nonce',runner)
    def test_runtime_projection_excludes_report_metadata_and_normalizes_sweeps(self):
        document={"parameters":{"CTLE_fp1":[[21.25]],"f_HP_P":[[]],"consumed":2.0,"report":3.0},"options":{"BREAD_CRUMBS":1.0,"DEBUG":1.0}}
        projected=runtime_projection(document,{"CTLE_fp1","f_HP_P","consumed"},{"DEBUG"})
        self.assertEqual(projected,{"parameters":{"CTLE_fp1":[21.25],"f_HP_P":[],"consumed":2.0},"options":{"DEBUG":1.0}})
        scalar=copy.deepcopy(document);scalar["parameters"]["CTLE_fp1"]=21.25;scalar["parameters"]["f_HP_P"]=[]
        self.assertEqual(runtime_projection(scalar,{"CTLE_fp1","f_HP_P","consumed"},{"DEBUG"}),projected)
        document["parameters"]["CTLE_fp1"]=[[True]]
        with self.assertRaises(ValueError):runtime_projection(document,{"CTLE_fp1","f_HP_P","consumed"},{"DEBUG"})
    def test_mutations(self):
        self.reject(lambda x:x["channels"].reverse())
        self.reject(lambda x:x["channels"][0].__setitem__("sha256","0"*63))
        self.reject(lambda x:x["records"][0]["workbook"].__setitem__("path",r"C:\secret.xlsx"))
        self.reject(lambda x:x["claims"].__setitem__("historical_python_used",True))
        self.reject(lambda x:x.__setitem__("nonce","b"*64))
        self.reject(lambda x:x["source"]["candidate"].__setitem__("commit","0"*40))
        self.reject(lambda x:x["source"]["adapter"].__setitem__("sha256","0"*64))
        self.reject(lambda x:x["source"]["toolchain"]["cargo"].__setitem__("role","rustc"))
        self.reject(lambda x:x["records"][0].__setitem__("status","passed"))
        self.reject(lambda x:x["records"][0].__setitem__("source_inventory_unchanged",False))
    def full(self, engine, marker):
        value = sample(); value["engine"]=engine; value["nonce"]=f"{marker:064x}"; value["run_id"]=f"run-{engine}-{value['nonce']}"; value["status"]="fresh_matrix_run"; value["selection_count"]=13
        counts=[2,2,2,1,1,1,2,2,3,3,3,3,3]; records=[]
        for index,count in enumerate(counts):
            wb=WORKBOOKS[CONFIG_PATHS[index]]; metrics=[]
            for case_index in range(count): metrics.append({name:float(index+case_index) for name in (("ERL",) if count==1 else tuple(__import__('tools.run_p5_06_original13_fresh_matrix',fromlist=['METRICS']).METRICS))})
            materialization={"comparison":"not_run_for_rust_result_replay"} if engine=="rust" else {"comparison":"equal","first_difference":None,"pinned_sha256":"d"*64,"rust_sha256":"d"*64,"parameter_shape":[100,10],"parameter_slot_digest":"e"*64,"parameter_mat_bytes":100,"parameter_mat_sha256":"f"*64}
            records.append({"workbook_index":index,"workbook":{"path":CONFIG_PATHS[index],"bytes":wb[0],"sha256":wb[1]},"status":"passed","exit_code":0,"detail_sha256":"c"*64,"source_inventory_unchanged":True,"config_materialization":materialization,"case_count":count,"metrics":metrics})
        value["records"]=records; return value
    def aggregate(self, reports):
        directory=tempfile.TemporaryDirectory(); root=Path(directory.name); paths=[]
        for index,report in enumerate(reports):
            path=root/f"r{index}.json";path.write_text(json.dumps(report),encoding="utf-8");paths.append(path)
        output=root/"aggregate.json";command=[sys.executable,str(Path(__file__).with_name("aggregate_p5_06_original13_fresh_matrix.py"))]
        for path in paths:command.extend(["--report",str(path)])
        command.extend(["--output",str(output)]);result=subprocess.run(command,capture_output=True);payload=json.loads(output.read_text()) if output.exists() else None;directory.cleanup();return result,payload
    def test_aggregate_source_status_slot_value_and_hash_gates(self):
        reports=[self.full("matlab",1),self.full("matlab",2),self.full("rust",3),self.full("rust",4)]
        result,payload=self.aggregate(reports);self.assertEqual(result.returncode,0);self.assertEqual(payload["status"],"accepted_stage1")
        mutated=copy.deepcopy(reports);mutated[0]["source"]["toolchain"]["cargo"]["role"]="rustc";self.assertNotEqual(self.aggregate(mutated)[0].returncode,0)
        mutated=copy.deepcopy(reports);mutated[2]["records"][0]["status"]="candidate_branch_missing";self.assertNotEqual(self.aggregate(mutated)[0].returncode,0)
        mutated=copy.deepcopy(reports);mutated[2]["records"][0]["metrics"][0].pop("COM_dB");self.assertNotEqual(self.aggregate(mutated)[0].returncode,0)
        mutated=copy.deepcopy(reports);mutated[2]["records"][0]["metrics"][0]["COM_dB"]+=1e-6;self.assertEqual(self.aggregate(mutated)[1]["status"],"blocked")
        duplicated=[reports[0],reports[0],reports[2],reports[3]];self.assertNotEqual(self.aggregate(duplicated)[0].returncode,0)
    def test_materialization_drift_is_valid_report_but_not_accepted(self):
        report=self.full("matlab",1);record=report["records"][0];record["status"]="config_materialization_drift";record["config_materialization"]["comparison"]="drift";record["config_materialization"]["first_difference"]="parameters.CTLE_fp1";record["config_materialization"]["rust_sha256"]="9"*64
        self.assertTrue(verify(report))
        reports=[report,self.full("matlab",2),self.full("rust",3),self.full("rust",4)]
        self.assertNotEqual(self.aggregate(reports)[0].returncode,0)
        report["records"][0]["config_materialization"]["parameter_slot_digest"]="0"*63
        with self.assertRaises(Error):verify(report)
if __name__ == "__main__": unittest.main()
