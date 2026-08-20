#![forbid(unsafe_code)]

//! External-only same-index observation of one fixed off-grid ADS pulse.
//! This runner has no public API and cannot alter the selected candidate route.

use std::{
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_contracts::{CausalFirChannelV1, LinkPlanV1, RxStagesV1, TxStageV1, UniformTimebaseV1};
use sipi_ieee_com_sparam::{
    enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1,
    truncate_selected_p3c_response_v1,
};
use sipi_link::{ConvolutionLimitsV1, convolve_causal_fir_v1};
use sipi_p3c::{
    P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1, P3C_PRBS9_TOTAL_SAMPLES_V1,
    P3C_SELECTED_FULL_LINEAR_MACS_V1, P3C_SELECTED_FULL_LINEAR_SAMPLES_V1,
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
    SelectedP3cSealedS4pIdentityV2, admit_selected_p3c_sealed_s4p_v2,
};
use sipi_types::{Seconds, Volts};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const PAYLOAD_ONE_ENV: &str = "SIPI_P3C_ADS_FIXED_PULSE_PAYLOAD_ONE";
const PAYLOAD_TWO_ENV: &str = "SIPI_P3C_ADS_FIXED_PULSE_PAYLOAD_TWO";
const REPORT_ENV: &str = "SIPI_P3C_ADS_FIXED_PULSE_OPERATOR_RUNNER_REPORT";
const SCHEMA: &str = "sipi.p3c.ads-fixed-pulse-operator-runner.v1";
const DT_BITS: u64 = P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1;
const PULSE_START: usize = 16_353;
const PULSE_END: usize = 16_385;
const PAYLOAD_BYTES: usize = P3C_PRBS9_TOTAL_SAMPLES_V1 * 24;

#[derive(Debug, Eq, PartialEq)]
struct RunFact {
    manifest_sha256: String,
    ads_payload_sha256: String,
    record_count: usize,
    uniform_bin_count: usize,
    causality_iterations: usize,
    causality_stop: &'static str,
    retained_taps: usize,
    input_sha256: String,
    ads_tx_sha256: String,
    ads_rx_sha256: String,
    product_prefix_sha256: String,
    residual_sha256: String,
    pre_pulse_reference_rms_bits: String,
    pre_pulse_product_rms_bits: String,
    pre_pulse_residual_rms_bits: String,
    post_pulse_reference_rms_bits: String,
    post_pulse_product_rms_bits: String,
    post_pulse_residual_rms_bits: String,
    post_pulse_nrmse_bits: String,
    strict_identity: bool,
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute()
        .then_some(path)
        .ok_or_else(|| format!("{name}_not_absolute"))
}

fn sha256_reader(mut reader: impl Read) -> Result<(u64, String), String> {
    let mut digest = Sha256::new();
    let mut count = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader
            .read(&mut buffer)
            .map_err(|_| "source_read".to_owned())?;
        if read == 0 {
            break;
        }
        count = count
            .checked_add(read as u64)
            .ok_or_else(|| "source_length".to_owned())?;
        digest.update(&buffer[..read]);
    }
    Ok((count, format!("{:x}", digest.finalize())))
}

fn source_identity(path: &Path) -> Result<(u64, String), String> {
    let value = sha256_reader(File::open(path).map_err(|_| "source_open".to_owned())?)?;
    (value
        == (
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        ))
        .then_some(value)
        .ok_or_else(|| "source_identity".to_owned())
}

fn read_ads_payload(path: &Path) -> Result<(String, Vec<f64>, Vec<f64>), String> {
    let bytes = fs::read(path).map_err(|_| "ads_payload_read".to_owned())?;
    if bytes.len() != PAYLOAD_BYTES {
        return Err("ads_payload_length".to_owned());
    }
    let mut tx = Vec::with_capacity(P3C_PRBS9_TOTAL_SAMPLES_V1);
    let mut rx = Vec::with_capacity(P3C_PRBS9_TOTAL_SAMPLES_V1);
    for index in 0..P3C_PRBS9_TOTAL_SAMPLES_V1 {
        let offset = index * 24;
        let time = f64::from_le_bytes(
            bytes[offset..offset + 8]
                .try_into()
                .map_err(|_| "ads_payload_decode")?,
        );
        let tx_value = f64::from_le_bytes(
            bytes[offset + 8..offset + 16]
                .try_into()
                .map_err(|_| "ads_payload_decode")?,
        );
        let rx_value = f64::from_le_bytes(
            bytes[offset + 16..offset + 24]
                .try_into()
                .map_err(|_| "ads_payload_decode")?,
        );
        let expected = index as f64 * f64::from_bits(DT_BITS);
        let scale = time.abs().max(expected.abs()).max(f64::MIN_POSITIVE);
        if !time.is_finite()
            || !tx_value.is_finite()
            || !rx_value.is_finite()
            || (time - expected).abs() > 8.0 * f64::EPSILON * scale
        {
            return Err("ads_payload_grid".to_owned());
        }
        tx.push(tx_value);
        rx.push(rx_value);
    }
    Ok((format!("{:x}", Sha256::digest(bytes)), tx, rx))
}

