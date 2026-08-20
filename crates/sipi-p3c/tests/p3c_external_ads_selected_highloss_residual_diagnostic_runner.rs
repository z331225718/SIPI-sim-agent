#![forbid(unsafe_code)]

//! External-only strict-index residual diagnostic; it retains no waveform data.

use std::{
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use serde_json::Value;
use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_compare::selected_highloss_prbs9_waveform_only_v3::{
    SelectedHighlossPrbs9WaveformPairV3, compare_selected_highloss_prbs9_waveform_only_v3,
    diagnose_selected_highloss_prbs9_residual_v1,
};
use sipi_contracts::{
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3,
};
use sipi_ieee_com_sparam::{
    enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1,
    truncate_selected_p3c_response_v1,
};
use sipi_p3c::{
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
    SelectedP3cSealedS4pIdentityV2, admit_selected_p3c_sealed_s4p_v2,
    generate_selected_p3c_prbs9_impulse_candidate_v1,
    generate_selected_p3c_prbs9_impulse_candidate_v2,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REFERENCE_ENV: &str = "SIPI_P3C_ADS_REFERENCE_CANONICAL_PAYLOAD";
const REPORT_ENV: &str = "SIPI_P3C_SELECTED_HIGHLOSS_RESIDUAL_REPORT";
const REPORT_ENV_V2: &str = "SIPI_P3C_SELECTED_HIGHLOSS_RESIDUAL_V2_REPORT";
const REPORT_SCHEMA: &str = "sipi.p3c.external-ads-selected-highloss-residual-runner.v1";
const REPORT_SCHEMA_V2: &str = "sipi.p3c.external-ads-selected-highloss-residual-v2-runner.v1";
const ADS_CANONICAL_SHA256: &str =
    "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726";
const ADS_TUPLE_BYTES: usize = 24;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;

#[derive(Debug, Eq, PartialEq)]
struct PeriodFact {
    reference_rms_bits: String,
    candidate_rms_bits: String,
    residual_rms_bits: String,
    residual_mean_bits: String,
    residual_nrmse_bits: String,
    residual_digest: String,
    maximum_absolute_residual_bits: String,
    maximum_absolute_residual_offset: usize,
}

#[derive(Debug, Eq, PartialEq)]
struct RunFact {
    source_manifest_sha256: String,
    record_count: usize,
    reference_rx_payload_sha256: String,
    candidate_prefix_sha256: String,
    periods: Vec<PeriodFact>,
    third_period_ui_energy_digest: String,
    third_period_maximum_energy_ui_offset: usize,
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
        let read = reader
            .read(&mut buffer)
            .map_err(|_| "identity_read".to_owned())?;
        if read == 0 {
            break;
        }
        length = length
            .checked_add(read as u64)
            .ok_or_else(|| "identity_length_overflow".to_owned())?;
        hasher.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", hasher.finalize())))
}

fn selected_source_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = sha256_reader(File::open(path).map_err(|_| "source_open".to_owned())?)?;
    (identity
        == (
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        ))
        .then_some(identity)
        .ok_or_else(|| "source_identity".to_owned())
}

fn reference_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = sha256_reader(File::open(path).map_err(|_| "reference_open".to_owned())?)?;
    (identity
        == (
            (SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3 * ADS_TUPLE_BYTES) as u64,
            ADS_CANONICAL_SHA256.to_owned(),
        ))
        .then_some(identity)
        .ok_or_else(|| "reference_identity".to_owned())
}

fn fresh_root(index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-residual-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn manifest_sha256(root: &Path, artifact_id: &str) -> Result<String, String> {
    fs::read(root.join(artifact_id).join("success.json"))
        .map(|bytes| sha256(&bytes))
        .map_err(|_| "manifest_read".to_owned())
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
        if !time.is_finite()
            || !tx.is_finite()
            || !rx.is_finite()
            || (time - expected).abs() > 8.0 * f64::EPSILON.max(expected.abs() * f64::EPSILON)
        {
            return Err("reference_grid".to_owned());
        }
        values.push(rx);
    }
    let payload = values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect::<Vec<_>>();
    Ok((values, sha256(&payload)))
}

