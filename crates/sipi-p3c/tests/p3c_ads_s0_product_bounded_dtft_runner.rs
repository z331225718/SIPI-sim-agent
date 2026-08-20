//! External-only fixed ADS-S0 to product-bounded-response DTFT observation.
//!
//! This test target has no public API and does not produce a candidate waveform.

use std::{
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_ieee_com_sparam::{
    SelectedP3cCausalityStopV1, enforce_selected_p3c_causality_v1,
    interpolate_selected_p3c_hdiff_v1,
};
use sipi_p3c::{
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
    SelectedP3cSealedS4pIdentityV2, admit_selected_p3c_sealed_s4p_v2,
};

const SOURCE_ENV: &str = "SIPI_P3C_SOURCE";
const ADS_S0_PAYLOAD_ENV: &str = "SIPI_P3C_ADS_S0_HDIFF_PAYLOAD";
const REPORT_ENV: &str = "SIPI_P3C_REPORT";
const RUN_ID_ENV: &str = "SIPI_P3C_RUN_ID";
const REPORT_SCHEMA: &str = "sipi.p3c.ads-s0-product-bounded-dtft-runner.v1";
const PAYLOAD_MAGIC: &[u8] = b"sipi.p3c.ads-s0-hdiff-payload.v1\0";
const ADS_S0_POINTS: usize = 1_024;
const PRODUCT_SAMPLES: usize = 51_200;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;

#[derive(Clone, Copy, Debug, PartialEq)]
struct Complex {
    re: f64,
    im: f64,
}

impl Complex {
    const ONE: Self = Self { re: 1.0, im: 0.0 };
    const ZERO: Self = Self { re: 0.0, im: 0.0 };

    fn add(self, other: Self) -> Self {
        Self {
            re: self.re + other.re,
            im: self.im + other.im,
        }
    }

    fn sub(self, other: Self) -> Self {
        Self {
            re: self.re - other.re,
            im: self.im - other.im,
        }
    }

    fn mul(self, other: Self) -> Self {
        Self {
            re: self.re * other.re - self.im * other.im,
            im: self.re * other.im + self.im * other.re,
        }
    }

    fn scale(self, scalar: f64) -> Self {
        Self {
            re: self.re * scalar,
            im: self.im * scalar,
        }
    }

    fn norm_sqr(self) -> Result<f64, String> {
        let value = self.re.mul_add(self.re, self.im * self.im);
        value
            .is_finite()
            .then_some(value)
            .ok_or_else(|| "numeric".to_owned())
    }
}

#[derive(Debug, PartialEq)]
struct AdsS0Payload {
    frequencies: Vec<f64>,
    hdiff: Vec<Complex>,
    sha256: String,
    byte_length: usize,
}

#[derive(Debug, PartialEq)]
struct Fact {
    manifest_sha256: String,
    record_count: usize,
    bounded_sample_count: usize,
    sample_interval_bits: String,
    causality_iterations: usize,
    causality_stop: &'static str,
    ads_s0_payload_byte_length: usize,
    ads_s0_payload_sha256: String,
    ads_s0_axis_sha256: String,
    ads_s0_hdiff_sha256: String,
    product_dtft_sha256: String,
    delta_sha256: String,
    delta_l2_squared_bits: String,
    delta_max_abs_bits: String,
    delta_max_index: usize,
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute()
        .then_some(path)
        .ok_or_else(|| format!("{name}_not_absolute"))
}

fn required_run_id() -> Result<String, String> {
    let value = env::var(RUN_ID_ENV).map_err(|_| "run_id_missing".to_owned())?;
    if value.is_empty()
        || value.len() > 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
    {
        return Err("run_id_invalid".to_owned());
    }
    Ok(value)
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn read_sha256(path: &Path) -> Result<(u64, String), String> {
    let mut stream = File::open(path).map_err(|_| "source_open".to_owned())?;
    let mut hash = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = stream
            .read(&mut buffer)
            .map_err(|_| "source_read".to_owned())?;
        if read == 0 {
            break;
        }
        length = length
            .checked_add(read as u64)
            .ok_or_else(|| "source_length".to_owned())?;
        hash.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", hash.finalize())))
}

fn source_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = read_sha256(path)?;
    (identity
        == (
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        ))
        .then_some(identity)
        .ok_or_else(|| "source_identity".to_owned())
}

fn read_f64(bytes: &[u8], offset: &mut usize) -> Result<f64, String> {
    let end = offset
        .checked_add(8)
        .ok_or_else(|| "payload_length".to_owned())?;
    let raw: [u8; 8] = bytes
        .get(*offset..end)
        .ok_or_else(|| "payload_length".to_owned())?
        .try_into()
        .map_err(|_| "payload_length".to_owned())?;
    *offset = end;
    let value = f64::from_bits(u64::from_be_bytes(raw));
    value
        .is_finite()
        .then_some(value)
        .ok_or_else(|| "payload_nonfinite".to_owned())
}

fn read_ads_s0_payload(path: &Path) -> Result<AdsS0Payload, String> {
    let bytes = fs::read(path).map_err(|_| "payload_open".to_owned())?;
    let expected = PAYLOAD_MAGIC.len() + 8 + ADS_S0_POINTS * 24;
    if bytes.len() != expected || !bytes.starts_with(PAYLOAD_MAGIC) {
        return Err("payload_shape".to_owned());
    }
    let mut offset = PAYLOAD_MAGIC.len();
    let count = u64::from_be_bytes(
        bytes[offset..offset + 8]
            .try_into()
            .map_err(|_| "payload_count".to_owned())?,
    );
    offset += 8;
    if count != ADS_S0_POINTS as u64 {
        return Err("payload_count".to_owned());
    }
    let mut frequencies = Vec::with_capacity(ADS_S0_POINTS);
    let mut hdiff = Vec::with_capacity(ADS_S0_POINTS);
    for _ in 0..ADS_S0_POINTS {
        let frequency = read_f64(&bytes, &mut offset)?;
        let value = Complex {
            re: read_f64(&bytes, &mut offset)?,
            im: read_f64(&bytes, &mut offset)?,
        };
        frequencies.push(frequency);
        hdiff.push(value);
    }
    if offset != bytes.len() || frequencies.windows(2).any(|pair| pair[1] <= pair[0]) {
        return Err("payload_axis".to_owned());
    }
    Ok(AdsS0Payload {
        frequencies,
        hdiff,
        sha256: sha256(&bytes),
        byte_length: bytes.len(),
    })
}

fn finite_dtft(samples: &[f64], frequency: f64, dt: f64) -> Result<Complex, String> {
    if samples.is_empty()
        || !frequency.is_finite()
        || !dt.is_finite()
        || dt <= 0.0
        || samples.iter().any(|value| !value.is_finite())
    {
        return Err("dtft_input".to_owned());
    }
    let angle = -std::f64::consts::TAU * frequency * dt;
    let (sin, cos) = angle.sin_cos();
    let rotor = Complex { re: cos, im: sin };
    let mut phase = Complex::ONE;
    let mut sum = Complex::ZERO;
    for sample in samples {
        sum = sum.add(phase.scale(*sample));
        if !sum.re.is_finite() || !sum.im.is_finite() {
            return Err("dtft_numeric".to_owned());
        }
        phase = phase.mul(rotor);
        if !phase.re.is_finite() || !phase.im.is_finite() {
            return Err("dtft_numeric".to_owned());
        }
    }
    Ok(sum)
}

fn sequence_digest(domain: &[u8], axis: &[f64], values: &[Complex]) -> Result<String, String> {
    if axis.len() != ADS_S0_POINTS
        || values.len() != ADS_S0_POINTS
        || axis.windows(2).any(|pair| pair[1] <= pair[0])
    {
        return Err("digest_shape".to_owned());
    }
    let mut hash = Sha256::new();
    hash.update(domain);
    hash.update((axis.len() as u64).to_be_bytes());
    hash.update(DT_BITS.to_be_bytes());
    for (frequency, value) in axis.iter().zip(values) {
        if !frequency.is_finite() || !value.re.is_finite() || !value.im.is_finite() {
            return Err("digest_nonfinite".to_owned());
        }
        hash.update(frequency.to_bits().to_be_bytes());
        hash.update(value.re.to_bits().to_be_bytes());
        hash.update(value.im.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn axis_digest(axis: &[f64]) -> Result<String, String> {
    if axis.len() != ADS_S0_POINTS
        || axis
            .windows(2)
            .any(|pair| !pair[0].is_finite() || pair[1] <= pair[0])
    {
        return Err("axis".to_owned());
    }
    let mut hash = Sha256::new();
    hash.update(b"sipi.p3c.ads-s0-product-bounded.axis.v1\0");
    hash.update((axis.len() as u64).to_be_bytes());
    for value in axis {
        hash.update(value.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn l2_and_max(values: &[Complex]) -> Result<(f64, f64, usize), String> {
    if values.len() != ADS_S0_POINTS {
        return Err("delta_shape".to_owned());
    }
    let mut total = 0.0;
    let mut max_value = -1.0;
    let mut max_index = 0;
    for (index, value) in values.iter().copied().enumerate() {
        let magnitude_squared = value.norm_sqr()?;
        total += magnitude_squared;
        if !total.is_finite() {
            return Err("delta_numeric".to_owned());
        }
        let magnitude = magnitude_squared.sqrt();
        if !magnitude.is_finite() {
            return Err("delta_numeric".to_owned());
        }
        if magnitude > max_value {
            max_value = magnitude;
            max_index = index;
        }
    }
    Ok((total, max_value, max_index))
}

fn fresh_root() -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-ads-s0-dtft-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn evaluate(source: &Path, payload_path: &Path, run_id: &str) -> Result<Fact, String> {
    let before = source_identity(source)?;
    let payload = read_ads_s0_payload(payload_path)?;
    let root = fresh_root()?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root).map_err(|_| "artifact_root".to_owned())?;
        let artifact_id = format!("ads-s0-product-bounded-dtft-{run_id}");
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
        let manifest = sha256(
            &fs::read(root.join(&artifact_id).join("success.json"))
                .map_err(|_| "manifest".to_owned())?,
        );
        let reader =
            ArtifactRoot::open_existing(&root).map_err(|_| "artifact_reopen".to_owned())?;
        let identity = SelectedP3cSealedS4pIdentityV2::try_new(&artifact_id, &manifest)
            .map_err(|_| "identity".to_owned())?;
        let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &identity)
            .map_err(|_| "admission".to_owned())?;
        let uniform = interpolate_selected_p3c_hdiff_v1(admitted.transfer())
            .map_err(|_| "interpolation".to_owned())?;
        let bounded =
            enforce_selected_p3c_causality_v1(&uniform).map_err(|_| "causality".to_owned())?;
        if bounded.sample_count() != PRODUCT_SAMPLES
            || bounded.sample_interval().get().to_bits() != DT_BITS
        {
            return Err("bounded_grid".to_owned());
        }
        let samples = bounded
            .samples()
            .iter()
            .map(|value| value.get())
            .collect::<Vec<_>>();
        let product = payload
            .frequencies
            .iter()
            .copied()
            .map(|frequency| finite_dtft(&samples, frequency, bounded.sample_interval().get()))
            .collect::<Result<Vec<_>, _>>()?;
        let delta = product
            .iter()
            .copied()
            .zip(payload.hdiff.iter().copied())
            .map(|(product, ads)| product.sub(ads))
            .collect::<Vec<_>>();
        let (l2_squared, max_abs, max_index) = l2_and_max(&delta)?;
        let stop = match bounded.stop() {
            SelectedP3cCausalityStopV1::RelativeError => "relative_error",
            SelectedP3cCausalityStopV1::SuccessiveErrorDifference => "successive_error_difference",
        };
        Ok(Fact {
            manifest_sha256: manifest,
            record_count: admitted.record_count(),
            bounded_sample_count: bounded.sample_count(),
            sample_interval_bits: format!("{DT_BITS:016x}"),
            causality_iterations: bounded.iteration_count(),
            causality_stop: stop,
            ads_s0_payload_byte_length: payload.byte_length,
            ads_s0_payload_sha256: payload.sha256,
            ads_s0_axis_sha256: axis_digest(&payload.frequencies)?,
            ads_s0_hdiff_sha256: sequence_digest(
                b"sipi.p3c.ads-s0-product-bounded.ads-hdiff.v1\0",
                &payload.frequencies,
                &payload.hdiff,
            )?,
            product_dtft_sha256: sequence_digest(
                b"sipi.p3c.ads-s0-product-bounded.product-dtft.v1\0",
                &payload.frequencies,
                &product,
            )?,
            delta_sha256: sequence_digest(
                b"sipi.p3c.ads-s0-product-bounded.delta.v1\0",
                &payload.frequencies,
                &delta,
            )?,
            delta_l2_squared_bits: format!("{:016x}", l2_squared.to_bits()),
            delta_max_abs_bits: format!("{:016x}", max_abs.to_bits()),
            delta_max_index: max_index,
        })
    })();
    let cleanup = fs::remove_dir_all(root).map_err(|_| "cleanup".to_owned());
    match (result, cleanup) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error), Ok(())) | (_, Err(error)) => Err(error),
    }
}