fn digest(domain: &[u8], samples: &[f64]) -> Result<String, String> {
    if samples.iter().any(|sample| !sample.is_finite()) {
        return Err("digest_nonfinite".to_owned());
    }
    let mut hash = Sha256::new();
    hash.update(domain);
    hash.update((samples.len() as u64).to_be_bytes());
    hash.update(DT_BITS.to_be_bytes());
    for sample in samples {
        hash.update(sample.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn rms(samples: &[f64]) -> Result<f64, String> {
    if samples.is_empty() {
        return Err("empty_partition".to_owned());
    }
    let max = samples
        .iter()
        .fold(0.0_f64, |current, value| current.max(value.abs()));
    if !max.is_finite() {
        return Err("rms_nonfinite".to_owned());
    }
    if max == 0.0 {
        return Ok(0.0);
    }
    let mean = samples
        .iter()
        .map(|value| (value / max).powi(2))
        .sum::<f64>()
        / samples.len() as f64;
    let value = max * mean.sqrt();
    value
        .is_finite()
        .then_some(value)
        .ok_or_else(|| "rms_nonfinite".to_owned())
}

fn nrmse(reference: &[f64], candidate: &[f64]) -> Result<f64, String> {
    if reference.len() != candidate.len() || reference.is_empty() {
        return Err("nrmse_shape".to_owned());
    }
    let residual = reference
        .iter()
        .zip(candidate)
        .map(|(left, right)| right - left)
        .collect::<Vec<_>>();
    let reference_rms = rms(reference)?;
    (reference_rms > 0.0)
        .then_some(rms(&residual)? / reference_rms)
        .ok_or_else(|| "nrmse_zero_reference".to_owned())
}

fn pulse_input() -> Vec<Volts> {
    (0..P3C_PRBS9_TOTAL_SAMPLES_V1)
        .map(|index| {
            Volts::try_new(if (PULSE_START..PULSE_END).contains(&index) {
                1.0
            } else {
                0.0
            })
            .unwrap()
        })
        .collect()
}

fn fresh_root(index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-fixed-pulse-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn run_once(source: &Path, payload: &Path, index: usize) -> Result<RunFact, String> {
    let before = source_identity(source)?;
    let (ads_payload_sha256, ads_tx, ads_rx) = read_ads_payload(payload)?;
    let root = fresh_root(index)?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root).map_err(|_| "artifact_root".to_owned())?;
        let artifact_id = format!("selected-s4p-fixed-pulse-{index}");
        let mut stage = store
            .begin(&artifact_id)
            .map_err(|_| "artifact_begin".to_owned())?;
        stage
            .stage_reader(
                SELECTED_P3C_S4P_FILE_NAME_V1,
                File::open(source).map_err(|_| "source_reopen".to_owned())?,
                SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            )
            .map_err(|_| "artifact_stage".to_owned())?;
        stage
            .seal()
            .map_err(|_| "artifact_seal".to_owned())?
            .publish_new()
            .map_err(|_| "artifact_publish".to_owned())?;
        if source_identity(source)? != before {
            return Err("source_drift".to_owned());
        }
        let manifest = format!(
            "{:x}",
            Sha256::digest(
                fs::read(root.join(&artifact_id).join("success.json"))
                    .map_err(|_| "manifest".to_owned())?
            )
        );
        let reader =
            ArtifactRoot::open_existing(&root).map_err(|_| "artifact_reopen".to_owned())?;
        let identity = SelectedP3cSealedS4pIdentityV2::try_new(&artifact_id, &manifest)
            .map_err(|_| "identity".to_owned())?;
        let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &identity)
            .map_err(|_| "admission".to_owned())?;
        let uniform = interpolate_selected_p3c_hdiff_v1(admitted.transfer())
            .map_err(|_| "interpolation".to_owned())?;
        let causal =
            enforce_selected_p3c_causality_v1(&uniform).map_err(|_| "causality".to_owned())?;
        let truncated =
            truncate_selected_p3c_response_v1(&causal).map_err(|_| "truncation".to_owned())?;
        let dt = Seconds::try_new(f64::from_bits(DT_BITS)).map_err(|_| "dt".to_owned())?;
        let plan = LinkPlanV1::try_new(
            UniformTimebaseV1::try_new(
                Seconds::try_new(0.0).map_err(|_| "zero".to_owned())?,
                dt,
                P3C_PRBS9_TOTAL_SAMPLES_V1,
            )
            .map_err(|_| "timebase".to_owned())?,
            TxStageV1::DirectLaunch,
            pulse_input(),
            CausalFirChannelV1::try_new(dt, truncated.samples().to_vec())
                .map_err(|_| "channel".to_owned())?,
            RxStagesV1::bypass(),
        )
        .map_err(|_| "plan".to_owned())?;
        let output = convolve_causal_fir_v1(
            &plan,
            ConvolutionLimitsV1::try_new(
                P3C_SELECTED_FULL_LINEAR_SAMPLES_V1,
                P3C_SELECTED_FULL_LINEAR_MACS_V1,
            )
            .map_err(|_| "limits".to_owned())?,
        )
        .map_err(|_| "convolution".to_owned())?;
        let product = output
            .waveform()
            .samples()
            .iter()
            .take(P3C_PRBS9_TOTAL_SAMPLES_V1)
            .map(|sample| sample.get())
            .collect::<Vec<_>>();
        if output.waveform().samples().len() != P3C_SELECTED_FULL_LINEAR_SAMPLES_V1
            || product.len() != ads_rx.len()
            || truncated.sample_count() != 10_871
            || causal.iteration_count() != 32
        {
            return Err("fixed_shape".to_owned());
        }
        let residual = product
            .iter()
            .zip(&ads_rx)
            .map(|(candidate, reference)| candidate - reference)
            .collect::<Vec<_>>();
        let stop = match causal.stop() {
            sipi_ieee_com_sparam::SelectedP3cCausalityStopV1::RelativeError => "relative_error",
            sipi_ieee_com_sparam::SelectedP3cCausalityStopV1::SuccessiveErrorDifference => {
                "successive_error_difference"
            }
        };
        Ok(RunFact {
            manifest_sha256: manifest,
            ads_payload_sha256,
            record_count: admitted.record_count(),
            uniform_bin_count: uniform.sample_count(),
            causality_iterations: causal.iteration_count(),
            causality_stop: stop,
            retained_taps: truncated.sample_count(),
            input_sha256: digest(
                b"sipi.p3c.fixed-pulse-input.v1\0",
                &pulse_input()
                    .iter()
                    .map(|value| value.get())
                    .collect::<Vec<_>>(),
            )?,
            ads_tx_sha256: digest(b"sipi.p3c.fixed-pulse-ads-tx.v1\0", &ads_tx)?,
            ads_rx_sha256: digest(b"sipi.p3c.fixed-pulse-ads-rx.v1\0", &ads_rx)?,
            product_prefix_sha256: digest(b"sipi.p3c.fixed-pulse-product-prefix.v1\0", &product)?,
            residual_sha256: digest(b"sipi.p3c.fixed-pulse-residual.v1\0", &residual)?,
            pre_pulse_reference_rms_bits: format!(
                "{:016x}",
                rms(&ads_rx[..PULSE_START])?.to_bits()
            ),
            pre_pulse_product_rms_bits: format!("{:016x}", rms(&product[..PULSE_START])?.to_bits()),
            pre_pulse_residual_rms_bits: format!(
                "{:016x}",
                rms(&residual[..PULSE_START])?.to_bits()
            ),
            post_pulse_reference_rms_bits: format!(
                "{:016x}",
                rms(&ads_rx[PULSE_START..])?.to_bits()
            ),
            post_pulse_product_rms_bits: format!(
                "{:016x}",
                rms(&product[PULSE_START..])?.to_bits()
            ),
            post_pulse_residual_rms_bits: format!(
                "{:016x}",
                rms(&residual[PULSE_START..])?.to_bits()
            ),
            post_pulse_nrmse_bits: format!(
                "{:016x}",
                nrmse(&ads_rx[PULSE_START..], &product[PULSE_START..])?.to_bits()
            ),
            strict_identity: ads_rx == product,
        })
    })();
    let cleanup = fs::remove_dir_all(&root).map_err(|_| "cleanup".to_owned());
    match (result, cleanup) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error), Ok(())) | (_, Err(error)) => Err(error),
    }
}

