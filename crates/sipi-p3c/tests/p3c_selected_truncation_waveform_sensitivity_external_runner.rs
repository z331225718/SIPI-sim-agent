#![forbid(unsafe_code)]

//! External-only third-period sensitivity observation for selected truncation.

use std::{
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_compare::selected_highloss_prbs9_waveform_only_v3::{
    compare_selected_highloss_prbs9_waveform_only_v3, SelectedHighlossPrbs9WaveformPairV3,
};
use sipi_contracts::SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3;
use sipi_ieee_com_sparam::{
    enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1,
    truncate_selected_p3c_response_v1,
};
use sipi_p3c::{
    admit_selected_p3c_sealed_s4p_v2, diagnose_selected_p3c_full_causal_third_period_v1,
    generate_selected_p3c_prbs9_impulse_candidate_v1, SelectedP3cSealedS4pIdentityV2,
    P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1, SELECTED_P3C_S4P_BYTE_LENGTH_V1,
    SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REFERENCE_ENV: &str = "SIPI_P3C_ADS_REFERENCE_CANONICAL_PAYLOAD";
const REPORT_ENV: &str = "SIPI_P3C_SELECTED_TRUNCATION_SENSITIVITY_REPORT";
const ADS_CANONICAL_SHA256: &str =
    "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726";
const ADS_TUPLE_BYTES: usize = 24;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;
const BASELINE_NRMSE_BITS: u64 = 0x3f9c_4139_b95f_cc93;

#[derive(Debug, PartialEq)]
struct RunFact {
    source_manifest_sha256: String,
    record_count: usize,
    reference_rx_payload_sha256: String,
    causality_iterations: usize,
    causal_response_sha256: String,
    retained_taps: usize,
    truncated_prefix_sha256: String,
    truncated_nrmse_bits: String,
    full_causal_third_sha256: String,
    full_causal_nrmse_bits: String,
}

impl RunFact {
    fn same_outcome(&self, other: &Self) -> bool {
        self.record_count == other.record_count
            && self.reference_rx_payload_sha256 == other.reference_rx_payload_sha256
            && self.causality_iterations == other.causality_iterations
            && self.causal_response_sha256 == other.causal_response_sha256
            && self.retained_taps == other.retained_taps
            && self.truncated_prefix_sha256 == other.truncated_prefix_sha256
            && self.truncated_nrmse_bits == other.truncated_nrmse_bits
            && self.full_causal_third_sha256 == other.full_causal_third_sha256
            && self.full_causal_nrmse_bits == other.full_causal_nrmse_bits
    }
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute()
        .then_some(path)
        .ok_or_else(|| format!("{name}_not_absolute"))
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn sha256_reader(mut reader: impl Read) -> Result<(u64, String), String> {
    let mut hasher = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader.read(&mut buffer).map_err(|_| "identity_read".to_owned())?;
        if read == 0 {
            break;
        }
        length = length.checked_add(read as u64).ok_or_else(|| "identity_length_overflow".to_owned())?;
        hasher.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", hasher.finalize())))
}

fn source_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = sha256_reader(File::open(path).map_err(|_| "source_open".to_owned())?)?;
    (identity == (SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1.to_owned()))
        .then_some(identity)
        .ok_or_else(|| "source_identity".to_owned())
}

fn reference_values(path: &Path) -> Result<(Vec<f64>, String), String> {
    let bytes = fs::read(path).map_err(|_| "reference_read".to_owned())?;
    if bytes.len() != SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3 * ADS_TUPLE_BYTES
        || sha256(&bytes) != ADS_CANONICAL_SHA256
    {
        return Err("reference_identity".to_owned());
    }
    let mut values = Vec::with_capacity(SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3);
    for (index, tuple) in bytes.chunks_exact(ADS_TUPLE_BYTES).enumerate() {
        let time = f64::from_le_bytes(tuple[..8].try_into().map_err(|_| "reference_layout")?);
        let tx = f64::from_le_bytes(tuple[8..16].try_into().map_err(|_| "reference_layout")?);
        let rx = f64::from_le_bytes(tuple[16..].try_into().map_err(|_| "reference_layout")?);
        let expected = index as f64 * f64::from_bits(DT_BITS);
        if !time.is_finite() || !tx.is_finite() || !rx.is_finite()
            || (time - expected).abs() > 8.0 * f64::EPSILON.max(expected.abs() * f64::EPSILON)
        {
            return Err("reference_grid".to_owned());
        }
        values.push(rx);
    }
    let payload = values.iter().flat_map(|value| value.to_le_bytes()).collect::<Vec<_>>();
    Ok((values, sha256(&payload)))
}

fn fresh_root(index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| "clock".to_owned())?.as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-truncation-sensitivity-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn waveform_digest(domain: &[u8], values: &[f64]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(domain);
    hasher.update((values.len() as u64).to_be_bytes());
    hasher.update(DT_BITS.to_be_bytes());
    for value in values {
        hasher.update(value.to_bits().to_be_bytes());
    }
    format!("{:x}", hasher.finalize())
}

fn metric(reference: &[f64], candidate: Vec<f64>) -> Result<String, String> {
    let pair = SelectedHighlossPrbs9WaveformPairV3::try_new(reference.to_vec(), candidate)
        .map_err(|_| "metric_pair".to_owned())?;
    compare_selected_highloss_prbs9_waveform_only_v3(&pair)
        .map(|report| format!("{:016x}", report.waveform_nrmse().to_bits()))
        .map_err(|_| "waveform_nrmse".to_owned())
}

fn run_once(source: &Path, reference_path: &Path, index: usize) -> Result<RunFact, String> {
    let root = fresh_root(index)?;
    let result = (|| {
        let before = source_identity(source)?;
        let artifact_id = format!("selected-s4p-truncation-sensitivity-{index}");
        let store = ArtifactRoot::open_or_create(&root).map_err(|_| "source_root".to_owned())?;
        let mut stage = store.begin(&artifact_id).map_err(|_| "source_begin".to_owned())?;
        stage.stage_reader(SELECTED_P3C_S4P_FILE_NAME_V1, File::open(source).map_err(|_| "source_reopen".to_owned())?, SELECTED_P3C_S4P_BYTE_LENGTH_V1).map_err(|_| "source_stage".to_owned())?;
        stage.seal().map_err(|_| "source_seal".to_owned())?.publish_new().map_err(|_| "source_publish".to_owned())?;
        if source_identity(source)? != before {
            return Err("source_drift".to_owned());
        }
        let manifest = sha256(&fs::read(root.join(&artifact_id).join("success.json")).map_err(|_| "manifest_read".to_owned())?);
        let reader = ArtifactRoot::open_existing(&root).map_err(|_| "source_reopen_root".to_owned())?;
        let identity = SelectedP3cSealedS4pIdentityV2::try_new(&artifact_id, &manifest).map_err(|_| "source_request_identity".to_owned())?;
        let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &identity).map_err(|_| "source_admission".to_owned())?;
        if admitted.source_byte_length() != before.0 || admitted.source_sha256() != before.1 {
            return Err("source_admission_provenance".to_owned());
        }
        let reference_before = sha256_reader(File::open(reference_path).map_err(|_| "reference_open".to_owned())?)?;
        let (reference, reference_rx_payload_sha256) = reference_values(reference_path)?;
        if sha256_reader(File::open(reference_path).map_err(|_| "reference_reopen".to_owned())?)? != reference_before {
            return Err("reference_drift".to_owned());
        }
        let spectrum = interpolate_selected_p3c_hdiff_v1(admitted.transfer()).map_err(|_| "interpolation".to_owned())?;
        let causal = enforce_selected_p3c_causality_v1(&spectrum).map_err(|_| "causality".to_owned())?;
        let causal_values = causal.samples().iter().map(|sample| sample.get()).collect::<Vec<_>>();
        let truncated = truncate_selected_p3c_response_v1(&causal).map_err(|_| "truncation".to_owned())?;
        let baseline = generate_selected_p3c_prbs9_impulse_candidate_v1(&truncated).map_err(|_| "candidate_convolution".to_owned())?;
        let truncated_values = baseline.waveform_prefix().iter().map(|sample| sample.get()).collect::<Vec<_>>();
        let truncated_nrmse_bits = metric(&reference, truncated_values.clone())?;
        if u64::from_str_radix(&truncated_nrmse_bits, 16).ok() != Some(BASELINE_NRMSE_BITS) {
            return Err("baseline_nrmse_not_reproduced".to_owned());
        }
        let full = diagnose_selected_p3c_full_causal_third_period_v1(&causal).map_err(|_| "full_causal_diagnostic".to_owned())?;
        let full_values = full.samples().iter().map(|sample| sample.get()).collect::<Vec<_>>();
        let mut full_for_metric = vec![0.0; P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1];
        full_for_metric.extend_from_slice(&full_values);
        Ok(RunFact {
            source_manifest_sha256: manifest,
            record_count: admitted.record_count(),
            reference_rx_payload_sha256,
            causality_iterations: causal.iteration_count(),
            causal_response_sha256: waveform_digest(b"sipi.p3c.selected-bounded-causal-response.v1\0", &causal_values),
            retained_taps: truncated.sample_count(),
            truncated_prefix_sha256: waveform_digest(b"sipi.p3c.selected-highloss-prbs9-waveform-prefix.v3\0", &truncated_values),
            truncated_nrmse_bits,
            full_causal_third_sha256: waveform_digest(b"sipi.p3c.selected-full-causal-third-period.v1\0", &full_values),
            full_causal_nrmse_bits: metric(&reference, full_for_metric)?,
        })
    })();
    if fs::remove_dir_all(root).is_err() {
        return Err("cleanup".to_owned());
    }
    result
}

fn report_run(fact: &RunFact) -> Value {
    json!({
        "source_manifest_sha256": fact.source_manifest_sha256,
        "record_count": fact.record_count,
        "reference_rx_payload_sha256": fact.reference_rx_payload_sha256,
        "causality_iterations": fact.causality_iterations,
        "causal_response_sha256": fact.causal_response_sha256,
        "retained_taps": fact.retained_taps,
        "truncated_prefix_sha256": fact.truncated_prefix_sha256,
        "truncated_nrmse_bits": fact.truncated_nrmse_bits,
        "full_causal_third_sha256": fact.full_causal_third_sha256,
        "full_causal_nrmse_bits": fact.full_causal_nrmse_bits,
    })
}

#[test]
#[ignore = "external-only selected truncation sensitivity; requires source/reference/report paths"]
fn p3c_selected_truncation_waveform_sensitivity_external_runner_v1() {
    let source = required_path(SOURCE_ENV).unwrap();
    let reference = required_path(REFERENCE_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    assert!(!report.exists() && !report.starts_with(env::current_dir().unwrap()), "report_path_not_fresh_external");
    let first = run_once(&source, &reference, 1).unwrap();
    let second = run_once(&source, &reference, 2).unwrap();
    assert_ne!(first.source_manifest_sha256, second.source_manifest_sha256);
    assert!(first.same_outcome(&second), "fresh_runs_not_identical");
    let payload = json!({
        "schema": "sipi.p3c.selected-truncation-waveform-sensitivity-runner.v1",
        "status": "observed",
        "source_byte_length": SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        "source_sha256": SELECTED_P3C_S4P_SHA256_V1,
        "ads_canonical_triple_payload_sha256": ADS_CANONICAL_SHA256,
        "source_reference_identity_checks": "before_stage_after_equal",
        "fresh_runs": [report_run(&first), report_run(&second)],
        "cleanup_status": "complete",
    });
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, serde_json::to_vec(&payload).unwrap()).unwrap();
}