fn candidate_values(
    source: &Path,
    root: &Path,
    index: usize,
) -> Result<(usize, String, Vec<f64>), String> {
    let before = selected_source_identity(source)?;
    let artifact_id = format!("selected-s4p-residual-{index}");
    let store = ArtifactRoot::open_or_create(root).map_err(|_| "source_root".to_owned())?;
    let mut stage = store
        .begin(&artifact_id)
        .map_err(|_| "source_begin".to_owned())?;
    stage
        .stage_reader(
            SELECTED_P3C_S4P_FILE_NAME_V1,
            File::open(source).map_err(|_| "source_reopen".to_owned())?,
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        )
        .map_err(|_| "source_stage".to_owned())?;
    stage
        .seal()
        .map_err(|_| "source_seal".to_owned())?
        .publish_new()
        .map_err(|_| "source_publish".to_owned())?;
    if selected_source_identity(source)? != before {
        return Err("source_drift".to_owned());
    }
    let manifest = manifest_sha256(root, &artifact_id)?;
    let reader = ArtifactRoot::open_existing(root).map_err(|_| "source_reopen_root".to_owned())?;
    let identity = SelectedP3cSealedS4pIdentityV2::try_new(&artifact_id, &manifest)
        .map_err(|_| "source_request_identity".to_owned())?;
    let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &identity)
        .map_err(|_| "source_admission".to_owned())?;
    if admitted.source_byte_length() != before.0 || admitted.source_sha256() != before.1 {
        return Err("source_admission_provenance".to_owned());
    }
    let uniform = interpolate_selected_p3c_hdiff_v1(admitted.transfer())
        .map_err(|_| "candidate_interpolation".to_owned())?;
    let causal = enforce_selected_p3c_causality_v1(&uniform)
        .map_err(|_| "candidate_causality".to_owned())?;
    let truncated = truncate_selected_p3c_response_v1(&causal)
        .map_err(|_| "candidate_truncation".to_owned())?;
    let candidate = generate_selected_p3c_prbs9_impulse_candidate_v1(&truncated)
        .map_err(|_| "candidate_convolution".to_owned())?;
    let values = candidate
        .waveform_prefix()
        .iter()
        .map(|sample| sample.get())
        .collect::<Vec<_>>();
    (values.len() == SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3
        && values.iter().all(|value| value.is_finite()))
    .then_some((admitted.record_count(), manifest, values))
    .ok_or_else(|| "candidate_values".to_owned())
}

fn candidate_values_v2(
    source: &Path,
    root: &Path,
    index: usize,
) -> Result<(usize, String, Vec<f64>), String> {
    let before = selected_source_identity(source)?;
    let artifact_id = format!("selected-s4p-residual-v2-{index}");
    let store = ArtifactRoot::open_or_create(root).map_err(|_| "source_root".to_owned())?;
    let mut stage = store
        .begin(&artifact_id)
        .map_err(|_| "source_begin".to_owned())?;
    stage
        .stage_reader(
            SELECTED_P3C_S4P_FILE_NAME_V1,
            File::open(source).map_err(|_| "source_reopen".to_owned())?,
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        )
        .map_err(|_| "source_stage".to_owned())?;
    stage
        .seal()
        .map_err(|_| "source_seal".to_owned())?
        .publish_new()
        .map_err(|_| "source_publish".to_owned())?;
    if selected_source_identity(source)? != before {
        return Err("source_drift".to_owned());
    }
    let manifest = manifest_sha256(root, &artifact_id)?;
    let reader = ArtifactRoot::open_existing(root).map_err(|_| "source_reopen_root".to_owned())?;
    let identity = SelectedP3cSealedS4pIdentityV2::try_new(&artifact_id, &manifest)
        .map_err(|_| "source_request_identity".to_owned())?;
    let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &identity)
        .map_err(|_| "source_admission".to_owned())?;
    if admitted.source_byte_length() != before.0 || admitted.source_sha256() != before.1 {
        return Err("source_admission_provenance".to_owned());
    }
    let uniform = interpolate_selected_p3c_hdiff_v1(admitted.transfer())
        .map_err(|_| "candidate_interpolation".to_owned())?;
    let causal = enforce_selected_p3c_causality_v1(&uniform)
        .map_err(|_| "candidate_causality".to_owned())?;
    let truncated = truncate_selected_p3c_response_v1(&causal)
        .map_err(|_| "candidate_truncation".to_owned())?;
    let candidate = generate_selected_p3c_prbs9_impulse_candidate_v2(&truncated)
        .map_err(|_| "candidate_convolution".to_owned())?;
    let values = candidate
        .waveform_prefix()
        .iter()
        .map(|sample| sample.get())
        .collect::<Vec<_>>();
    (values.len() == SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3
        && values.iter().all(|value| value.is_finite()))
    .then_some((admitted.record_count(), manifest, values))
    .ok_or_else(|| "candidate_values".to_owned())
}

