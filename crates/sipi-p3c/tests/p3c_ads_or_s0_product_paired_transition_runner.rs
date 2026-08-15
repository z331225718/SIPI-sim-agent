//! External-only paired ADS OR/S0 and product raw/bounded transition observation.
//!
//! The test has no public API. It evaluates only an exact 1024-node common axis.

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
    enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1,
    inverse_selected_p3c_uniform_spectrum_v1, SelectedP3cCausalityStopV1,
};
use sipi_p3c::{
    admit_selected_p3c_sealed_s4p_v2, SelectedP3cSealedS4pIdentityV2,
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SOURCE";
const PAYLOAD_ENV: &str = "SIPI_P3C_ADS_OR_S0_HDIFF_PAYLOAD";
const REPORT_ENV: &str = "SIPI_P3C_REPORT";
const RUN_ID_ENV: &str = "SIPI_P3C_RUN_ID";
const SCHEMA: &str = "sipi.p3c.ads-or-s0-product-paired-transition-runner.v1";
const MAGIC: &[u8] = b"sipi.p3c.ads-or-s0-hdiff-payload.v1\0";
const POINTS: usize = 1_024;
const SAMPLES: usize = 51_200;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;

#[derive(Clone, Copy, Debug, PartialEq)]
struct Complex {
    re: f64,
    im: f64,
}

impl Complex {
    const ZERO: Self = Self { re: 0.0, im: 0.0 };
    const ONE: Self = Self { re: 1.0, im: 0.0 };
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
        let result = self.re.mul_add(self.re, self.im * self.im);
        result
            .is_finite()
            .then_some(result)
            .ok_or_else(|| "numeric".to_owned())
    }
}

struct Payload {
    axis: Vec<f64>,
    original: Vec<Complex>,
    s0: Vec<Complex>,
    length: usize,
    sha256: String,
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute()
        .then_some(path)
        .ok_or_else(|| format!("{name}_not_absolute"))
}

