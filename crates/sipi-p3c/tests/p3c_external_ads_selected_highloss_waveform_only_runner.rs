#![forbid(unsafe_code)]

//! External-only v3 waveform-only comparison. It retains no source, ADS, or
//! waveform bytes in the emitted report.

use std::{
    env,
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

use serde_json::Value;
use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_contracts::{
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACT_SCHEMA_V3,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACTS_REQUEST_SCHEMA_V3,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_BYTE_LENGTH_V3,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3,
    SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_TIMEBASE_PROFILE_V3,
};
use sipi_ieee_com_sparam::{
    enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1,
    truncate_selected_p3c_response_v1,
};
use sipi_p3c::{
    admit_selected_p3c_sealed_s4p_v2, generate_selected_p3c_prbs9_impulse_candidate_v1,
    SelectedP3cSealedS4pIdentityV2, SELECTED_P3C_S4P_BYTE_LENGTH_V1,
    SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REFERENCE_ENV: &str = "SIPI_P3C_ADS_REFERENCE_CANONICAL_PAYLOAD";
const CLI_ENV: &str = "SIPI_P3C_SELECTED_HIGHLOSS_WAVEFORM_ONLY_CLI";
const REPORT_ENV: &str = "SIPI_P3C_SELECTED_HIGHLOSS_WAVEFORM_ONLY_REPORT";
const REPORT_SCHEMA: &str = "sipi.p3c.external-ads-selected-highloss-waveform-only-runner.v3";
const ADS_CANONICAL_SHA256: &str =
    "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726";
const ADS_TUPLE_BYTES: usize = 24;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;
const EYE_TIE_EXCLUSION: &str = "excluded_not_evaluated_for_this_selected_closed_eye_profile";

#[derive(Debug, Eq, PartialEq)]
struct MetricFact {
    reference_rx_payload_sha256: String,
    candidate_payload_sha256: String,
    reference_waveform_digest: String,
    candidate_waveform_digest: String,
    waveform_nrmse_bits: String,
    waveform_nrmse_limit_bits: String,
    within_waveform_nrmse_limit: bool,
    within_selected_waveform_only_profile: bool,
}

#[derive(Debug, Eq, PartialEq)]
struct RunFact {
    source_manifest_sha256: String,
    reference_manifest_sha256: String,
    candidate_manifest_sha256: String,
    record_count: usize,
    candidate_prefix_sha256: String,
    metric: MetricFact,
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

fn ulp(value: f64) -> f64 {
    if value == 0.0 {
        f64::from_bits(1)
    } else {
        let magnitude = value.abs();
        f64::from_bits(magnitude.to_bits() + 1) - magnitude
    }
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
        length = length
            .checked_add(read as u64)
            .ok_or_else(|| "identity_length_overflow".to_owned())?;
        hasher.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", hasher.finalize())))
}

fn selected_source_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = sha256_reader(File::open(path).map_err(|_| "source_open".to_owned())?)?;
    if identity
        != (
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        )
    {
        return Err("source_identity".to_owned());
    }
    Ok(identity)
}

fn reference_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = sha256_reader(File::open(path).map_err(|_| "reference_open".to_owned())?)?;
    if identity
        != (
            (SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3 * ADS_TUPLE_BYTES) as u64,
            ADS_CANONICAL_SHA256.to_owned(),
        )
    {
        return Err("reference_identity".to_owned());
    }
    Ok(identity)
}

fn fresh_root(kind: &str, index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-v3-{kind}-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn waveform_payload(values: &[f64]) -> Result<Vec<u8>, String> {
    if values.len() != SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3
        || values.iter().any(|value| !value.is_finite())
    {
        return Err("waveform_values".to_owned());
    }
    Ok(values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect())
}

fn reference_values(path: &Path) -> Result<(Vec<f64>, String), String> {
    let bytes = fs::read(path).map_err(|_| "reference_read".to_owned())?;
    if bytes.len()
        != SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3 * ADS_TUPLE_BYTES
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
        let tolerance = 8.0 * ulp(time.abs().max(expected.abs()));
        if !time.is_finite()
            || !tx.is_finite()
            || !rx.is_finite()
            || (time - expected).abs() > tolerance
        {
            return Err("reference_grid".to_owned());
        }
        values.push(rx);
    }
    let payload = waveform_payload(&values)?;
    Ok((values, sha256(&payload)))
}

fn manifest_sha256(root: &Path, artifact_id: &str) -> Result<String, String> {
    Ok(sha256(
        &fs::read(root.join(artifact_id).join("success.json"))
            .map_err(|_| "manifest_read".to_owned())?,
    ))
}

fn publish_waveform(
    root: &Path,
    artifact_id: &str,
    values: &[f64],
) -> Result<(String, String), String> {
    let payload = waveform_payload(values)?;
    let payload_sha256 = sha256(&payload);
    let metadata = format!(
        "{{\"schema\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACT_SCHEMA_V3}\",\"contract_sha256\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3}\",\"quantity\":\"differential_voltage\",\"unit\":\"volts_differential\",\"timebase_profile\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_TIMEBASE_PROFILE_V3}\",\"sample_count\":{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3},\"encoding\":\"ieee754-binary64-little-endian\",\"payload\":{{\"byte_length\":{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_BYTE_LENGTH_V3},\"sha256\":\"{payload_sha256}\"}}}}"
    );
    let store = ArtifactRoot::open_or_create(root).map_err(|_| "metric_root".to_owned())?;
    let mut stage = store.begin(artifact_id).map_err(|_| "metric_begin".to_owned())?;
    stage
        .stage_reader("waveform.json", metadata.as_bytes(), 4096)
        .map_err(|_| "metric_metadata".to_owned())?;
    stage
        .stage_reader(
            "waveform.f64le",
            payload.as_slice(),
            SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_BYTE_LENGTH_V3,
        )
        .map_err(|_| "metric_payload".to_owned())?;
    stage
        .seal()
        .map_err(|_| "metric_seal".to_owned())?
        .publish_new()
        .map_err(|_| "metric_publish".to_owned())?;
    Ok((manifest_sha256(root, artifact_id)?, payload_sha256))
}

fn candidate_values(source: &Path, root: &Path, index: usize) -> Result<(usize, String, Vec<f64>), String> {
    let before = selected_source_identity(source)?;
    let artifact_id = format!("selected-s4p-{index}");
    let store = ArtifactRoot::open_or_create(root).map_err(|_| "source_root".to_owned())?;
    let mut stage = store.begin(&artifact_id).map_err(|_| "source_begin".to_owned())?;
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
    if admitted.source_byte_length() != before.0
        || admitted.source_sha256() != before.1
        || admitted.artifact_id() != artifact_id
        || admitted.manifest_sha256() != manifest
    {
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
    waveform_payload(&values)?;
    Ok((admitted.record_count(), manifest, values))
}

fn string_field<'a>(object: &'a serde_json::Map<String, Value>, key: &str) -> Result<&'a str, String> {
    object
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| "cli_response_shape".to_owned())
}