fn candidate_prefix_digest(values: &[f64]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"sipi.p3c.selected-highloss-prbs9-waveform-prefix.v3\0");
    hasher.update((values.len() as u64).to_be_bytes());
    hasher.update(DT_BITS.to_be_bytes());
    for value in values {
        hasher.update(value.to_bits().to_be_bytes());
    }
    format!("{:x}", hasher.finalize())
}

fn run_once(source: &Path, reference_path: &Path, index: usize) -> Result<RunFact, String> {
    let root = fresh_root(index)?;
    let result = (|| {
        let (record_count, source_manifest_sha256, candidate) =
            candidate_values(source, &root, index)?;
        let reference_before = reference_identity(reference_path)?;
        let (reference, reference_rx_payload_sha256) = reference_values(reference_path)?;
        if reference_identity(reference_path)? != reference_before {
            return Err("reference_drift".to_owned());
        }
        let candidate_prefix_sha256 = candidate_prefix_digest(&candidate);
        let pair = SelectedHighlossPrbs9WaveformPairV3::try_new(reference, candidate)
            .map_err(|_| "diagnostic_pair".to_owned())?;
        let report = compare_selected_highloss_prbs9_waveform_only_v3(&pair)
            .map_err(|_| "diagnostic_v3".to_owned())?;
        let diagnostic = diagnose_selected_highloss_prbs9_residual_v1(&pair)
            .map_err(|_| "diagnostic_residual".to_owned())?;
        if diagnostic.periods()[2].residual_nrmse().to_bits() != report.waveform_nrmse().to_bits() {
            return Err("third_period_nrmse_mismatch".to_owned());
        }
        let periods = diagnostic
            .periods()
            .iter()
            .map(|period| PeriodFact {
                reference_rms_bits: format!("{:016x}", period.reference_rms().to_bits()),
                candidate_rms_bits: format!("{:016x}", period.candidate_rms().to_bits()),
                residual_rms_bits: format!("{:016x}", period.residual_rms().to_bits()),
                residual_mean_bits: format!("{:016x}", period.residual_mean().to_bits()),
                residual_nrmse_bits: format!("{:016x}", period.residual_nrmse().to_bits()),
                residual_digest: period.residual_digest().to_owned(),
                maximum_absolute_residual_bits: format!(
                    "{:016x}",
                    period.maximum_absolute_residual().to_bits()
                ),
                maximum_absolute_residual_offset: period.maximum_absolute_residual_offset(),
            })
            .collect();
        Ok(RunFact {
            source_manifest_sha256,
            record_count,
            reference_rx_payload_sha256,
            candidate_prefix_sha256,
            periods,
            third_period_ui_energy_digest: diagnostic.third_period_ui_energy_digest().to_owned(),
            third_period_maximum_energy_ui_offset: diagnostic
                .third_period_maximum_energy_ui_offset(),
        })
    })();
    if fs::remove_dir_all(root).is_err() {
        return Err("cleanup".to_owned());
    }
    result
}