fn json(fact: &Fact) -> String {
    format!(
        "{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"observed\",\"manifest_sha256\":\"{}\",\"record_count\":{},\"bounded_sample_count\":{},\"sample_interval_bits\":\"{}\",\"causality_iterations\":{},\"causality_stop\":\"{}\",\"ads_s0_payload_byte_length\":{},\"ads_s0_payload_sha256\":\"{}\",\"ads_s0_axis_sha256\":\"{}\",\"ads_s0_hdiff_sha256\":\"{}\",\"product_dtft_sha256\":\"{}\",\"delta_sha256\":\"{}\",\"delta_l2_squared_bits\":\"{}\",\"delta_max_abs_bits\":\"{}\",\"delta_max_index\":{},\"cleanup_status\":\"complete\"}}\n",
        fact.manifest_sha256,
        fact.record_count,
        fact.bounded_sample_count,
        fact.sample_interval_bits,
        fact.causality_iterations,
        fact.causality_stop,
        fact.ads_s0_payload_byte_length,
        fact.ads_s0_payload_sha256,
        fact.ads_s0_axis_sha256,
        fact.ads_s0_hdiff_sha256,
        fact.product_dtft_sha256,
        fact.delta_sha256,
        fact.delta_l2_squared_bits,
        fact.delta_max_abs_bits,
        fact.delta_max_index
    )
}

