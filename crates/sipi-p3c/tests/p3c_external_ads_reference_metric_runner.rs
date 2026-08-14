#![forbid(unsafe_code)]

//! External-only PRBS9 reference binding runner. It retains no waveform bytes.

use std::{env, fs::{self, File}, io::{Read, Write}, path::{Path, PathBuf}, process::{Command, Stdio}, time::{SystemTime, UNIX_EPOCH}};

use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_compare::prbs9_waveform_v2::{compare_prbs9_metrics_v2, Prbs9WaveformMetricErrorV2, Prbs9WaveformPairV2};
use sipi_ieee_com_sparam::{enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1, truncate_selected_p3c_response_v1};
use sipi_p3c::{admit_selected_p3c_sealed_s4p_v2, generate_selected_p3c_prbs9_impulse_candidate_v1, SelectedP3cSealedS4pIdentityV2, SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1};

const SOURCE: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REFERENCE: &str = "SIPI_P3C_ADS_REFERENCE_CANONICAL_PAYLOAD";
const CLI: &str = "SIPI_P3C_PRBS9_METRIC_CLI";
const REPORT: &str = "SIPI_P3C_ADS_REFERENCE_METRIC_REPORT";
const CONTRACT: &str = "f47329b6ddda01cbcde1f24e21cb93e03f8ef6139ea2d43ff74cad9e2049d2b5";
const REFERENCE_CANONICAL_SHA: &str = "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726";
const COUNT: usize = 49_056;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;

fn env_path(name: &str) -> Result<PathBuf, String> {
    let value = env::var_os(name).ok_or_else(|| format!("{name}_missing"))?;
    let path = PathBuf::from(value);
    path.is_absolute().then_some(path).ok_or_else(|| format!("{name}_not_absolute"))
}

fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }

fn ulp(value: f64) -> f64 {
    if value == 0.0 {
        f64::from_bits(1)
    } else {
        let magnitude = value.abs();
        f64::from_bits(magnitude.to_bits() + 1) - magnitude
    }
}

fn identity(path: &Path) -> Result<(u64, String), String> {
    let mut file = File::open(path).map_err(|_| "source_open".to_owned())?;
    let mut hasher = Sha256::new(); let mut length = 0_u64; let mut buf = [0; 65_536];
    loop { let count = file.read(&mut buf).map_err(|_| "source_read".to_owned())?; if count == 0 { break; } length += count as u64; hasher.update(&buf[..count]); }
    let result = (length, format!("{:x}", hasher.finalize()));
    if result != (SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1.to_owned()) { return Err("source_identity".to_owned()); }
    Ok(result)
}

fn fresh(prefix: &str, index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| "clock".to_owned())?.as_nanos();
    let path = env::temp_dir().join(format!("{prefix}-{index}-{nonce}"));
    fs::create_dir(&path).map_err(|_| "root_create".to_owned())?; Ok(path)
}

fn reference_values(path: &Path) -> Result<(Vec<f64>, String), String> {
    let bytes = fs::read(path).map_err(|_| "reference_read".to_owned())?;
    if bytes.len() != COUNT * 24 || digest(&bytes) != REFERENCE_CANONICAL_SHA { return Err("reference_identity".to_owned()); }
    let mut values = Vec::with_capacity(COUNT);
    let mut rows = bytes.chunks_exact(24);
    for (index, row) in rows.by_ref().enumerate() {
        let time = f64::from_le_bytes(row[..8].try_into().map_err(|_| "reference_layout")?);
        let tx = f64::from_le_bytes(row[8..16].try_into().map_err(|_| "reference_layout")?);
        let rx = f64::from_le_bytes(row[16..].try_into().map_err(|_| "reference_layout")?);
        let expected_time = index as f64 * f64::from_bits(DT_BITS);
        let grid_tolerance = 8.0 * ulp(time.abs().max(expected_time.abs()));
        if !time.is_finite() || !tx.is_finite() || !rx.is_finite() || (time - expected_time).abs() > grid_tolerance { return Err("reference_grid".to_owned()); }
        values.push(rx);
    }
    if !rows.remainder().is_empty() { return Err("reference_layout".to_owned()); }
    let payload = values.iter().flat_map(|value| value.to_le_bytes()).collect::<Vec<_>>();
    Ok((values, digest(&payload)))
}