fn json(fact: &RunFact) -> String {
    format!(
        "{{\"manifest_sha256\":\"{}\",\"ads_payload_sha256\":\"{}\",\"record_count\":{},\"uniform_bin_count\":{},\"causality_iterations\":{},\"causality_stop\":\"{}\",\"retained_taps\":{},\"input_sha256\":\"{}\",\"ads_tx_sha256\":\"{}\",\"ads_rx_sha256\":\"{}\",\"product_prefix_sha256\":\"{}\",\"residual_sha256\":\"{}\",\"pre_pulse_reference_rms_bits\":\"{}\",\"pre_pulse_product_rms_bits\":\"{}\",\"pre_pulse_residual_rms_bits\":\"{}\",\"post_pulse_reference_rms_bits\":\"{}\",\"post_pulse_product_rms_bits\":\"{}\",\"post_pulse_residual_rms_bits\":\"{}\",\"post_pulse_nrmse_bits\":\"{}\",\"strict_identity\":{}}}",
        fact.manifest_sha256,
        fact.ads_payload_sha256,
        fact.record_count,
        fact.uniform_bin_count,
        fact.causality_iterations,
        fact.causality_stop,
        fact.retained_taps,
        fact.input_sha256,
        fact.ads_tx_sha256,
        fact.ads_rx_sha256,
        fact.product_prefix_sha256,
        fact.residual_sha256,
        fact.pre_pulse_reference_rms_bits,
        fact.pre_pulse_product_rms_bits,
        fact.pre_pulse_residual_rms_bits,
        fact.post_pulse_reference_rms_bits,
        fact.post_pulse_product_rms_bits,
        fact.post_pulse_residual_rms_bits,
        fact.post_pulse_nrmse_bits,
        fact.strict_identity
    )
}