#[test]
fn unit_impulse_has_unity_dtft_at_every_frequency() {
    for frequency in [0.0, 1.0, 12.5] {
        assert_eq!(
            finite_dtft(&[1.0, 0.0, 0.0], frequency, 0.25).unwrap(),
            Complex::ONE
        );
    }
}

#[test]
fn delayed_impulse_uses_negative_sign_and_sample_zero_origin() {
    let result = finite_dtft(&[0.0, 0.0, 1.0], 0.125, 1.0).unwrap();
    assert!((result.re - 0.0).abs() <= 1.0e-12);
    assert!((result.im - -1.0).abs() <= 1.0e-12);
}

#[test]
fn alternating_sequence_has_zero_dc_and_real_nyquist_sum() {
    let input = [1.0, -1.0, 1.0, -1.0];
    assert_eq!(finite_dtft(&input, 0.0, 1.0).unwrap(), Complex::ZERO);
    let nyquist = finite_dtft(&input, 0.5, 1.0).unwrap();
    assert!((nyquist.re - 4.0).abs() <= 1.0e-12 && nyquist.im.abs() <= 1.0e-12);
}

#[test]
fn dtft_rejects_nonfinite_input() {
    assert_eq!(
        finite_dtft(&[f64::NAN], 0.0, 1.0).unwrap_err(),
        "dtft_input"
    );
}

#[test]
#[ignore = "external-only ADS S0/product bounded DTFT observation"]
fn p3c_ads_s0_product_bounded_dtft_runner_v1() {
    let source = required_path(SOURCE_ENV).unwrap();
    let payload = required_path(ADS_S0_PAYLOAD_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    let run_id = required_run_id().unwrap();
    assert!(!report.exists());
    let value = evaluate(&source, &payload, &run_id).unwrap();
    let output = json(&value);
    serde_json::from_str::<serde_json::Value>(&output).unwrap();
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, output).unwrap();
}