fn publish(root: &Path, id: &str, values: &[f64]) -> Result<(String, String), String> {
    if values.len() != COUNT || values.iter().any(|value| !value.is_finite()) { return Err("artifact_values".to_owned()); }
    let payload = values.iter().flat_map(|value| value.to_le_bytes()).collect::<Vec<_>>();
    let payload_sha = digest(&payload);
    let metadata = format!("{{\"schema\":\"sipi.compare.prbs9-waveform-artifact.v1\",\"contract_sha256\":\"{CONTRACT}\",\"quantity\":\"differential_voltage\",\"unit\":\"volts_differential\",\"timebase_profile\":\"prbs9-v2-32gtps-osr32-three-period-half-open\",\"sample_count\":49056,\"encoding\":\"ieee754-binary64-little-endian\",\"payload\":{{\"byte_length\":392448,\"sha256\":\"{payload_sha}\"}}}}");
    let store = ArtifactRoot::open_or_create(root).map_err(|_| "artifact_root".to_owned())?;
    let mut stage = store.begin(id).map_err(|_| "artifact_begin".to_owned())?;
    stage.stage_reader("waveform.json", metadata.as_bytes(), 4096).map_err(|_| "artifact_metadata".to_owned())?;
    stage.stage_reader("waveform.f64le", payload.as_slice(), 392_448).map_err(|_| "artifact_payload".to_owned())?;
    stage.seal().map_err(|_| "artifact_seal".to_owned())?.publish_new().map_err(|_| "artifact_publish".to_owned())?;
    Ok((digest(&fs::read(root.join(id).join("success.json")).map_err(|_| "manifest_read".to_owned())?), payload_sha))
}

fn candidate(source: &Path, root: &Path, index: usize) -> Result<Vec<f64>, String> {
    let before = identity(source)?; let store = ArtifactRoot::open_or_create(root).map_err(|_| "source_root".to_owned())?;
    let id = format!("s4p-{index}"); let mut stage = store.begin(&id).map_err(|_| "source_begin".to_owned())?;
    stage.stage_reader(SELECTED_P3C_S4P_FILE_NAME_V1, File::open(source).map_err(|_| "source_reopen".to_owned())?, SELECTED_P3C_S4P_BYTE_LENGTH_V1).map_err(|_| "source_stage".to_owned())?;
    stage.seal().map_err(|_| "source_seal".to_owned())?.publish_new().map_err(|_| "source_publish".to_owned())?;
    if identity(source)? != before { return Err("source_drift".to_owned()); }
    let manifest = digest(&fs::read(root.join(&id).join("success.json")).map_err(|_| "source_manifest".to_owned())?);
    let reader = ArtifactRoot::open_existing(root).map_err(|_| "source_reopen_root".to_owned())?;
    let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &SelectedP3cSealedS4pIdentityV2::try_new(&id, &manifest).map_err(|_| "source_identity_request".to_owned())?).map_err(|_| "admission".to_owned())?;
    let uniform = interpolate_selected_p3c_hdiff_v1(admitted.transfer()).map_err(|_| "interpolation".to_owned())?;
    let causal = enforce_selected_p3c_causality_v1(&uniform).map_err(|_| "causality".to_owned())?;
    let truncated = truncate_selected_p3c_response_v1(&causal).map_err(|_| "truncation".to_owned())?;
    Ok(generate_selected_p3c_prbs9_impulse_candidate_v1(&truncated).map_err(|_| "candidate_convolution".to_owned())?.waveform_prefix().iter().map(|value| value.get()).collect())
}

fn metric_reason(reference: Vec<f64>, candidate: Vec<f64>) -> &'static str {
    let pair = match Prbs9WaveformPairV2::try_new(reference, candidate) {
        Ok(pair) => pair,
        Err(_) => return "pair_rejection",
    };
    match compare_prbs9_metrics_v2(&pair) {
        Ok(_) => "core_ok",
        Err(Prbs9WaveformMetricErrorV2::ZeroReferenceNorm) => "zero_reference_norm",
        Err(Prbs9WaveformMetricErrorV2::ZeroReferenceEyeMetric { metric: "height" }) => "zero_reference_eye_height",
        Err(Prbs9WaveformMetricErrorV2::ZeroReferenceEyeMetric { metric: "width" }) => "zero_reference_eye_width",
        Err(Prbs9WaveformMetricErrorV2::ZeroReferenceEyeMetric { .. }) => "numeric_rejection",
        Err(Prbs9WaveformMetricErrorV2::ZeroPlateau { waveform: "reference", .. }) => "zero_plateau_reference",
        Err(Prbs9WaveformMetricErrorV2::ZeroPlateau { waveform: "candidate", .. }) => "zero_plateau_candidate",
        Err(Prbs9WaveformMetricErrorV2::ZeroPlateau { .. }) => "numeric_rejection",
        Err(Prbs9WaveformMetricErrorV2::CrossingCount { waveform: "reference", actual: 0, .. }) => "crossing_missing_reference",
        Err(Prbs9WaveformMetricErrorV2::CrossingCount { waveform: "candidate", actual: 0, .. }) => "crossing_missing_candidate",
        Err(Prbs9WaveformMetricErrorV2::CrossingCount { waveform: "reference", .. }) => "crossing_multiple_reference",
        Err(Prbs9WaveformMetricErrorV2::CrossingCount { waveform: "candidate", .. }) => "crossing_multiple_candidate",
        Err(Prbs9WaveformMetricErrorV2::CrossingCount { .. } | Prbs9WaveformMetricErrorV2::NumericOverflow { .. } | Prbs9WaveformMetricErrorV2::LengthMismatch { .. } | Prbs9WaveformMetricErrorV2::NonFiniteValue { .. }) => "numeric_rejection",
    }
}