fn run_once_v2(source: &Path, reference_path: &Path, index: usize) -> Result<RunFact, String> {
    let root = fresh_root(index)?;
    let result = (|| {
        let (record_count, source_manifest_sha256, candidate) =
            candidate_values_v2(source, &root, index)?;
        let reference_before = reference_identity(reference_path)?;
        let (reference, reference_rx_payload_sha256) = reference_values(reference_path)?;
        if reference_identity(reference_path)? != reference_before {
            return Err("reference_drift".to_owned());
        }
        let candidate_prefix_sha256 = candidate_prefix_digest(&candidate);
        let pair = SelectedHighlossPrbs9WaveformPairV3::try_new(reference, candidate)
            .map_err(|_| "diagnostic_pair".to_owned())?;
        let report = compare_selected_highloss_prbs9_waveform_only_v3(&pair)
            .map_err(|_| "diagnostic_v3".to_owned())?;
        let diagnostic = diagnose_selected_highloss_prbs9_residual_v1(&pair)
            .map_err(|_| "diagnostic_residual".to_owned())?;
        if diagnostic.periods()[2].residual_nrmse().to_bits() != report.waveform_nrmse().to_bits() {
            return Err("third_period_nrmse_mismatch".to_owned());
        }
        let periods = diagnostic
            .periods()
            .iter()
            .map(|period| PeriodFact {
                reference_rms_bits: format!("{:016x}", period.reference_rms().to_bits()),
                candidate_rms_bits: format!("{:016x}", period.candidate_rms().to_bits()),
                residual_rms_bits: format!("{:016x}", period.residual_rms().to_bits()),
                residual_mean_bits: format!("{:016x}", period.residual_mean().to_bits()),
                residual_nrmse_bits: format!("{:016x}", period.residual_nrmse().to_bits()),
                residual_digest: period.residual_digest().to_owned(),
                maximum_absolute_residual_bits: format!(
                    "{:016x}",
                    period.maximum_absolute_residual().to_bits()
                ),
                maximum_absolute_residual_offset: period.maximum_absolute_residual_offset(),
            })
            .collect();
        Ok(RunFact {
            source_manifest_sha256,
            record_count,
            reference_rx_payload_sha256,
            candidate_prefix_sha256,
            periods,
            third_period_ui_energy_digest: diagnostic.third_period_ui_energy_digest().to_owned(),
            third_period_maximum_energy_ui_offset: diagnostic
                .third_period_maximum_energy_ui_offset(),
        })
    })();
    if fs::remove_dir_all(root).is_err() {
        return Err("cleanup".to_owned());
    }
    result
}

fn run_json(fact: &RunFact) -> String {
    let periods = fact.periods.iter().map(|period| format!("{{\"reference_rms_bits\":\"{}\",\"candidate_rms_bits\":\"{}\",\"residual_rms_bits\":\"{}\",\"residual_mean_bits\":\"{}\",\"residual_nrmse_bits\":\"{}\",\"residual_digest\":\"{}\",\"maximum_absolute_residual_bits\":\"{}\",\"maximum_absolute_residual_offset\":{}}}", period.reference_rms_bits, period.candidate_rms_bits, period.residual_rms_bits, period.residual_mean_bits, period.residual_nrmse_bits, period.residual_digest, period.maximum_absolute_residual_bits, period.maximum_absolute_residual_offset)).collect::<Vec<_>>().join(",");
    format!(
        "{{\"source_manifest_sha256\":\"{}\",\"record_count\":{},\"reference_rx_payload_sha256\":\"{}\",\"candidate_prefix_sha256\":\"{}\",\"periods\":[{}],\"third_period_ui_energy_digest\":\"{}\",\"third_period_maximum_energy_ui_offset\":{}}}",
        fact.source_manifest_sha256,
        fact.record_count,
        fact.reference_rx_payload_sha256,
        fact.candidate_prefix_sha256,
        periods,
        fact.third_period_ui_energy_digest,
        fact.third_period_maximum_energy_ui_offset
    )
}

