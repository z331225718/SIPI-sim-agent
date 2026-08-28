import argparse, hashlib, json, math, re, subprocess, tempfile, time
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
CANDIDATE = ("af518684936f8656eda61288abe2647f7d909ea4", "e49c50407557806c4addae103acbfd576b01527e", "3098bb432d8c00c4c65c058cf0f325172112de6c24fb5e55127688d8e147d990", 54_650_880)
PREP = ("90dea971a1661cf6ae0b7f71aab12b84f6eb241c", "e7eb1134f0061e586f117058d25a5298e2d7d799")
PREP_PARENT = ("1e2f1be2d9be730ca38cf21ce8393de02c295f6a", "2bd39e64b193e79cd0a57eea0d33e06bbe54f383")
UPSTREAM = ("5272ffe74702cd585054d975559b06f8afae7b6e", "7094ab6e84989b218730c52432c70da10261f8ea", "5f3f17e19edc07cf6498c9bfea20b8691082e2c05364b4462bc54df8549d0a04")
UPSTREAM_DECLARED_ARCHIVE = "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf"
PREP_BLOBS = {
    "docs/baselines/audits/2026-08-29-com-02-04-result-surface.md": "d01e6db8f09d3c7894e4624013067ae28a73c36d",
    "tools/com_direct_semantic_replay.py": "19bf336376fbb148f3136258bcbd356342e956d5",
    "tools/com_direct_semantic_replay_v2.py": "d55c9c9d1e8381be3cac218b7cb38d5f45018a47",
    "tools/test_com_direct_semantic_replay_prep.py": "4fcf50777afd67c89640a1f65ef45728bd48acc0",
}
PREP_RAW = {
    "docs/baselines/audits/2026-08-29-com-02-04-result-surface.md": (4970, "966fdf45af8226b4509b269020cb4f35030bd55e7ea03e7780db9394dba4b2ac"),
    "tools/com_direct_semantic_replay.py": (28358, "a73d857f3baeb59ad533f72f33c961d6e6384e241e42788d20c0221b38b8a660"),
    "tools/com_direct_semantic_replay_v2.py": (16536, "ed89117b623d0cf47d168bdddfa1412515ac8716059e761d34e220d539923a6f"),
    "tools/test_com_direct_semantic_replay_prep.py": (9881, "d8a366aa20602d787d93850c7769d1aa5c8653d9be2d0e85c2e97fbe5121e281"),
}
INTERPOSED_FILES = {
    "docs/baselines/as-06-ngspice-result-parity-aggregate.v2.json", "docs/baselines/as-06-ngspice-result-parity-run-01.v2.json",
    "docs/baselines/as-06-ngspice-result-parity-run-02.v2.json", "docs/baselines/as-06-ngspice-result-parity.v2.yaml",
    "docs/baselines/audits/2026-08-29-as-06-ngspice-result-parity-v2.md", "tools/test_verify_as_06_ngspice_result_parity_formal.py",
    "tools/verify_as_06_ngspice_result_parity_formal.py",
}
RUNS = (
    ("com-02", 1, "com02-formal-1", "62940bae93c0e6e0691ce5fe045b2b952a9b7348dd6601975852ad3031062bd7"),
    ("com-02", 2, "com02-formal-2", "573194e6b07f08de69133ba9041c73778ffef7b5ab1be374168ba66ee3e8d07e"),
    ("com-04", 1, "com04-formal-1", "2e47a945d8bb4932aff2cf15530f586a2942cdf298cf549b756829b33864919c"),
    ("com-04", 2, "com04-formal-2", "f801ccbe9c1fe1d4578fc240b6041d1a106b3cbe727ec44a0208badc637136f7"),
)
REPORT_KEYS = {"candidate", "mode", "parity", "payloads_committed", "portable_semantic_branches", "prep_source_inventory", "replay_count", "replays", "run_id", "scenario_count", "schema", "semantic_payload_fields", "semantic_replays_identical", "source", "unsupported_fail_closed", "upstream"}
INVENTORY_KEYS = {"build", "fixture", "fresh_run_index", "helper", "nonce", "run_id", "runner", "source_probe", "toolchain", "v2_wrapper"}
REPLAY_KEYS = {"exit_code", "mode", "scenario_count", "scenarios", "semantic", "semantic_sha256"}
SCENARIO_KEYS = {"artifact_files", "binary_schema", "exit_code", "result_schema", "scenario", "semantic", "semantic_sha256", "source_revision"}
SCENARIOS = ("base", "fd_to_td", "mixed_mode", "fext_next", "equalization", "tdiln", "search", "calibration", "mmse", "rx_ffe_search")
SOURCE_KEYS = {"commit", "declared_license", "reachable_paths", "repository", "tree"}
UPSTREAM_KEYS = {"archive_sha256", "commit", "declared_license", "materialization", "repository", "runtime_executed", "source_map", "tree"}
CANDIDATE_KEYS = {"archive_bytes", "archive_sha256", "binary", "binary_bytes", "binary_sha256", "commit", "materialization", "status", "tree"}
BUILD_KEYS = {"archive_sha256", "binary", "candidate_execution_observations", "command", "returncode", "rustc_wrapper_cleared", "source_commit", "source_mode", "source_tree", "stderr_sha256", "stdout_sha256", "timed_out", "timeout_seconds"}
FIXTURE_KEYS = {"corpus_sha256", "generator", "inputs", "scenario_count"}
TOOLCHAIN_KEYS = {"cargo", "path_redacted", "rustc"}
PROBE_KEYS = {"s2p_forbids_matched_kernel", "s2p_uses_validated_fd_to_td_leaf", "s4p_forbids_matched_kernel", "s4p_uses_validated_fd_to_td_leaf", "s_parameter_fit", "source", "source_sha256"}
PARITY_KEYS = {"external_blockers", "numeric_upstream_parity_claim", "status"}
SEMANTIC_KEYS = {"case_index", "channels", "crosstalk_inputs", "metrics", "portable_branches", "report_manifest", "scenario", "waveform", "workflow"}
SHAPES = {
    "source.com-02": "077bf732d40948b3735050ebe6cab50b7c241c00f949316f09d821adc929a8d0", "source.com-04": "226462422490290dee132f7099bf4bf5396ed833ab27887cac3c92dd6f766f84",
    "upstream": "7a88b415bc75173c1a1edb216593e0e9fb3c2c436185166933d24fc72e1a8f7d", "candidate": "fcec9c8df50323a8b582bce10f4efc97fd961a457cf28292f3bb4b87567921c4", "parity": "8b2ff5b714663f1c8d8e36d79b9df5b96d37c69757dea787c8bcc07a5aac977a",
    "build": "22dc19cfc0a7b310a10c80a8c29863421b1c82339c70a140ef95d5ac0c215a6a", "fixture": "c8d465ea7b6564d29b5863ea7e35685002d21e80691414c7fe66233d268d74ac", "toolchain": "41cd4cc8f73b3fb9dd243f73af301d8b07160228562b5ef80f3724ccfe9a288c", "source_probe": "10b237b3cd0262cc44f5db9d094a62e2e9d7a89cc7af19b6c9b882fdb78aa626",
}
SEMANTIC_SHAPES = dict(zip(SCENARIOS, ("1a4a1cbd0cbffc90e1c118acf5f7f8a27ef94ec736ba6c6bb721c6ab2b5dd7bf", "b9d8d1656937aec341b017b227b04cf3e479e7df984aedbab9877b7c6089badc", "1c18d43a2b4f7ccf5646875341b0172047e1cd3a1c2e9f85f54210050f6e83a7", "18818e8dc1b0b57d06edf1e412341c6474d5e0c398dbd34e399eacfc80539dfa", "f4245cfb2c021ef7d1dfa1f8ce7932138256b0d22754a9dc9e3b02d857249d68", "7701227c8003299711b60ad601236292261f787375429d49a583648fac1d3ca7", "7e623dab041b8383d058c9db2ef7f8608d39d279135199cafa8f583d10935e96", "7cb8c921ae7084db34342cb697255e488574ad07e1eb6c6003c33b00c955bc29", "5d2ac841894c4de83c2c7b6d3be17c232e2931f8f56697a065690ab47dc4a63b", "10b865981141757fd2c9692dc3b3f2260d6374fb913f423680347c5c648e7785")))
SOURCE_PATHS = ["src/agent_com/api.py", "src/agent_com/pipeline.py", "src/agent_com/network/mixed_mode.py", "src/agent_com/signal/interpolation.py", "src/agent_com/signal/fd_to_td.py", "src/agent_com/equalization/apply.py", "src/agent_com/equalization/ctle.py", "src/agent_com/equalization/rx_ffe.py", "src/agent_com/equalization/search.py", "src/agent_com/equalization/mmse.py", "src/agent_com/equalization/fvlms_rxffe.py", "src/agent_com/equalization/tx_ffe.py", "src/agent_com/equalization/dfe.py", "src/agent_com/signal/filters.py", "src/agent_com/noise/discrete_pdf.py", "src/agent_com/metrics/com.py", "src/agent_com/metrics/tdiln.py", "src/agent_com/runtime.py", "src/agent_com/calibration.py", "src/agent_com/legacy_csv.py", "src/agent_com/reporting.py"]
SOURCE_PATHS_COM04 = ["src/agent_com/__init__.py", "src/agent_com/api.py", "src/agent_com/models.py", "src/agent_com/config/excel.py", "src/agent_com/config/materialize.py", "src/agent_com/pipeline.py", "src/agent_com/network/mixed_mode.py", "src/agent_com/signal/interpolation.py", "src/agent_com/signal/fd_to_td.py", "src/agent_com/equalization/apply.py", "src/agent_com/equalization/ctle.py", "src/agent_com/equalization/rx_ffe.py", "src/agent_com/equalization/search.py", "src/agent_com/equalization/mmse.py", "src/agent_com/equalization/fvlms_rxffe.py", "src/agent_com/equalization/tx_ffe.py", "src/agent_com/equalization/dfe.py", "src/agent_com/signal/filters.py", "src/agent_com/noise/discrete_pdf.py", "src/agent_com/metrics/com.py", "src/agent_com/metrics/tdiln.py", "src/agent_com/reporting.py", "src/agent_com/runtime.py", "src/agent_com/calibration.py", "src/agent_com/legacy_csv.py", "src/agent_com/_orchestration.py"]
SEMANTIC_ANCHORS = {
    "semantic_payload_fields": ["scenarios[].scenario", "cases[].case_index", "cases[].channels", "cases[].metrics.COM_dB/VEC_dB/VEO_mV/sigma_N_V", "cases[].metrics.FOM (portable search selection when requested)", "cases[].metrics.available_signal_v/interference_noise_v/threshold_der/eye_opening_v", "cases[].metrics.calibration_sigma_bn_v/calibration_sigma_ne_v/calibration_sigma_hp_v", "cases[].diagnostics.channel_impulse", "cases[].diagnostics.crosstalk_inputs", "cases[].diagnostics.portable_branches", "report_manifest"],
    "portable_semantic_branches": ["fd_to_td_json", "mixed_mode_pn_skew", "fext_next_waveform_inputs", "equalization_apply", "tdiln", "search_nonmmse_no_rxffe", "mmse_kkt_search", "fvlms_rxffe_search", "calibration_noise_controller", "workbook_csv_mat_reuse", "legacy_csv_projection"],
    "unsupported_fail_closed": ["matlab_only_reporting", "wiener_hopf_source_unimplemented"],
}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def reject_constant(value): raise ValueError(f"non-finite JSON token: {value}")
def load_report(path):
    if Path(path).stat().st_size > 4 * 1024 * 1024: raise RuntimeError("report budget")
    return json.loads(Path(path).read_bytes(), parse_constant=reject_constant)
