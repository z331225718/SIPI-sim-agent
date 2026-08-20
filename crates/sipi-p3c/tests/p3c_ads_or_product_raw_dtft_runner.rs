//! External-only ADS-CMP1_OR to product raw-periodic DTFT observation.
//!
//! This test target has no public API and does not generate a waveform.

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
    interpolate_selected_p3c_hdiff_v1, inverse_selected_p3c_uniform_spectrum_v1,
};
use sipi_p3c::{
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
    SelectedP3cSealedS4pIdentityV2, admit_selected_p3c_sealed_s4p_v2,
};

const SOURCE_ENV: &str = "SIPI_P3C_SOURCE";
const ADS_OR_PAYLOAD_ENV: &str = "SIPI_P3C_ADS_OR_HDIFF_PAYLOAD";
const REPORT_ENV: &str = "SIPI_P3C_REPORT";
const RUN_ID_ENV: &str = "SIPI_P3C_RUN_ID";
const SCHEMA: &str = "sipi.p3c.ads-or-product-raw-dtft-runner.v1";
const PAYLOAD_MAGIC: &[u8] = b"sipi.p3c.ads-or-hdiff-payload.v1\0";
const PRODUCT_SAMPLES: usize = 51_200;
const MAX_ADS_OR_POINTS: usize = 4_096;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;

#[derive(Clone, Copy, Debug, PartialEq)]
struct Complex {
    re: f64,
    im: f64,
}