#[test]
#[ignore = "external-only strict-index residual diagnostic; requires source/reference/report paths"]
fn p3c_external_ads_selected_highloss_residual_diagnostic_runner_v1() {
    let source = required_path(SOURCE_ENV).unwrap();
    let reference = required_path(REFERENCE_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    assert!(
        !report.exists() && !report.starts_with(env::current_dir().unwrap()),
        "report_path_not_fresh_external"
    );
    let first = run_once(&source, &reference, 1).unwrap();
    let second = run_once(&source, &reference, 2).unwrap();
    assert_ne!(first.source_manifest_sha256, second.source_manifest_sha256);
    assert_eq!(first.record_count, second.record_count);
    assert_eq!(
        first.reference_rx_payload_sha256,
        second.reference_rx_payload_sha256
    );
    assert_eq!(
        first.candidate_prefix_sha256,
        second.candidate_prefix_sha256
    );
    assert_eq!(first.periods, second.periods);
    assert_eq!(
        first.third_period_ui_energy_digest,
        second.third_period_ui_energy_digest
    );
    assert_eq!(
        first.third_period_maximum_energy_ui_offset,
        second.third_period_maximum_energy_ui_offset
    );
    let payload = format!(
        "{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"observed\",\"source_byte_length\":{},\"source_sha256\":\"{}\",\"ads_canonical_triple_payload_sha256\":\"{ADS_CANONICAL_SHA256}\",\"contract_sha256\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3}\",\"source_reference_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n",
        SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        SELECTED_P3C_S4P_SHA256_V1,
        run_json(&first),
        run_json(&second)
    );
    serde_json::from_str::<Value>(&payload).expect("report_json");
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, payload).unwrap();
}

#[test]
#[ignore = "external-only strict-index residual diagnostic for the selected finite-edge v2 candidate"]
fn p3c_external_ads_selected_highloss_residual_diagnostic_runner_v2() {
    let source = required_path(SOURCE_ENV).unwrap();
    let reference = required_path(REFERENCE_ENV).unwrap();
    let report = required_path(REPORT_ENV_V2).unwrap();
    assert!(
        !report.exists() && !report.starts_with(env::current_dir().unwrap()),
        "report_path_not_fresh_external"
    );
    let first = run_once_v2(&source, &reference, 1).unwrap();
    let second = run_once_v2(&source, &reference, 2).unwrap();
    assert_ne!(first.source_manifest_sha256, second.source_manifest_sha256);
    assert_eq!(first.record_count, second.record_count);
    assert_eq!(
        first.reference_rx_payload_sha256,
        second.reference_rx_payload_sha256
    );
    assert_eq!(
        first.candidate_prefix_sha256,
        second.candidate_prefix_sha256
    );
    assert_eq!(first.periods, second.periods);
    assert_eq!(
        first.third_period_ui_energy_digest,
        second.third_period_ui_energy_digest
    );
    assert_eq!(
        first.third_period_maximum_energy_ui_offset,
        second.third_period_maximum_energy_ui_offset
    );
    let payload = format!(
        "{{\"schema\":\"{REPORT_SCHEMA_V2}\",\"status\":\"observed\",\"source_byte_length\":{},\"source_sha256\":\"{}\",\"ads_canonical_triple_payload_sha256\":\"{ADS_CANONICAL_SHA256}\",\"contract_sha256\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3}\",\"source_reference_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n",
        SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        SELECTED_P3C_S4P_SHA256_V1,
        run_json(&first),
        run_json(&second)
    );
    serde_json::from_str::<Value>(&payload).expect("report_json");
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, payload).unwrap();
}
