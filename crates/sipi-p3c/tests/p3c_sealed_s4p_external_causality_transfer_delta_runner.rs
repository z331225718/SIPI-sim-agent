#![forbid(unsafe_code)]

//! External-only observation of the selected bounded-causality transfer delta.
//! It does not generate a candidate waveform or alter any product policy.

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
use sipi_ieee_com_sparam::{
    enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1,
    inverse_selected_p3c_uniform_spectrum_v1, SelectedP3cCausalityStopV1,
};
use sipi_p3c::{
    admit_selected_p3c_sealed_s4p_v2, SelectedP3cSealedS4pIdentityV2,
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REPORT_ENV: &str = "SIPI_P3C_CAUSALITY_TRANSFER_DELTA_REPORT";
const REPORT_SCHEMA: &str = "sipi.p3c.sealed-s4p-causality-transfer-delta-runner.v1";
const SAMPLE_COUNT: usize = 51_200;
const ONE_SIDED_BINS: usize = 25_601;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;
const DF_BITS: u64 = 0x4173_12d0_0000_0000; // 20 MHz
const FACTORS: &[usize] = &[32, 32, 2, 25];
const BANDS: [(usize, usize); 4] = [(0, 1), (1, 801), (801, 2001), (2001, ONE_SIDED_BINS)];

#[derive(Clone, Copy, Debug)]
struct Complex {
    re: f64,
    im: f64,
}

impl Complex {
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
    fn norm_sqr(self) -> Result<f64, String> {
        let value = self.re.mul_add(self.re, self.im * self.im);
        value
            .is_finite()
            .then_some(value)
            .ok_or_else(|| "numeric".to_owned())
    }
}

#[derive(Debug, Eq, PartialEq)]
struct BandFact {
    raw_energy_bits: String,
    bounded_energy_bits: String,
    delta_energy_bits: String,
}

#[derive(Debug, Eq, PartialEq)]
struct BinFact {
    index: usize,
    raw_re_bits: String,
    raw_im_bits: String,
    bounded_re_bits: String,
    bounded_im_bits: String,
    delta_re_bits: String,
    delta_im_bits: String,
}

#[derive(Debug, Eq, PartialEq)]
struct RunFact {
    source_manifest_sha256: String,
    record_count: usize,
    uniform_bin_count: usize,
    raw_sample_count: usize,
    bounded_sample_count: usize,
    sample_interval_bits: String,
    frequency_step_bits: String,
    iteration_count: usize,
    final_error_bits: String,
    stop: &'static str,
    raw_response_sha256: String,
    bounded_response_sha256: String,
    raw_spectrum_sha256: String,
    bounded_spectrum_sha256: String,
    delta_spectrum_sha256: String,
    residual_peak_frequency_bracket: [BinFact; 2],
    bands: [BandFact; 4],
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
    let mut hash = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader
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
    let identity = sha256_reader(File::open(path).map_err(|_| "source_open".to_owned())?)?;
    (identity
        == (
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        ))
        .then_some(identity)
        .ok_or_else(|| "source_identity".to_owned())
}

fn fresh_root(index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-causality-transfer-delta-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn response_digest(role: &[u8], samples: &[f64]) -> Result<String, String> {
    if samples.len() != SAMPLE_COUNT || samples.iter().any(|value| !value.is_finite()) {
        return Err("response".to_owned());
    }
    let mut hash = Sha256::new();
    hash.update(b"sipi.p3c.selected-causality-transfer-delta-response.v1\0");
    hash.update(role);
    hash.update((samples.len() as u64).to_be_bytes());
    hash.update(DT_BITS.to_be_bytes());
    for value in samples {
        hash.update(value.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn factorized_dft(values: &[Complex], factors: &[usize]) -> Result<Vec<Complex>, String> {
    if factors.is_empty() {
        return (values.len() == 1)
            .then_some(values.to_vec())
            .ok_or_else(|| "dft_factorization".to_owned());
    }
    let radix = factors[0];
    if radix < 2 || values.len() % radix != 0 {
        return Err("dft_factorization".to_owned());
    }
    let inner = values.len() / radix;
    let mut branches = Vec::with_capacity(radix);
    for branch in 0..radix {
        let child = (0..inner)
            .map(|offset| values[branch + radix * offset])
            .collect::<Vec<_>>();
        branches.push(factorized_dft(&child, &factors[1..])?);
    }
    let mut output = vec![Complex::ZERO; values.len()];
    for inner_frequency in 0..inner {
        for outer_frequency in 0..radix {
            let frequency = inner_frequency + inner * outer_frequency;
            let mut sum = Complex::ZERO;
            for branch in 0..radix {
                let angle =
                    -std::f64::consts::TAU * (frequency * branch) as f64 / values.len() as f64;
                let (sin, cos) = angle.sin_cos();
                sum = sum.add(branches[branch][inner_frequency].mul(Complex { re: cos, im: sin }));
            }
            if !sum.re.is_finite() || !sum.im.is_finite() {
                return Err("dft_numeric".to_owned());
            }
            output[frequency] = sum;
        }
    }
    Ok(output)
}

fn forward_dft(samples: &[f64]) -> Result<Vec<Complex>, String> {
    if samples.len() != SAMPLE_COUNT || samples.iter().any(|value| !value.is_finite()) {
        return Err("dft_input".to_owned());
    }
    factorized_dft(
        &samples
            .iter()
            .copied()
            .map(|re| Complex { re, im: 0.0 })
            .collect::<Vec<_>>(),
        FACTORS,
    )
}

fn one_sided_digest(role: &[u8], spectrum: &[Complex]) -> Result<String, String> {
    if spectrum.len() != SAMPLE_COUNT {
        return Err("dft_length".to_owned());
    }
    let mut hash = Sha256::new();
    hash.update(b"sipi.p3c.selected-causality-transfer-delta-spectrum.v1\0");
    hash.update(role);
    hash.update((ONE_SIDED_BINS as u64).to_be_bytes());
    hash.update(DF_BITS.to_be_bytes());
    for value in &spectrum[..ONE_SIDED_BINS] {
        if !value.re.is_finite() || !value.im.is_finite() {
            return Err("dft_numeric".to_owned());
        }
        hash.update(value.re.to_bits().to_be_bytes());
        hash.update(value.im.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn weighted_energy(spectrum: &[Complex], start: usize, end: usize) -> Result<f64, String> {
    if spectrum.len() != SAMPLE_COUNT || start >= end || end > ONE_SIDED_BINS {
        return Err("band".to_owned());
    }
    let mut sum = 0.0;
    for index in start..end {
        let weight = if index == 0 || index == SAMPLE_COUNT / 2 {
            1.0
        } else {
            2.0
        };
        sum += weight * spectrum[index].norm_sqr()?;
        if !sum.is_finite() {
            return Err("numeric".to_owned());
        }
    }
    let result = sum / (SAMPLE_COUNT as f64).powi(2);
    result
        .is_finite()
        .then_some(result)
        .ok_or_else(|| "numeric".to_owned())
}

fn band_fact(
    raw: &[Complex],
    bounded: &[Complex],
    delta: &[Complex],
    range: (usize, usize),
) -> Result<BandFact, String> {
    Ok(BandFact {
        raw_energy_bits: format!("{:016x}", weighted_energy(raw, range.0, range.1)?.to_bits()),
        bounded_energy_bits: format!(
            "{:016x}",
            weighted_energy(bounded, range.0, range.1)?.to_bits()
        ),
        delta_energy_bits: format!(
            "{:016x}",
            weighted_energy(delta, range.0, range.1)?.to_bits()
        ),
    })
}

fn bin_fact(index: usize, raw: Complex, bounded: Complex, delta: Complex) -> BinFact {
    BinFact {
        index,
        raw_re_bits: format!("{:016x}", raw.re.to_bits()),
        raw_im_bits: format!("{:016x}", raw.im.to_bits()),
        bounded_re_bits: format!("{:016x}", bounded.re.to_bits()),
        bounded_im_bits: format!("{:016x}", bounded.im.to_bits()),
        delta_re_bits: format!("{:016x}", delta.re.to_bits()),
        delta_im_bits: format!("{:016x}", delta.im.to_bits()),
    }
}

fn run_once(source: &Path, index: usize) -> Result<RunFact, String> {
    let before = source_identity(source)?;
    let root = fresh_root(index)?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root).map_err(|_| "artifact_root".to_owned())?;
        let artifact_id = format!("selected-s4p-causality-transfer-delta-{index}");
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
        if admitted.source_byte_length() != before.0 || admitted.source_sha256() != before.1 {
            return Err("admission_provenance".to_owned());
        }
        let uniform = interpolate_selected_p3c_hdiff_v1(admitted.transfer())
            .map_err(|_| "interpolation".to_owned())?;
        if uniform.sample_count() != ONE_SIDED_BINS
            || uniform.frequency_step().get().to_bits() != DF_BITS
        {
            return Err("uniform_grid".to_owned());
        }
        let raw = inverse_selected_p3c_uniform_spectrum_v1(&uniform)
            .map_err(|_| "raw_transform".to_owned())?;
        let bounded =
            enforce_selected_p3c_causality_v1(&uniform).map_err(|_| "causality".to_owned())?;
        if raw.sample_count() != SAMPLE_COUNT
            || bounded.sample_count() != SAMPLE_COUNT
            || raw.sample_interval().get().to_bits() != DT_BITS
            || bounded.sample_interval().get().to_bits() != DT_BITS
        {
            return Err("response_grid".to_owned());
        }
        let raw_values = raw
            .samples()
            .iter()
            .map(|value| value.get())
            .collect::<Vec<_>>();
        let bounded_values = bounded
            .samples()
            .iter()
            .map(|value| value.get())
            .collect::<Vec<_>>();
        let raw_spectrum = forward_dft(&raw_values)?;
        let bounded_spectrum = forward_dft(&bounded_values)?;
        let delta_spectrum = raw_spectrum
            .iter()
            .copied()
            .zip(bounded_spectrum.iter().copied())
            .map(|(raw, bounded)| bounded.sub(raw))
            .collect::<Vec<_>>();
        let stop = match bounded.stop() {
            SelectedP3cCausalityStopV1::RelativeError => "relative_error",
            SelectedP3cCausalityStopV1::SuccessiveErrorDifference => "successive_error_difference",
        };
        Ok(RunFact {
            source_manifest_sha256: manifest,
            record_count: admitted.record_count(),
            uniform_bin_count: uniform.sample_count(),
            raw_sample_count: raw.sample_count(),
            bounded_sample_count: bounded.sample_count(),
            sample_interval_bits: format!("{DT_BITS:016x}"),
            frequency_step_bits: format!("{DF_BITS:016x}"),
            iteration_count: bounded.iteration_count(),
            final_error_bits: format!("{:016x}", bounded.final_error().get().to_bits()),
            stop,
            raw_response_sha256: response_digest(b"raw", &raw_values)?,
            bounded_response_sha256: response_digest(b"bounded", &bounded_values)?,
            raw_spectrum_sha256: one_sided_digest(b"raw", &raw_spectrum)?,
            bounded_spectrum_sha256: one_sided_digest(b"bounded", &bounded_spectrum)?,
            delta_spectrum_sha256: one_sided_digest(b"bounded-minus-raw", &delta_spectrum)?,
            residual_peak_frequency_bracket: [
                bin_fact(
                    203,
                    raw_spectrum[203],
                    bounded_spectrum[203],
                    delta_spectrum[203],
                ),
                bin_fact(
                    204,
                    raw_spectrum[204],
                    bounded_spectrum[204],
                    delta_spectrum[204],
                ),
            ],
            bands: [
                band_fact(&raw_spectrum, &bounded_spectrum, &delta_spectrum, BANDS[0])?,
                band_fact(&raw_spectrum, &bounded_spectrum, &delta_spectrum, BANDS[1])?,
                band_fact(&raw_spectrum, &bounded_spectrum, &delta_spectrum, BANDS[2])?,
                band_fact(&raw_spectrum, &bounded_spectrum, &delta_spectrum, BANDS[3])?,
            ],
        })
    })();
    let cleanup = fs::remove_dir_all(&root).map_err(|_| "cleanup".to_owned());
    match (result, cleanup) {
        (Ok(value), Ok(())) => Ok(value),
        (Err(error), Ok(())) | (_, Err(error)) => Err(error),
    }
}

fn bin_json(fact: &BinFact) -> String {
    format!("{{\"index\":{},\"raw_re_bits\":\"{}\",\"raw_im_bits\":\"{}\",\"bounded_re_bits\":\"{}\",\"bounded_im_bits\":\"{}\",\"delta_re_bits\":\"{}\",\"delta_im_bits\":\"{}\"}}", fact.index, fact.raw_re_bits, fact.raw_im_bits, fact.bounded_re_bits, fact.bounded_im_bits, fact.delta_re_bits, fact.delta_im_bits)
}
fn band_json(fact: &BandFact) -> String {
    format!("{{\"raw_energy_bits\":\"{}\",\"bounded_energy_bits\":\"{}\",\"delta_energy_bits\":\"{}\"}}", fact.raw_energy_bits, fact.bounded_energy_bits, fact.delta_energy_bits)
}
fn run_json(fact: &RunFact) -> String {
    format!("{{\"source_manifest_sha256\":\"{}\",\"record_count\":{},\"uniform_bin_count\":{},\"raw_sample_count\":{},\"bounded_sample_count\":{},\"sample_interval_bits\":\"{}\",\"frequency_step_bits\":\"{}\",\"iteration_count\":{},\"final_error_bits\":\"{}\",\"stop\":\"{}\",\"raw_response_sha256\":\"{}\",\"bounded_response_sha256\":\"{}\",\"raw_spectrum_sha256\":\"{}\",\"bounded_spectrum_sha256\":\"{}\",\"delta_spectrum_sha256\":\"{}\",\"residual_peak_frequency_bracket\":[{},{}],\"bands\":[{},{},{},{}]}}", fact.source_manifest_sha256, fact.record_count, fact.uniform_bin_count, fact.raw_sample_count, fact.bounded_sample_count, fact.sample_interval_bits, fact.frequency_step_bits, fact.iteration_count, fact.final_error_bits, fact.stop, fact.raw_response_sha256, fact.bounded_response_sha256, fact.raw_spectrum_sha256, fact.bounded_spectrum_sha256, fact.delta_spectrum_sha256, bin_json(&fact.residual_peak_frequency_bracket[0]), bin_json(&fact.residual_peak_frequency_bracket[1]), band_json(&fact.bands[0]), band_json(&fact.bands[1]), band_json(&fact.bands[2]), band_json(&fact.bands[3]))
}

fn same_observation(left: &RunFact, right: &RunFact) -> bool {
    left.record_count == right.record_count
        && left.uniform_bin_count == right.uniform_bin_count
        && left.raw_sample_count == right.raw_sample_count
        && left.bounded_sample_count == right.bounded_sample_count
        && left.sample_interval_bits == right.sample_interval_bits
        && left.frequency_step_bits == right.frequency_step_bits
        && left.iteration_count == right.iteration_count
        && left.final_error_bits == right.final_error_bits
        && left.stop == right.stop
        && left.raw_response_sha256 == right.raw_response_sha256
        && left.bounded_response_sha256 == right.bounded_response_sha256
        && left.raw_spectrum_sha256 == right.raw_spectrum_sha256
        && left.bounded_spectrum_sha256 == right.bounded_spectrum_sha256
        && left.delta_spectrum_sha256 == right.delta_spectrum_sha256
        && left.residual_peak_frequency_bracket == right.residual_peak_frequency_bracket
        && left.bands == right.bands
}

#[test]
fn factorized_dft_matches_direct_small_input() {
    let input = [1.0, -2.0, 0.5, 3.0, -1.0, 4.0];
    let complex = input
        .iter()
        .copied()
        .map(|re| Complex { re, im: 0.0 })
        .collect::<Vec<_>>();
    let actual = factorized_dft(&complex, &[2, 3]).unwrap();
    for (frequency, value) in actual.iter().enumerate() {
        let expected = input
            .iter()
            .enumerate()
            .fold(Complex::ZERO, |sum, (index, sample)| {
                let angle =
                    -std::f64::consts::TAU * (frequency * index) as f64 / input.len() as f64;
                let (sin, cos) = angle.sin_cos();
                sum.add(Complex {
                    re: *sample * cos,
                    im: *sample * sin,
                })
            });
        assert!((value.re - expected.re).abs() <= 1.0e-12);
        assert!((value.im - expected.im).abs() <= 1.0e-12);
    }
}

#[test]
fn fixed_band_edges_are_disjoint_and_cover_the_one_sided_grid() {
    assert_eq!(BANDS[0].0, 0);
    assert!(BANDS.windows(2).all(|pair| pair[0].1 == pair[1].0));
    assert_eq!(BANDS[3].1, ONE_SIDED_BINS);
}

#[test]
#[ignore = "external-only selected S4P causality transfer-delta observation"]
fn p3c_sealed_s4p_external_causality_transfer_delta_runner_v1() {
    let source = required_path(SOURCE_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    let first = run_once(&source, 1).unwrap();
    let second = run_once(&source, 2).unwrap();
    assert_ne!(first.source_manifest_sha256, second.source_manifest_sha256);
    assert!(
        same_observation(&first, &second),
        "fresh observations differ"
    );
    let payload = format!("{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"observed\",\"source_byte_length\":{SELECTED_P3C_S4P_BYTE_LENGTH_V1},\"source_sha256\":\"{SELECTED_P3C_S4P_SHA256_V1}\",\"source_identity_checks\":\"before_stage_after_equal\",\"fixed_dft\":{{\"samples\":{SAMPLE_COUNT},\"one_sided_bins\":{ONE_SIDED_BINS},\"sample_interval_bits\":\"{DT_BITS:016x}\",\"frequency_step_bits\":\"{DF_BITS:016x}\",\"window\":\"rectangular\",\"forward_sign\":\"negative\",\"normalization\":\"none\",\"factorization\":[32,32,2,25],\"bands\":[[0,1],[1,801],[801,2001],[2001,{ONE_SIDED_BINS}]]}},\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n", run_json(&first), run_json(&second));
    serde_json::from_str::<Value>(&payload).unwrap();
    assert!(!report.exists());
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, payload).unwrap();
}