def finite_tree(value):
    if isinstance(value, float) and not math.isfinite(value): raise RuntimeError("non-finite value")
    if isinstance(value, dict):
        if any(type(key) is not str for key in value): raise RuntimeError("non-string key")
        for item in value.values(): finite_tree(item)
    elif isinstance(value, list):
        for item in value: finite_tree(item)
    elif value is not None and type(value) not in (str, int, float, bool): raise RuntimeError("invalid JSON type")
def canonical_sha(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def shape(value):
    if isinstance(value, dict): return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list): return [shape(item) for item in value]
    if value is None: return "null"
    return {str: "str", bool: "bool", int: "int", float: "float"}[type(value)]
def shape_sha(value): return canonical_sha(shape(value))
def exact(value, kind, label):
    if type(value) is not kind: raise RuntimeError(f"{label} exact type drift")
def tool_receipt(value, role):
    keys = {"executable", "file_sha256", "path_redacted", "role", "timed_out", "timeout_seconds", "version_exit_code", "version_output_sha256"}
    if set(value) != keys or value["role"] != role or value["executable"] != f"{role}.exe": raise RuntimeError("tool receipt drift")
    if value["path_redacted"] is not True or value["timed_out"] is not False or type(value["timeout_seconds"]) is not int or value["timeout_seconds"] != 30 or type(value["version_exit_code"]) is not int or value["version_exit_code"] != 0: raise RuntimeError("tool execution receipt drift")
    if not HEX64.fullmatch(value["file_sha256"]) or not HEX64.fullmatch(value["version_output_sha256"]): raise RuntimeError("tool digest drift")