fn run_once(source: &Path, reference: &Path, cli: &Path, index: usize) -> Result<(bool, String), String> {
    let s4p_root = fresh("sipi-p3c-metric-s4p", index)?; let metric_root = fresh("sipi-p3c-metric-artifacts", index)?;
    let result = (|| {
        let candidate_values = candidate(source, &s4p_root, index)?;
        let (reference_values, reference_payload_sha) = reference_values(reference)?;
        let direct_core_reason = metric_reason(reference_values.clone(), candidate_values.clone());
        let (reference_manifest, _) = publish(&metric_root, &format!("reference-{index}"), &reference_values)?;
        let (candidate_manifest, candidate_payload_sha) = publish(&metric_root, &format!("candidate-{index}"), &candidate_values)?;
        let request = format!("{{\"schema\":\"sipi.compare.prbs9-metric-artifacts-request.v1\",\"contract_sha256\":\"{CONTRACT}\",\"reference\":{{\"artifact_id\":\"reference-{index}\",\"manifest_sha256\":\"{reference_manifest}\"}},\"candidate\":{{\"artifact_id\":\"candidate-{index}\",\"manifest_sha256\":\"{candidate_manifest}\"}}}}");
        let mut child = Command::new(cli).args(["compare", "prbs9-metrics", "--stdin", "--artifact-root", metric_root.to_string_lossy().as_ref()]).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().map_err(|_| "cli_spawn".to_owned())?;
        child.stdin.take().ok_or_else(|| "cli_stdin".to_owned())?.write_all(request.as_bytes()).map_err(|_| "cli_write".to_owned())?;
        let output = child.wait_with_output().map_err(|_| "cli_wait".to_owned())?;
        let exit_code = output.status.code().unwrap_or(-1);
        if exit_code == 3 {
            let stdout = String::from_utf8(output.stdout).map_err(|_| "cli_utf8".to_owned())?;
            let stderr = String::from_utf8(output.stderr).map_err(|_| "cli_utf8".to_owned())?;
            if !stdout.contains("\"command\":\"compare\"") || !stdout.contains("\"status\":\"invalid\"") || !stdout.contains("\"result\":null") || !stderr.contains("\"code\":\"contract_rejected\"") || !stderr.contains("\"stage\":\"schema\"") || !stderr.contains("\"rule_id\":\"contract.cross-field.v1\"") { return Err("cli_rejection_envelope".to_owned()); }
            let token = if direct_core_reason == "core_ok" { "core_ok_cli_rejected" } else { direct_core_reason };
            return Ok((false, format!("{{\"status\":\"rejected\",\"stage\":\"cli\",\"exit_code\":{exit_code},\"direct_core_reason\":\"{token}\",\"cli_stdout_byte_length\":{},\"cli_stdout_sha256\":\"{}\",\"cli_stderr_byte_length\":{},\"cli_stderr_sha256\":\"{}\"}}", stdout.len(), digest(stdout.as_bytes()), stderr.len(), digest(stderr.as_bytes()))));
        }
        if !output.status.success() || !output.stderr.is_empty() { return Err("cli_failed".to_owned()); }
        let response = String::from_utf8(output.stdout).map_err(|_| "cli_utf8".to_owned())?;
        Ok((true, format!("{{\"status\":\"admitted\",\"reference_manifest_sha256\":\"{reference_manifest}\",\"candidate_manifest_sha256\":\"{candidate_manifest}\",\"reference_rx_payload_sha256\":\"{reference_payload_sha}\",\"candidate_payload_sha256\":\"{candidate_payload_sha}\",\"cli_result\":{}}}", response.trim())))
    })();
    let left = fs::remove_dir_all(&s4p_root); let right = fs::remove_dir_all(&metric_root);
    if left.is_err() || right.is_err() { return Err("cleanup".to_owned()); } result
}

#[test]
#[ignore = "external-only ADS reference binding; requires explicit source/reference/CLI/report paths"]
fn p3c_external_ads_reference_metric_runner_v1() {
    let source = env_path(SOURCE).unwrap(); let reference = env_path(REFERENCE).unwrap(); let cli = env_path(CLI).unwrap(); let report = env_path(REPORT).unwrap();
    assert!(!report.exists() && !report.starts_with(env::current_dir().unwrap()));
    let (first_admitted, first) = run_once(&source, &reference, &cli, 1).unwrap();
    let (second_admitted, second) = run_once(&source, &reference, &cli, 2).unwrap();
    assert_eq!(first_admitted, second_admitted, "run_outcome_mismatch");
    if !first_admitted { assert_eq!(first, second, "rejected_run_mismatch"); }
    let outcome = if first_admitted { "admitted" } else { "rejected" };
    fs::write(report, format!("{{\"schema\":\"sipi.p3c.external-ads-reference-metric-runner.v1\",\"outcome\":\"{outcome}\",\"runs\":[{first},{second}],\"cleanup_status\":\"complete\"}}\n")).unwrap();
}