#[test]
fn fixed_off_grid_pulse_has_exactly_thirty_two_one_volt_samples() {
    let input = pulse_input();
    assert_eq!(input.len(), P3C_PRBS9_TOTAL_SAMPLES_V1);
    assert!(input[..PULSE_START].iter().all(|value| value.get() == 0.0));
    assert!(
        input[PULSE_START..PULSE_END]
            .iter()
            .all(|value| value.get() == 1.0)
    );
    assert!(input[PULSE_END..].iter().all(|value| value.get() == 0.0));
}

#[test]
#[ignore = "external-only selected S4P fixed pulse operator observation"]
fn p3c_external_ads_fixed_pulse_operator_runner_v1() {
    let source = required_path(SOURCE_ENV).unwrap();
    let payload_one = required_path(PAYLOAD_ONE_ENV).unwrap();
    let payload_two = required_path(PAYLOAD_TWO_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    assert!(!report.exists());
    let first = run_once(&source, &payload_one, 1).unwrap();
    let second = run_once(&source, &payload_two, 2).unwrap();
    assert_ne!(first.manifest_sha256, second.manifest_sha256);
    assert_eq!(first.ads_payload_sha256, second.ads_payload_sha256);
    assert_eq!(
        json(&first).replace(&first.manifest_sha256, "manifest"),
        json(&second).replace(&second.manifest_sha256, "manifest")
    );
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    let content = format!(
        "{{\"schema\":\"{SCHEMA}\",\"status\":\"observed\",\"sample_interval_bits\":\"{DT_BITS:016x}\",\"pulse\":{{\"start_index\":{PULSE_START},\"end_index_exclusive\":{PULSE_END},\"one_volt_sample_count\":32}},\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n",
        json(&first),
        json(&second)
    );
    serde_json::from_str::<serde_json::Value>(&content).unwrap();
    fs::write(report, content).unwrap();
}