def fixture_digest(inputs):
    return canonical_sha(inputs)
def git(repo, *args):
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(["git", "-C", str(repo), *args], stdout=stdout, stderr=stderr)
        deadline = time.monotonic() + 30
        while process.poll() is None:
            if time.monotonic() > deadline or __import__("os").fstat(stdout.fileno()).st_size > 64 * 1024 * 1024 or __import__("os").fstat(stderr.fileno()).st_size > 1024 * 1024:
                process.kill(); process.wait(); raise RuntimeError("bounded git gate failed")
            time.sleep(0.01)
        if process.returncode: raise RuntimeError("git gate failed")
        stdout.seek(0); payload = stdout.read(64 * 1024 * 1024 + 1)
        if len(payload) > 64 * 1024 * 1024: raise RuntimeError("git output cap")
        return payload

def verify_git(repo, upstream_repo):
    if git(repo, "show", "-s", "--format=%T", PREP[0]).decode().strip() != PREP[1]: raise RuntimeError("prep tree drift")
    if git(repo, "show", "-s", "--format=%T", CANDIDATE[0]).decode().strip() != CANDIDATE[1]: raise RuntimeError("candidate tree drift")
    if git(repo, "show", "-s", "--format=%T", PREP_PARENT[0]).decode().strip() != PREP_PARENT[1]: raise RuntimeError("interposed tree drift")
    changes = git(repo, "diff", "--name-status", f"{PREP[0]}..{PREP_PARENT[0]}").decode().splitlines()
    if set(changes) != {f"A\t{path}" for path in INTERPOSED_FILES}: raise RuntimeError("interposed exact-seven drift")
    for path, blob in PREP_BLOBS.items():
        if git(repo, "rev-parse", f"{PREP[0]}:{path}").decode().strip() != blob: raise RuntimeError("prep blob drift")
        raw = git(repo, "cat-file", "blob", blob)
        if (len(raw), hashlib.sha256(raw).hexdigest()) != PREP_RAW[path] or raw != (Path(repo) / path).read_bytes(): raise RuntimeError("prep raw/size/hash/live drift")
        if git(repo, "rev-parse", f"{PREP_PARENT[0]}:{path}").decode().strip() != blob: raise RuntimeError("interposed COM prep blob drift")
    audit = git(repo, "cat-file", "blob", PREP_BLOBS[next(iter(PREP_BLOBS))]).decode()
    for marker in ("selected_dfe_taps()", "No `cases[].port_order`", "prep source inventory"):
        if marker not in audit: raise RuntimeError("audit marker drift")
    if git(upstream_repo, "show", "-s", "--format=%T", UPSTREAM[0]).decode().strip() != UPSTREAM[1]: raise RuntimeError("upstream tree drift")
    with tempfile.TemporaryDirectory() as directory:
        for source, commit, expected, expected_bytes in ((repo, CANDIDATE[0], CANDIDATE[2], CANDIDATE[3]), (upstream_repo, UPSTREAM[0], UPSTREAM[2], 43_950_080)):
            path = Path(directory) / f"{commit}.tar"
            path.write_bytes(git(source, "archive", "--format=tar", commit))
            if sha(path) != expected or path.stat().st_size != expected_bytes: raise RuntimeError("archive mechanical identity drift")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True); parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--report", action="append", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.report) != 4: parser.error("four reports required")
    verify_git(args.repo, args.upstream_repo)
    reports = [load_report(path) for path in args.report]; hashes = [sha(path) for path in args.report]; nonces = []
    for report, (mode, index, _, _) in zip(reports, RUNS):
        if set(report) != REPORT_KEYS or report["mode"] != mode or report["schema"] != f"sipi.{mode}.direct-semantic-replay.v2": parser.error("report envelope drift")
        finite_tree(report)
        if set(report["source"]) != SOURCE_KEYS or set(report["upstream"]) != UPSTREAM_KEYS or set(report["candidate"]) != CANDIDATE_KEYS or set(report["parity"]) != PARITY_KEYS: parser.error("provenance schema drift")
        for label, value in ((f"source.{mode}", report["source"]), ("upstream", report["upstream"]), ("candidate", report["candidate"]), ("parity", report["parity"])):
            if shape_sha(value) != SHAPES[label]: parser.error(f"{label} nested shape drift")
        exact(report["payloads_committed"], bool, "payloads")
        for key, expected in SEMANTIC_ANCHORS.items():
            value = report[key]
            if type(value) is not list or any(type(item) is not str for item in value) or value != expected: parser.error(f"{key} semantic anchor drift")
        if report["payloads_committed"] is not False: parser.error("payload commitment drift")
        if report["source"]["commit"] != UPSTREAM[0] or report["source"]["tree"] != UPSTREAM[1] or report["parity"] != {"external_blockers": ["matlab_engine", "proprietary_golden", "plotting_format"], "numeric_upstream_parity_claim": False, "status": "semantic_replay_only"}: parser.error("source/parity drift")
        if report["source"] != {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "repository": "https://github.com/z331225718/agent-com.git", "declared_license": "MIT", "reachable_paths": SOURCE_PATHS if mode == "com-02" else SOURCE_PATHS_COM04}: parser.error("source value drift")
        expected_upstream = {"archive_sha256": UPSTREAM_DECLARED_ARCHIVE, "commit": UPSTREAM[0], "declared_license": "MIT", "materialization": "git archive at immutable commit metadata-only", "repository": "https://github.com/z331225718/agent-com.git", "runtime_executed": False, "source_map": f"crates/sipi-agent-com-direct/SOURCE-MAP-{mode.upper()}.md", "tree": UPSTREAM[1]}
        if report["upstream"] != expected_upstream: parser.error("upstream value drift")
        candidate = report["candidate"]
        if (candidate["commit"], candidate["tree"], candidate["archive_sha256"], candidate["archive_bytes"]) != CANDIDATE: parser.error("candidate drift")
        if candidate["status"] != "bound_clean_git_archive" or candidate["materialization"] != "git archive; no working-tree overlay" or candidate["binary"] != ("target/debug/sipi-com-direct-run.exe" if mode == "com-02" else "target/debug/sipi-com-direct-public-api.exe") or type(candidate["binary_bytes"]) is not int or candidate["binary_bytes"] <= 0 or not HEX64.fullmatch(candidate["binary_sha256"]): parser.error("candidate value/type drift")
        inventory = report["prep_source_inventory"]
        if set(inventory) != INVENTORY_KEYS or inventory["fresh_run_index"] != index: parser.error("prep inventory drift")
        if set(inventory["build"]) != BUILD_KEYS or set(inventory["fixture"]) != FIXTURE_KEYS or set(inventory["toolchain"]) != TOOLCHAIN_KEYS or set(inventory["source_probe"]) != PROBE_KEYS: parser.error("inventory nested schema drift")
        for label in ("build", "fixture", "toolchain", "source_probe"):
            if shape_sha(inventory[label]) != SHAPES[label]: parser.error(f"{label} deep shape drift")
        exact(inventory["fresh_run_index"], int, "fresh index"); exact(inventory["fixture"]["scenario_count"], int, "fixture count"); exact(inventory["fixture"]["inputs"], list, "fixture inputs"); exact(inventory["toolchain"]["path_redacted"], bool, "toolchain redaction")
        if inventory["fixture"]["scenario_count"] != 10 or inventory["build"]["source_commit"] != CANDIDATE[0] or inventory["build"]["source_tree"] != CANDIDATE[1] or inventory["build"]["archive_sha256"] != CANDIDATE[2]: parser.error("build/fixture crossfield drift")
        build = inventory["build"]
        binary_name = "sipi-com-direct-run" if mode == "com-02" else "sipi-com-direct-public-api"
        expected_binary = f"target/debug/{binary_name}.exe"
        if build["command"] != ["cargo", "build", "--manifest-path", "crates/sipi-agent-com-direct/Cargo.toml", "--locked", "--bin", binary_name] or build["returncode"] != 0 or build["timed_out"] is not False or build["rustc_wrapper_cleared"] is not True or build["source_mode"] != "candidate_git_archive_at_immutable_commit" or build["timeout_seconds"] != 300: parser.error("build execution drift")
        if build["binary"] != {"path": candidate["binary"], "bytes": candidate["binary_bytes"], "sha256": candidate["binary_sha256"]} or candidate["binary"] != expected_binary: parser.error("candidate/build binary crossfield drift")
        focused = build["candidate_execution_observations"]
        if set(focused) != {"trusted_workbook_snp_port_order"}: parser.error("focused observation drift")
        focused = focused["trusted_workbook_snp_port_order"]
        if set(focused) != {"kind", "test", "returncode", "stdout_sha256", "stderr_sha256", "serialized_result_field"} or focused["kind"] != "focused_rust_test" or focused["test"] != "package_vtf_v1::tests::workbook_snp_port_order_is_applied_before_mixed_mode" or focused["returncode"] != 0 or focused["serialized_result_field"] is not None or not HEX64.fullmatch(focused["stdout_sha256"]) or not HEX64.fullmatch(focused["stderr_sha256"]): parser.error("focused port-order receipt drift")
        inputs = inventory["fixture"]["inputs"]
        if inventory["fixture"]["generator"] != "prep-bound tools/com_direct_semantic_replay.py::write_fixture" or inventory["fixture"]["corpus_sha256"] != fixture_digest(inputs): parser.error("fixture corpus digest drift")
        for item in inputs:
            if set(item) != {"scenario", "name", "bytes", "sha256"} or item["scenario"] not in SCENARIOS or type(item["name"]) is not str or not item["name"] or type(item["bytes"]) is not int or item["bytes"] <= 0 or not HEX64.fullmatch(item["sha256"]): parser.error("fixture input receipt drift")
        if set(inventory["toolchain"]) != TOOLCHAIN_KEYS or inventory["toolchain"]["path_redacted"] is not True: parser.error("toolchain envelope drift")
        tool_receipt(inventory["toolchain"]["cargo"], "cargo"); tool_receipt(inventory["toolchain"]["rustc"], "rustc")
        if inventory["source_probe"]["s_parameter_fit"] != "forbidden" or any(inventory["source_probe"][key] is not True for key in ("s2p_forbids_matched_kernel", "s2p_uses_validated_fd_to_td_leaf", "s4p_forbids_matched_kernel", "s4p_uses_validated_fd_to_td_leaf")): parser.error("source probe drift")
        expected_probe = hashlib.sha256(git(args.repo, "show", f"{CANDIDATE[0]}:{inventory['source_probe']['source']}")).hexdigest()
        if inventory["source_probe"]["source"] != "crates/sipi-agent-com-direct/src/run_v1.rs" or inventory["source_probe"]["source_sha256"] != expected_probe: parser.error("source probe Git binding drift")
        if inventory["helper"]["runtime_executed"] != "true-from-snapshot" or inventory["runner"]["runtime_executed"] is not False or inventory["v2_wrapper"]["runtime_executed"] != "self_unproven": parser.error("runtime claim drift")
        for role, expected_sha in (("helper", PREP_RAW["tools/com_direct_semantic_replay.py"][1]), ("v2_wrapper", PREP_RAW["tools/com_direct_semantic_replay_v2.py"][1])):
            receipt = inventory[role]
            if set(receipt) != {"path", "runtime_executed", "sha256"} or receipt["sha256"] != expected_sha: parser.error("prep receipt drift")
        expected_runner = (f"tools/run_{mode.replace('-', '_')}_direct_semantic_replay.py", "2f5b8e6b33a1405c15347e1deed3e2b8b47344f7e99537307408a8e66a5510bb" if mode == "com-02" else "f92ef79818429693b6782e8fb8a776424baf3613f77822a9e2c9e6347ba9adc8")
        if set(inventory["runner"]) != {"path", "runtime_executed", "sha256"} or (inventory["runner"]["path"], inventory["runner"]["sha256"]) != expected_runner: parser.error("runner receipt drift")
        nonce = inventory["nonce"]
        if report["upstream"]["commit"] != UPSTREAM[0] or report["upstream"]["tree"] != UPSTREAM[1] or report["upstream"]["archive_sha256"] != UPSTREAM_DECLARED_ARCHIVE: parser.error("upstream report drift")
        if not HEX64.fullmatch(nonce) or report["replay_count"] != 2 or report["scenario_count"] != 10 or report["semantic_replays_identical"] is not True: parser.error("fresh replay drift")
        nonces.append(nonce)
        if report["run_id"] != inventory["run_id"] or type(report["run_id"]) is not str or not report["run_id"].endswith(nonce): parser.error("run ID crossfield drift")
        if type(report["replays"]) is not list or len(report["replays"]) != 2: parser.error("replay count shape drift")
        for replay in report["replays"]:
            if set(replay) != REPLAY_KEYS or replay["mode"] != mode or replay["exit_code"] != 0 or replay["scenario_count"] != 10: parser.error("replay schema drift")
            exact(replay["exit_code"], int, "replay exit"); exact(replay["scenario_count"], int, "replay count")
            if replay["semantic_sha256"] != canonical_sha(replay["semantic"]): parser.error("replay semantic digest drift")
            if type(replay["scenarios"]) is not list or [item.get("scenario") for item in replay["scenarios"]] != list(SCENARIOS): parser.error("scenario order drift")
            for scenario in replay["scenarios"]:
                if set(scenario) != SCENARIO_KEYS or scenario["exit_code"] != 0 or scenario["semantic"].get("scenario") != scenario["scenario"]: parser.error("scenario schema drift")
                expected_semantic = SEMANTIC_KEYS | ({"legacy_csv"} if scenario["scenario"] == "base" else set()) | ({"candidate_execution_observations"} if scenario["scenario"] == "search" else set())
                if set(scenario["semantic"]) != expected_semantic or scenario["semantic_sha256"] != canonical_sha(scenario["semantic"]): parser.error("scenario semantic schema/digest drift")
                if shape_sha(scenario["semantic"]) != SEMANTIC_SHAPES[scenario["scenario"]]: parser.error("scenario nested shape/type drift")
                expected_artifacts = ["diagnostics.json", "report.html", "result.json"]
                if scenario["scenario"] == "base": expected_artifacts.insert(1, "legacy.csv")
                if scenario["source_revision"] != "r480" or type(scenario["result_schema"]) is not int or scenario["result_schema"] != 1 or scenario["binary_schema"] != f"sipi.{mode}.direct-port.v1" or scenario["artifact_files"] != expected_artifacts: parser.error("scenario artifact/source drift")
                waveform = scenario["semantic"]["waveform"]; report_manifest = scenario["semantic"]["report_manifest"]
                if type(waveform["sample_count"]) is not int or waveform["sample_count"] <= 0 or not HEX64.fullmatch(waveform["sha256"]): parser.error("waveform receipt drift")
                expected_manifest = {"actual_figure_count": 0, "expected_figure_count": 0, "figures": [], "kind": "diagnostic_fallback", "plotting": {"reason": "reporting plot format is non-core and no external renderer is bundled", "status": "external_blocked"}}
                if report_manifest != expected_manifest: parser.error("report manifest receipt drift")
            observation = replay["scenarios"][6]["semantic"].get("candidate_execution_observations")
            if not isinstance(observation, dict) or observation.get("result_path") != "cases[].diagnostics.portable_branches.search.dfe_taps": parser.error("search observation drift")
            taps = observation.get("search_winner_dfe_taps")
            if not isinstance(taps, list) or not taps or len(taps) > 256 or any(type(item) not in (int, float) or isinstance(item, bool) or not math.isfinite(item) for item in taps): parser.error("DFE observation drift")
            if any("candidate_execution_observations" in scenario["semantic"] for scenario in replay["scenarios"][:6] + replay["scenarios"][7:]): parser.error("inferred observation drift")
        if report["replays"][0]["semantic"] != report["replays"][1]["semantic"]: parser.error("inner replay drift")
    if len(set(nonces)) != 4 or len(set(hashes)) != 4: parser.error("fresh identity drift")
    for key in ("fixture", "toolchain", "source_probe"):
        if any(report["prep_source_inventory"][key] != reports[0]["prep_source_inventory"][key] for report in reports[1:]): parser.error(f"{key} fresh drift")
    for left, right in ((0, 1), (2, 3)):
        if reports[left]["replays"][0]["semantic"] != reports[right]["replays"][0]["semantic"]: parser.error("semantic drift")
    output = {"schema": "sipi.com-02-04.result-surface-formal-aggregate.v1", "status": "passed_scoped", "formal_runs": [{"mode": mode, "fresh_index": index, "record_label": label, "coordination_label_sha256": coordination, "source_run_id": report["run_id"], "source_nonce": nonce, "report_sha256": digest} for (mode, index, label, coordination), report, nonce, digest in zip(RUNS, reports, nonces, hashes)], "candidate": {"commit": CANDIDATE[0], "tree": CANDIDATE[1], "archive_sha256": CANDIDATE[2], "archive_bytes": CANDIDATE[3]}, "prep": {"commit": PREP[0], "tree": PREP[1], "blobs": PREP_BLOBS}, "upstream": {"commit": UPSTREAM[0], "tree": UPSTREAM[1], "mechanical_git_archive_sha256": UPSTREAM[2], "report_declared_archive_sha256": UPSTREAM_DECLARED_ARCHIVE}, "semantic_anchors": SEMANTIC_ANCHORS, "claims": {"prep_source_inventory": True, "fresh_nonce": True, "coordination_labels_are_not_execution_identity": True, "full_report_hashes": True, "upstream_numeric_parity": False, "port_order_result_wire": False}}
    with args.output.open("x", encoding="utf-8", newline="\n") as handle: json.dump(output, handle, indent=2, sort_keys=True); handle.write("\n")
    return 0

if __name__ == "__main__": raise SystemExit(main())