impl Complex {
    const ONE: Self = Self { re: 1.0, im: 0.0 };
    const ZERO: Self = Self { re: 0.0, im: 0.0 };
    fn add(self, rhs: Self) -> Self {
        Self {
            re: self.re + rhs.re,
            im: self.im + rhs.im,
        }
    }
    fn sub(self, rhs: Self) -> Self {
        Self {
            re: self.re - rhs.re,
            im: self.im - rhs.im,
        }
    }
    fn mul(self, rhs: Self) -> Self {
        Self {
            re: self.re * rhs.re - self.im * rhs.im,
            im: self.re * rhs.im + self.im * rhs.re,
        }
    }
    fn scale(self, rhs: f64) -> Self {
        Self {
            re: self.re * rhs,
            im: self.im * rhs,
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

#[derive(Debug)]
struct AdsPayload {
    frequencies: Vec<f64>,
    hdiff: Vec<Complex>,
    byte_length: usize,
    sha256: String,
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute()
        .then_some(path)
        .ok_or_else(|| format!("{name}_not_absolute"))
}

fn run_id() -> Result<String, String> {
    let value = env::var(RUN_ID_ENV).map_err(|_| "run_id_missing".to_owned())?;
    (!value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-'))
    .then_some(value)
    .ok_or_else(|| "run_id_invalid".to_owned())
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn read_hash(path: &Path) -> Result<(u64, String), String> {
    let mut stream = File::open(path).map_err(|_| "source_open".to_owned())?;
    let mut digest = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 65536];
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
        digest.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", digest.finalize())))
}

fn source_identity(path: &Path) -> Result<(u64, String), String> {
    let value = read_hash(path)?;
    (value
        == (
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        ))
        .then_some(value)
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

fn read_payload(path: &Path) -> Result<AdsPayload, String> {
    let bytes = fs::read(path).map_err(|_| "payload_open".to_owned())?;
    if !bytes.starts_with(PAYLOAD_MAGIC) || bytes.len() < PAYLOAD_MAGIC.len() + 8 {
        return Err("payload_shape".to_owned());
    }
    let mut offset = PAYLOAD_MAGIC.len();
    let count = u64::from_be_bytes(
        bytes[offset..offset + 8]
            .try_into()
            .map_err(|_| "payload_count".to_owned())?,
    ) as usize;
    offset += 8;
    if !(2..=MAX_ADS_OR_POINTS).contains(&count)
        || bytes.len() != PAYLOAD_MAGIC.len() + 8 + count * 24
    {
        return Err("payload_shape".to_owned());
    }
    let mut frequencies = Vec::with_capacity(count);
    let mut hdiff = Vec::with_capacity(count);
    for _ in 0..count {
        frequencies.push(read_f64(&bytes, &mut offset)?);
        hdiff.push(Complex {
            re: read_f64(&bytes, &mut offset)?,
            im: read_f64(&bytes, &mut offset)?,
        });
    }
    if offset != bytes.len() || frequencies.windows(2).any(|pair| pair[1] <= pair[0]) {
        return Err("payload_axis".to_owned());
    }
    Ok(AdsPayload {
        frequencies,
        hdiff,
        byte_length: bytes.len(),
        sha256: hash(&bytes),
    })
}

fn finite_dtft(samples: &[f64], frequency: f64, dt: f64) -> Result<Complex, String> {
    if samples.len() != PRODUCT_SAMPLES
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
    if axis.len() < 2
        || axis.len() != values.len()
        || axis
            .windows(2)
            .any(|pair| !pair[0].is_finite() || pair[1] <= pair[0])
    {
        return Err("digest_shape".to_owned());
    }
    let mut digest = Sha256::new();
    digest.update(domain);
    digest.update((axis.len() as u64).to_be_bytes());
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
    if axis.len() < 2
        || axis
            .windows(2)
            .any(|pair| !pair[0].is_finite() || pair[1] <= pair[0])
    {
        return Err("axis".to_owned());
    }
    let mut digest = Sha256::new();
    digest.update(b"sipi.p3c.ads-or-product-raw.axis.v1\0");
    digest.update((axis.len() as u64).to_be_bytes());
    for value in axis {
        digest.update(value.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn l2_and_max(values: &[Complex]) -> Result<(f64, f64, usize), String> {
    if values.len() < 2 {
        return Err("delta_shape".to_owned());
    }
    let mut total = 0.0;
    let mut maximum = -1.0;
    let mut maximum_index = 0;
    for (index, value) in values.iter().copied().enumerate() {
        let squared = value.norm_sqr()?;
        total += squared;
        let magnitude = squared.sqrt();
        if !(total.is_finite() && magnitude.is_finite()) {
            return Err("delta_numeric".to_owned());
        }
        if magnitude > maximum {
            maximum = magnitude;
            maximum_index = index;
        }
    }
    Ok((total, maximum, maximum_index))
}

fn fresh_root() -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock".to_owned())?
        .as_nanos();
    let path = env::temp_dir().join(format!("sipi-p3c-ads-or-raw-dtft-{nonce}"));
    fs::create_dir(&path).map_err(|_| "root_create".to_owned())?;
    Ok(path)
}

fn evaluate(source: &Path, payload_path: &Path, id: &str) -> Result<serde_json::Value, String> {
    let before = source_identity(source)?;
    let payload = read_payload(payload_path)?;
    let root = fresh_root()?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root).map_err(|_| "artifact_root".to_owned())?;
        let artifact_id = format!("ads-or-product-raw-dtft-{id}");
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
        let manifest = hash(
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
        if raw.sample_count() != PRODUCT_SAMPLES || raw.sample_interval().get().to_bits() != DT_BITS
        {
            return Err("raw_grid".to_owned());
        }
        let samples = raw
            .samples()
            .iter()
            .map(|value| value.get())
            .collect::<Vec<_>>();
        let product = payload
            .frequencies
            .iter()
            .copied()
            .map(|frequency| finite_dtft(&samples, frequency, raw.sample_interval().get()))
            .collect::<Result<Vec<_>, _>>()?;
        let delta = product
            .iter()
            .copied()
            .zip(payload.hdiff.iter().copied())
            .map(|(product, ads)| product.sub(ads))
            .collect::<Vec<_>>();
        let (l2_squared, maximum, maximum_index) = l2_and_max(&delta)?;
        Ok(
            serde_json::json!({"schema": SCHEMA, "status": "observed", "manifest_sha256": manifest, "record_count": admitted.record_count(), "raw_sample_count": raw.sample_count(), "sample_interval_bits": format!("{DT_BITS:016x}"), "ads_or_payload_byte_length": payload.byte_length, "ads_or_payload_sha256": payload.sha256, "ads_or_axis_sha256": axis_digest(&payload.frequencies)?, "ads_or_hdiff_sha256": sequence_digest(b"sipi.p3c.ads-or-product-raw.ads-hdiff.v1\0", &payload.frequencies, &payload.hdiff)?, "product_raw_dtft_sha256": sequence_digest(b"sipi.p3c.ads-or-product-raw.product-dtft.v1\0", &payload.frequencies, &product)?, "delta_sha256": sequence_digest(b"sipi.p3c.ads-or-product-raw.delta.v1\0", &payload.frequencies, &delta)?, "delta_l2_squared_bits": format!("{:016x}", l2_squared.to_bits()), "delta_max_abs_bits": format!("{:016x}", maximum.to_bits()), "delta_max_index": maximum_index, "cleanup_status": "complete"}),
        )
    })();
    let cleanup = fs::remove_dir_all(root).map_err(|_| "cleanup".to_owned());
    match (result, cleanup) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error), Ok(())) | (_, Err(error)) => Err(error),
    }
}

#[test]
fn unit_impulse_is_unity_at_all_arbitrary_nodes() {
    let mut input = vec![0.0; PRODUCT_SAMPLES];
    input[0] = 1.0;
    for frequency in [0.0, 1.0, 12.5] {
        assert_eq!(finite_dtft(&input, frequency, 0.25).unwrap(), Complex::ONE);
    }
}
#[test]
fn delayed_impulse_uses_negative_sign() {
    let mut input = vec![0.0; PRODUCT_SAMPLES];
    input[2] = 1.0;
    let value = finite_dtft(&input, 0.125, 1.0).unwrap();
    assert!(value.re.abs() <= 1.0e-12 && (value.im + 1.0).abs() <= 1.0e-12);
}
#[test]
fn nonfinite_and_short_sequences_fail_closed() {
    assert_eq!(
        finite_dtft(&[f64::NAN], 0.0, 1.0).unwrap_err(),
        "dtft_input"
    );
}

#[test]
#[ignore = "external-only ADS OR/product raw DTFT observation"]
fn p3c_ads_or_product_raw_dtft_runner_v1() {
    let source = required_path(SOURCE_ENV).unwrap();
    let payload = required_path(ADS_OR_PAYLOAD_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    assert!(!report.exists());
    let value = evaluate(&source, &payload, &run_id().unwrap()).unwrap();
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, format!("{}\n", value)).unwrap();
}