fn bool_field(object: &serde_json::Map<String, Value>, key: &str) -> Result<bool, String> {
    object
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| "cli_response_shape".to_owned())
}

fn f64_field(object: &serde_json::Map<String, Value>, key: &str) -> Result<f64, String> {
    let value = object
        .get(key)
        .and_then(Value::as_f64)
        .ok_or_else(|| "cli_response_shape".to_owned())?;
    value
        .is_finite()
        .then_some(value)
        .ok_or_else(|| "cli_response_nonfinite".to_owned())
}

fn invoke_cli(
    cli: &Path,
    root: &Path,
    reference_id: &str,
    reference_manifest: &str,
    candidate_id: &str,
    candidate_manifest: &str,
    reference_payload: &str,
    candidate_payload: &str,
) -> Result<MetricFact, String> {
    let request = format!(
        "{{\"schema\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_ARTIFACTS_REQUEST_SCHEMA_V3}\",\"contract_sha256\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3}\",\"reference\":{{\"artifact_id\":\"{reference_id}\",\"manifest_sha256\":\"{reference_manifest}\"}},\"candidate\":{{\"artifact_id\":\"{candidate_id}\",\"manifest_sha256\":\"{candidate_manifest}\"}}}}"
    );
    let mut child = Command::new(cli)
        .args([
            "compare",
            "prbs9-waveform-only",
            "--stdin",
            "--artifact-root",
            root.to_string_lossy().as_ref(),
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|_| "cli_spawn".to_owned())?;
    child
        .stdin
        .take()
        .ok_or_else(|| "cli_stdin".to_owned())?
        .write_all(request.as_bytes())
        .map_err(|_| "cli_write".to_owned())?;
    let output = child.wait_with_output().map_err(|_| "cli_wait".to_owned())?;
    if !output.status.success() || !output.stderr.is_empty() {
        return Err("cli_rejected".to_owned());
    }
    let envelope: Value = serde_json::from_slice(&output.stdout)
        .map_err(|_| "cli_response_json".to_owned())?;
    let envelope = envelope
        .as_object()
        .ok_or_else(|| "cli_response_shape".to_owned())?;
    if string_field(envelope, "schema")? != "sipi.cli.response.v1"
        || envelope.get("protocol").and_then(Value::as_u64) != Some(1)
        || string_field(envelope, "command")? != "compare"
        || string_field(envelope, "status")? != "ok"
        || envelope.get("diagnostic_count").and_then(Value::as_u64) != Some(0)
    {
        return Err("cli_envelope_contract".to_owned());
    }
    let object = envelope
        .get("result")
        .and_then(Value::as_object)
        .ok_or_else(|| "cli_response_shape".to_owned())?;
    if string_field(object, "schema")?
        != "sipi.compare.selected-highloss-prbs9-waveform-only-artifacts-run-result.v3"
        || string_field(object, "contract_sha256")?
            != SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3
        || string_field(object, "sampled_eye")? != EYE_TIE_EXCLUSION
        || string_field(object, "crossing_tie")? != EYE_TIE_EXCLUSION
        || string_field(object, "external_reference_binding")? != "not_evaluated"
        || string_field(object, "external_profile_acceptance")? != "not_evaluated"
    {
        return Err("cli_response_contract".to_owned());
    }
    let reference = object
        .get("reference")
        .and_then(Value::as_object)
        .ok_or_else(|| "cli_response_shape".to_owned())?;
    let candidate = object
        .get("candidate")
        .and_then(Value::as_object)
        .ok_or_else(|| "cli_response_shape".to_owned())?;
    if string_field(reference, "artifact_id")? != reference_id
        || string_field(reference, "manifest_sha256")? != reference_manifest
        || string_field(reference, "payload_sha256")? != reference_payload
        || string_field(candidate, "artifact_id")? != candidate_id
        || string_field(candidate, "manifest_sha256")? != candidate_manifest
        || string_field(candidate, "payload_sha256")? != candidate_payload
        || object.get("compared_start").and_then(Value::as_u64) != Some(32_704)
        || object.get("compared_samples").and_then(Value::as_u64) != Some(16_352)
    {
        return Err("cli_response_binding".to_owned());
    }
    let within_waveform_nrmse_limit = bool_field(object, "within_waveform_nrmse_limit")?;
    let within_selected_waveform_only_profile =
        bool_field(object, "within_selected_waveform_only_profile")?;
    if within_waveform_nrmse_limit != within_selected_waveform_only_profile {
        return Err("cli_response_gate".to_owned());
    }
    Ok(MetricFact {
        reference_rx_payload_sha256: reference_payload.to_owned(),
        candidate_payload_sha256: candidate_payload.to_owned(),
        reference_waveform_digest: string_field(reference, "waveform_digest")?.to_owned(),
        candidate_waveform_digest: string_field(candidate, "waveform_digest")?.to_owned(),
        waveform_nrmse_bits: format!("{:016x}", f64_field(object, "waveform_nrmse")?.to_bits()),
        waveform_nrmse_limit_bits: format!(
            "{:016x}",
            f64_field(object, "waveform_nrmse_limit")?.to_bits()
        ),
        within_waveform_nrmse_limit,
        within_selected_waveform_only_profile,
    })
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

fn run_once(source: &Path, reference: &Path, cli: &Path, index: usize) -> Result<RunFact, String> {
    let s4p_root = fresh_root("s4p", index)?;
    let metric_root = fresh_root("metric", index)?;
    let result = (|| {
        let (record_count, source_manifest_sha256, candidate_values) =
            candidate_values(source, &s4p_root, index)?;
        let reference_before = reference_identity(reference)?;
        let (reference_values, reference_payload_sha256) = reference_values(reference)?;
        if reference_identity(reference)? != reference_before {
            return Err("reference_drift".to_owned());
        }
        let reference_id = format!("ads-reference-{index}");
        let candidate_id = format!("selected-candidate-{index}");
        let (reference_manifest_sha256, published_reference_payload_sha256) =
            publish_waveform(&metric_root, &reference_id, &reference_values)?;
        let (candidate_manifest_sha256, candidate_payload_sha256) =
            publish_waveform(&metric_root, &candidate_id, &candidate_values)?;
        if reference_payload_sha256 != published_reference_payload_sha256 {
            return Err("reference_publish_identity".to_owned());
        }
        let metric = invoke_cli(
            cli,
            &metric_root,
            &reference_id,
            &reference_manifest_sha256,
            &candidate_id,
            &candidate_manifest_sha256,
            &reference_payload_sha256,
            &candidate_payload_sha256,
        )?;
        Ok(RunFact {
            source_manifest_sha256,
            reference_manifest_sha256,
            candidate_manifest_sha256,
            record_count,
            candidate_prefix_sha256: candidate_prefix_digest(&candidate_values),
            metric,
        })
    })();
    let s4p_cleanup = fs::remove_dir_all(&s4p_root);
    let metric_cleanup = fs::remove_dir_all(&metric_root);
    if s4p_cleanup.is_err() || metric_cleanup.is_err() {
        return Err("cleanup".to_owned());
    }
    result
}

fn run_json(fact: &RunFact) -> String {
    format!(
        "{{\"source_manifest_sha256\":\"{}\",\"reference_manifest_sha256\":\"{}\",\"candidate_manifest_sha256\":\"{}\",\"record_count\":{},\"candidate_prefix_sha256\":\"{}\",\"reference_rx_payload_sha256\":\"{}\",\"candidate_payload_sha256\":\"{}\",\"reference_waveform_digest\":\"{}\",\"candidate_waveform_digest\":\"{}\",\"waveform_nrmse_bits\":\"{}\",\"waveform_nrmse_limit_bits\":\"{}\",\"within_waveform_nrmse_limit\":{},\"within_selected_waveform_only_profile\":{}}}",
        fact.source_manifest_sha256,
        fact.reference_manifest_sha256,
        fact.candidate_manifest_sha256,
        fact.record_count,
        fact.candidate_prefix_sha256,
        fact.metric.reference_rx_payload_sha256,
        fact.metric.candidate_payload_sha256,
        fact.metric.reference_waveform_digest,
        fact.metric.candidate_waveform_digest,
        fact.metric.waveform_nrmse_bits,
        fact.metric.waveform_nrmse_limit_bits,
        fact.metric.within_waveform_nrmse_limit,
        fact.metric.within_selected_waveform_only_profile,
    )
}

#[test]
#[ignore = "external-only v3 waveform comparison; requires explicit source/reference/CLI/report paths"]
fn p3c_external_ads_selected_highloss_waveform_only_runner_v3() {
    let source = required_path(SOURCE_ENV).unwrap();
    let reference = required_path(REFERENCE_ENV).unwrap();
    let cli = required_path(CLI_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    assert!(
        !report.exists() && !report.starts_with(env::current_dir().unwrap()),
        "report_path_not_fresh_external"
    );
    let first = run_once(&source, &reference, &cli, 1).unwrap();
    let second = run_once(&source, &reference, &cli, 2).unwrap();
    assert_ne!(first.source_manifest_sha256, second.source_manifest_sha256);
    assert_ne!(first.reference_manifest_sha256, second.reference_manifest_sha256);
    assert_ne!(first.candidate_manifest_sha256, second.candidate_manifest_sha256);
    assert_eq!(first.record_count, second.record_count);
    assert_eq!(first.candidate_prefix_sha256, second.candidate_prefix_sha256);
    assert_eq!(first.metric, second.metric);
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(
        report,
        format!(
            "{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"{}\",\"source_byte_length\":{},\"source_sha256\":\"{}\",\"ads_canonical_triple_payload_sha256\":\"{ADS_CANONICAL_SHA256}\",\"contract_sha256\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3}\",\"source_reference_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\\n",
            if first.metric.within_selected_waveform_only_profile {
                "accepted"
            } else {
                "observed_not_accepted"
            },
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1,
            run_json(&first),
            run_json(&second),
        ),
    )
    .unwrap();
}