fn run_id() -> Result<String, String> {
    let id = env::var(RUN_ID_ENV).map_err(|_| "run_id_missing".to_owned())?;
    (!id.is_empty()
        && id.len() <= 64
        && id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-'))
    .then_some(id)
    .ok_or_else(|| "run_id_invalid".to_owned())
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn file_identity(path: &Path) -> Result<(u64, String), String> {
    let mut stream = File::open(path).map_err(|_| "source_open".to_owned())?;
    let mut digest = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 65_536];
    loop {
        let count = stream
            .read(&mut buffer)
            .map_err(|_| "source_read".to_owned())?;
        if count == 0 {
            break;
        }
        length = length
            .checked_add(count as u64)
            .ok_or_else(|| "source_length".to_owned())?;
        digest.update(&buffer[..count]);
    }
    Ok((length, format!("{:x}", digest.finalize())))
}

fn selected_source(path: &Path) -> Result<(u64, String), String> {
    let identity = file_identity(path)?;
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

fn read_payload(path: &Path) -> Result<Payload, String> {
    let bytes = fs::read(path).map_err(|_| "payload_open".to_owned())?;
    let expected = MAGIC.len() + 8 + POINTS * 40;
    if bytes.len() != expected || !bytes.starts_with(MAGIC) {
        return Err("payload_shape".to_owned());
    }
    let mut offset = MAGIC.len();
    let count = u64::from_be_bytes(
        bytes[offset..offset + 8]
            .try_into()
            .map_err(|_| "payload_count".to_owned())?,
    );
    offset += 8;
    if count != POINTS as u64 {
        return Err("payload_count".to_owned());
    }
    let mut axis = Vec::with_capacity(POINTS);
    let mut original = Vec::with_capacity(POINTS);
    let mut s0 = Vec::with_capacity(POINTS);
    for _ in 0..POINTS {
        axis.push(read_f64(&bytes, &mut offset)?);
        original.push(Complex {
            re: read_f64(&bytes, &mut offset)?,
            im: read_f64(&bytes, &mut offset)?,
        });
        s0.push(Complex {
            re: read_f64(&bytes, &mut offset)?,
            im: read_f64(&bytes, &mut offset)?,
        });
    }
    if offset != bytes.len() || axis.windows(2).any(|pair| pair[1] <= pair[0]) {
        return Err("payload_axis".to_owned());
    }
    Ok(Payload {
        axis,
        original,
        s0,
        length: bytes.len(),
        sha256: sha256(&bytes),
    })
}

fn finite_dtft(samples: &[f64], frequency: f64, dt: f64) -> Result<Complex, String> {
    if samples.len() != SAMPLES
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
        phase = phase.mul(rotor);
        if !(sum.re.is_finite()
            && sum.im.is_finite()
            && phase.re.is_finite()
            && phase.im.is_finite())
        {
            return Err("dtft_numeric".to_owned());
        }
    }
    Ok(sum)
}

fn sequence_digest(domain: &[u8], axis: &[f64], values: &[Complex]) -> Result<String, String> {
    if axis.len() != POINTS
        || values.len() != POINTS
        || axis
            .windows(2)
            .any(|pair| !pair[0].is_finite() || pair[1] <= pair[0])
    {
        return Err("digest_shape".to_owned());
    }
    let mut digest = Sha256::new();
    digest.update(domain);
    digest.update((POINTS as u64).to_be_bytes());
    digest.update(DT_BITS.to_be_bytes());
    for (frequency, value) in axis.iter().zip(values) {
        if !(frequency.is_finite() && value.re.is_finite() && value.im.is_finite()) {
            return Err("digest_nonfinite".to_owned());
        }
        digest.update(frequency.to_bits().to_be_bytes());
        digest.update(value.re.to_bits().to_be_bytes());
        digest.update(value.im.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn axis_digest(axis: &[f64]) -> Result<String, String> {
    if axis.len() != POINTS
        || axis
            .windows(2)
            .any(|pair| !pair[0].is_finite() || pair[1] <= pair[0])
    {
        return Err("axis".to_owned());
    }
    let mut digest = Sha256::new();
    digest.update(b"sipi.p3c.ads-or-s0.paired.axis.v1\0");
    digest.update((POINTS as u64).to_be_bytes());
    for value in axis {
        digest.update(value.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn l2_and_max(values: &[Complex]) -> Result<(f64, f64, usize), String> {
    if values.len() != POINTS {
        return Err("delta_shape".to_owned());
    }
    let mut total = 0.0;
    let mut maximum = -1.0;
    let mut index = 0;
    for (current, value) in values.iter().copied().enumerate() {
        let squared = value.norm_sqr()?;
        total += squared;
        let magnitude = squared.sqrt();
        if !(total.is_finite() && magnitude.is_finite()) {
            return Err("delta_numeric".to_owned());
        }
        if magnitude > maximum {
            maximum = magnitude;
            index = current;
        }
    }
    Ok((total, maximum, index))
}

fn transitions(
    original: &[Complex],
    s0: &[Complex],
    raw: &[Complex],
    bounded: &[Complex],
) -> Result<(Vec<Complex>, Vec<Complex>, Vec<Complex>), String> {
    if original.len() != POINTS
        || s0.len() != POINTS
        || raw.len() != POINTS
        || bounded.len() != POINTS
    {
        return Err("transition_shape".to_owned());
    }
    let ads = s0
        .iter()
        .zip(original)
        .map(|(after, before)| after.sub(*before))
        .collect::<Vec<_>>();
    let product = bounded
        .iter()
        .zip(raw)
        .map(|(after, before)| after.sub(*before))
        .collect::<Vec<_>>();
    let paired = ads
        .iter()
        .zip(&product)
        .map(|(ads, product)| ads.sub(*product))
        .collect::<Vec<_>>();
    Ok((ads, product, paired))
}

fn fresh_root() -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-ads-or-s0-paired-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn evaluate(source: &Path, payload_path: &Path, id: &str) -> Result<serde_json::Value, String> {
    let before = selected_source(source)?;
    let payload = read_payload(payload_path)?;
    let root = fresh_root()?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root).map_err(|_| "artifact_root".to_owned())?;
        let artifact_id = format!("ads-or-s0-paired-{id}");
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
        if selected_source(source)? != before {
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
        let raw = inverse_selected_p3c_uniform_spectrum_v1(&uniform)
            .map_err(|_| "raw_inverse".to_owned())?;
        let bounded =
            enforce_selected_p3c_causality_v1(&uniform).map_err(|_| "causality".to_owned())?;
        if raw.sample_count() != SAMPLES
            || bounded.sample_count() != SAMPLES
            || raw.sample_interval().get().to_bits() != DT_BITS
            || bounded.sample_interval().get().to_bits() != DT_BITS
        {
            return Err("product_grid".to_owned());
        }
        let raw_values = raw
            .samples()
            .iter()
            .map(|sample| sample.get())
            .collect::<Vec<_>>();
        let bounded_values = bounded
            .samples()
            .iter()
            .map(|sample| sample.get())
            .collect::<Vec<_>>();
        let product_raw = payload
            .axis
            .iter()
            .map(|frequency| finite_dtft(&raw_values, *frequency, raw.sample_interval().get()))
            .collect::<Result<Vec<_>, _>>()?;
        let product_bounded = payload
            .axis
            .iter()
            .map(|frequency| {
                finite_dtft(&bounded_values, *frequency, bounded.sample_interval().get())
            })
            .collect::<Result<Vec<_>, _>>()?;
        let (ads_transition, product_transition, paired_delta) = transitions(
            &payload.original,
            &payload.s0,
            &product_raw,
            &product_bounded,
        )?;
        let (l2, maximum, index) = l2_and_max(&paired_delta)?;
        let stop = match bounded.stop() {
            SelectedP3cCausalityStopV1::RelativeError => "relative_error",
            SelectedP3cCausalityStopV1::SuccessiveErrorDifference => "successive_error_difference",
        };
        Ok(serde_json::json!({
            "schema": SCHEMA, "status": "observed", "manifest_sha256": manifest, "record_count": admitted.record_count(), "common_node_count": POINTS,
            "sample_interval_bits": format!("{DT_BITS:016x}"), "raw_sample_count": raw.sample_count(), "bounded_sample_count": bounded.sample_count(), "causality_iterations": bounded.iteration_count(), "causality_stop": stop,
            "ads_payload_byte_length": payload.length, "ads_payload_sha256": payload.sha256, "axis_sha256": axis_digest(&payload.axis)?,
            "ads_original_sha256": sequence_digest(b"sipi.p3c.ads-or-s0.paired.original.v1\0", &payload.axis, &payload.original)?, "ads_s0_sha256": sequence_digest(b"sipi.p3c.ads-or-s0.paired.s0.v1\0", &payload.axis, &payload.s0)?,
            "product_raw_sha256": sequence_digest(b"sipi.p3c.ads-or-s0.paired.raw.v1\0", &payload.axis, &product_raw)?, "product_bounded_sha256": sequence_digest(b"sipi.p3c.ads-or-s0.paired.bounded.v1\0", &payload.axis, &product_bounded)?,
            "ads_transition_sha256": sequence_digest(b"sipi.p3c.ads-or-s0.paired.ads-transition.v1\0", &payload.axis, &ads_transition)?, "product_transition_sha256": sequence_digest(b"sipi.p3c.ads-or-s0.paired.product-transition.v1\0", &payload.axis, &product_transition)?, "paired_delta_sha256": sequence_digest(b"sipi.p3c.ads-or-s0.paired.delta.v1\0", &payload.axis, &paired_delta)?,
            "paired_delta_l2_squared_bits": format!("{:016x}", l2.to_bits()), "paired_delta_max_abs_bits": format!("{:016x}", maximum.to_bits()), "paired_delta_max_index": index, "cleanup_status": "complete"
        }))
    })();
    let cleanup = fs::remove_dir_all(root).map_err(|_| "cleanup".to_owned());
    match (result, cleanup) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error), Ok(())) | (_, Err(error)) => Err(error),
    }
}

#[test]
fn paired_transition_subtracts_after_minus_before_on_both_sides() {
    let values = vec![Complex::ZERO; POINTS];
    let mut s0 = values.clone();
    let mut bounded = values.clone();
    s0[0] = Complex { re: 4.0, im: -1.0 };
    bounded[0] = Complex { re: 3.0, im: -2.0 };
    let (ads, product, paired) = transitions(&values, &s0, &values, &bounded).unwrap();
    assert_eq!(ads[0], Complex { re: 4.0, im: -1.0 });
    assert_eq!(product[0], Complex { re: 3.0, im: -2.0 });
    assert_eq!(paired[0], Complex { re: 1.0, im: 1.0 });
}

#[test]
fn delayed_impulse_uses_negative_sign_and_zero_time_origin() {
    let mut samples = vec![0.0; SAMPLES];
    samples[2] = 1.0;
    let value = finite_dtft(&samples, 0.125, 1.0).unwrap();
    assert!(value.re.abs() <= 1.0e-12 && (value.im + 1.0).abs() <= 1.0e-12);
}

#[test]
fn transition_shape_rejects_wrong_axis_length() {
    assert_eq!(
        transitions(&[], &[], &[], &[]).unwrap_err(),
        "transition_shape"
    );
}

#[test]
#[ignore = "external-only ADS OR/S0 paired transition observation"]
fn p3c_ads_or_s0_product_paired_transition_runner_v1() {
    let source = required_path(SOURCE_ENV).unwrap();
    let payload = required_path(PAYLOAD_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    assert!(!report.exists());
    let value = evaluate(&source, &payload, &run_id().unwrap()).unwrap();
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, format!("{value}\n")).unwrap();
}
