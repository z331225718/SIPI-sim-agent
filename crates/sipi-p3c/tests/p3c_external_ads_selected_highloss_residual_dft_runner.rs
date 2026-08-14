#![forbid(unsafe_code)]

//! External-only current-v2 residual DFT diagnostic. It retains no waveform,
//! residual vector, or spectrum bins in the emitted report.

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
    compare_selected_highloss_prbs9_waveform_only_v3, SelectedHighlossPrbs9WaveformPairV3,
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
    admit_selected_p3c_sealed_s4p_v2, generate_selected_p3c_prbs9_impulse_candidate_v2,
    SelectedP3cSealedS4pIdentityV2, SELECTED_P3C_S4P_BYTE_LENGTH_V1,
    SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REFERENCE_ENV: &str = "SIPI_P3C_ADS_REFERENCE_CANONICAL_PAYLOAD";
const REPORT_ENV: &str = "SIPI_P3C_SELECTED_HIGHLOSS_RESIDUAL_DFT_REPORT";
const REPORT_SCHEMA: &str = "sipi.p3c.external-ads-selected-highloss-residual-dft-v2-runner.v1";
const ADS_CANONICAL_SHA256: &str = "5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726";
const ADS_TUPLE_BYTES: usize = 24;
const DT_BITS: u64 = 0x3d71_2e0b_e826_d695;
const THIRD_START: usize = 32_704;
const THIRD_SAMPLES: usize = 16_352;
const ONE_SIDED_BINS: usize = THIRD_SAMPLES / 2 + 1;
const ABS_INTEGRITY_LIMIT: f64 = 1.0e-24;
const REL_INTEGRITY_LIMIT: f64 = 1.0e-10;

#[derive(Clone, Copy, Debug)]
struct Complex {
    re: f64,
    im: f64,
}

impl Complex {
    const ZERO: Self = Self { re: 0.0, im: 0.0 };

    fn add(self, other: Self) -> Self {
        Self { re: self.re + other.re, im: self.im + other.im }
    }

    fn mul(self, other: Self) -> Self {
        Self {
            re: self.re * other.re - self.im * other.im,
            im: self.re * other.im + self.im * other.re,
        }
    }

    fn norm_sqr(self) -> Option<f64> {
        let value = self.re.mul_add(self.re, self.im * self.im);
        value.is_finite().then_some(value)
    }
}

#[derive(Debug, Eq, PartialEq)]
struct BandFact {
    reference_energy_bits: String,
    candidate_energy_bits: String,
    residual_energy_bits: String,
    residual_to_reference_sqrt_bits: String,
}

#[derive(Debug, Eq, PartialEq)]
struct RunFact {
    source_manifest_sha256: String,
    record_count: usize,
    reference_rx_payload_sha256: String,
    candidate_prefix_sha256: String,
    time_nrmse_bits: String,
    frequency_nrmse_bits: String,
    reference_spectrum_sha256: String,
    candidate_spectrum_sha256: String,
    residual_spectrum_sha256: String,
    maximum_residual_energy_bin: usize,
    bands: [BandFact; 4],
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute().then_some(path).ok_or_else(|| format!("{name}_not_absolute"))
}

fn sha256(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }

fn sha256_reader(mut reader: impl Read) -> Result<(u64, String), String> {
    let mut hasher = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader.read(&mut buffer).map_err(|_| "identity_read".to_owned())?;
        if read == 0 { break; }
        length = length.checked_add(read as u64).ok_or_else(|| "identity_length_overflow".to_owned())?;
        hasher.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", hasher.finalize())))
}

fn selected_source_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = sha256_reader(File::open(path).map_err(|_| "source_open".to_owned())?)?;
    (identity == (SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1.to_owned()))
        .then_some(identity).ok_or_else(|| "source_identity".to_owned())
}

fn reference_identity(path: &Path) -> Result<(u64, String), String> {
    let identity = sha256_reader(File::open(path).map_err(|_| "reference_open".to_owned())?)?;
    (identity == ((SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3 * ADS_TUPLE_BYTES) as u64, ADS_CANONICAL_SHA256.to_owned()))
        .then_some(identity).ok_or_else(|| "reference_identity".to_owned())
}

fn fresh_root(index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| "clock".to_owned())?.as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-residual-dft-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|_| "root_create".to_owned())?;
    Ok(root)
}

fn manifest_sha256(root: &Path, artifact_id: &str) -> Result<String, String> {
    fs::read(root.join(artifact_id).join("success.json")).map(|bytes| sha256(&bytes)).map_err(|_| "manifest_read".to_owned())
}

fn reference_values(path: &Path) -> Result<(Vec<f64>, String), String> {
    let bytes = fs::read(path).map_err(|_| "reference_read".to_owned())?;
    if bytes.len() != SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3 * ADS_TUPLE_BYTES || sha256(&bytes) != ADS_CANONICAL_SHA256 {
        return Err("reference_identity".to_owned());
    }
    let mut values = Vec::with_capacity(SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3);
    for (index, tuple) in bytes.chunks_exact(ADS_TUPLE_BYTES).enumerate() {
        let time = f64::from_le_bytes(tuple[..8].try_into().map_err(|_| "reference_layout")?);
        let tx = f64::from_le_bytes(tuple[8..16].try_into().map_err(|_| "reference_layout")?);
        let rx = f64::from_le_bytes(tuple[16..].try_into().map_err(|_| "reference_layout")?);
        let expected = index as f64 * f64::from_bits(DT_BITS);
        if !time.is_finite() || !tx.is_finite() || !rx.is_finite() || (time - expected).abs() > 8.0 * f64::EPSILON.max(expected.abs() * f64::EPSILON) {
            return Err("reference_grid".to_owned());
        }
        values.push(rx);
    }
    let payload = values.iter().flat_map(|value| value.to_le_bytes()).collect::<Vec<_>>();
    Ok((values, sha256(&payload)))
}

fn candidate_values_v2(source: &Path, root: &Path, index: usize) -> Result<(usize, String, Vec<f64>), String> {
    let before = selected_source_identity(source)?;
    let artifact_id = format!("selected-s4p-residual-dft-v2-{index}");
    let store = ArtifactRoot::open_or_create(root).map_err(|_| "source_root".to_owned())?;
    let mut stage = store.begin(&artifact_id).map_err(|_| "source_begin".to_owned())?;
    stage.stage_reader(SELECTED_P3C_S4P_FILE_NAME_V1, File::open(source).map_err(|_| "source_reopen".to_owned())?, SELECTED_P3C_S4P_BYTE_LENGTH_V1).map_err(|_| "source_stage".to_owned())?;
    stage.seal().map_err(|_| "source_seal".to_owned())?.publish_new().map_err(|_| "source_publish".to_owned())?;
    if selected_source_identity(source)? != before { return Err("source_drift".to_owned()); }
    let manifest = manifest_sha256(root, &artifact_id)?;
    let reader = ArtifactRoot::open_existing(root).map_err(|_| "source_reopen_root".to_owned())?;
    let identity = SelectedP3cSealedS4pIdentityV2::try_new(&artifact_id, &manifest).map_err(|_| "source_request_identity".to_owned())?;
    let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &identity).map_err(|_| "source_admission".to_owned())?;
    if admitted.source_byte_length() != before.0 || admitted.source_sha256() != before.1 { return Err("source_admission_provenance".to_owned()); }
    let uniform = interpolate_selected_p3c_hdiff_v1(admitted.transfer()).map_err(|_| "candidate_interpolation".to_owned())?;
    let causal = enforce_selected_p3c_causality_v1(&uniform).map_err(|_| "candidate_causality".to_owned())?;
    let truncated = truncate_selected_p3c_response_v1(&causal).map_err(|_| "candidate_truncation".to_owned())?;
    let candidate = generate_selected_p3c_prbs9_impulse_candidate_v2(&truncated).map_err(|_| "candidate_convolution".to_owned())?;
    let values = candidate.waveform_prefix().iter().map(|sample| sample.get()).collect::<Vec<_>>();
    (values.len() == SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_SAMPLE_COUNT_V3 && values.iter().all(|value| value.is_finite())).then_some((admitted.record_count(), manifest, values)).ok_or_else(|| "candidate_values".to_owned())
}

fn candidate_prefix_digest(values: &[f64]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"sipi.p3c.selected-highloss-prbs9-waveform-prefix.v3\0");
    hasher.update((values.len() as u64).to_be_bytes());
    hasher.update(DT_BITS.to_be_bytes());
    for value in values { hasher.update(value.to_bits().to_be_bytes()); }
    format!("{:x}", hasher.finalize())
}

fn forward_dft(values: &[f64]) -> Result<Vec<Complex>, String> {
    if values.len() != THIRD_SAMPLES || values.iter().any(|value| !value.is_finite()) {
        return Err("dft_input".to_owned());
    }
    let values = values.iter().copied().map(|re| Complex { re, im: 0.0 }).collect::<Vec<_>>();
    factorized_dft(&values, &[32, 7, 73])
}

fn factorized_dft(values: &[Complex], factors: &[usize]) -> Result<Vec<Complex>, String> {
    if factors.is_empty() { return (values.len() == 1).then_some(values.to_vec()).ok_or_else(|| "dft_factorization".to_owned()); }
    let radix = factors[0];
    let length = values.len();
    if radix < 2 || length % radix != 0 { return Err("dft_factorization".to_owned()); }
    let inner = length / radix;
    let mut subtransforms = Vec::with_capacity(radix);
    for branch in 0..radix {
        let input = (0..inner).map(|offset| values[branch + radix * offset]).collect::<Vec<_>>();
        subtransforms.push(factorized_dft(&input, &factors[1..])?);
    }
    let mut output = vec![Complex::ZERO; length];
    for frequency_inner in 0..inner {
        for frequency_outer in 0..radix {
            let frequency = frequency_inner + inner * frequency_outer;
            let mut sum = Complex::ZERO;
            for branch in 0..radix {
                let angle = -2.0 * std::f64::consts::PI * (frequency * branch) as f64 / length as f64;
                let (sin, cos) = angle.sin_cos();
                sum = sum.add(subtransforms[branch][frequency_inner].mul(Complex { re: cos, im: sin }));
            }
            if !sum.re.is_finite() || !sum.im.is_finite() { return Err("dft_numeric".to_owned()); }
            output[frequency] = sum;
        }
    }
    Ok(output)
}

fn one_sided_digest(role: &[u8], spectrum: &[Complex]) -> Result<String, String> {
    if spectrum.len() != THIRD_SAMPLES { return Err("dft_length".to_owned()); }
    let mut hash = Sha256::new();
    hash.update(b"sipi.p3c.selected-highloss-residual-dft-one-sided.v1\0");
    hash.update(role);
    hash.update((ONE_SIDED_BINS as u64).to_be_bytes());
    hash.update(DT_BITS.to_be_bytes());
    for value in &spectrum[..ONE_SIDED_BINS] {
        if !value.re.is_finite() || !value.im.is_finite() { return Err("dft_numeric".to_owned()); }
        hash.update(value.re.to_bits().to_be_bytes());
        hash.update(value.im.to_bits().to_be_bytes());
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn weighted_energy(spectrum: &[Complex], start: usize, end: usize) -> Result<f64, String> {
    if spectrum.len() != THIRD_SAMPLES || start >= end || end > ONE_SIDED_BINS { return Err("dft_band".to_owned()); }
    let mut sum = 0.0;
    for index in start..end {
        let weight = if index == 0 || index == THIRD_SAMPLES / 2 { 1.0 } else { 2.0 };
        let energy = spectrum[index].norm_sqr().ok_or_else(|| "dft_numeric".to_owned())?;
        sum += weight * energy;
        if !sum.is_finite() { return Err("dft_numeric".to_owned()); }
    }
    let mean_square = sum / (THIRD_SAMPLES as f64 * THIRD_SAMPLES as f64);
    mean_square.is_finite().then_some(mean_square).ok_or_else(|| "dft_numeric".to_owned())
}

fn band_fact(reference: &[Complex], candidate: &[Complex], residual: &[Complex], start: usize, end: usize) -> Result<BandFact, String> {
    let reference_energy = weighted_energy(reference, start, end)?;
    let candidate_energy = weighted_energy(candidate, start, end)?;
    let residual_energy = weighted_energy(residual, start, end)?;
    if reference_energy == 0.0 { return Err("zero_band_reference".to_owned()); }
    let ratio = (residual_energy / reference_energy).sqrt();
    if !ratio.is_finite() { return Err("dft_numeric".to_owned()); }
    Ok(BandFact {
        reference_energy_bits: format!("{:016x}", reference_energy.to_bits()),
        candidate_energy_bits: format!("{:016x}", candidate_energy.to_bits()),
        residual_energy_bits: format!("{:016x}", residual_energy.to_bits()),
        residual_to_reference_sqrt_bits: format!("{:016x}", ratio.to_bits()),
    })
}

fn run_once(source: &Path, reference_path: &Path, index: usize) -> Result<RunFact, String> {
    let root = fresh_root(index)?;
    let result = (|| {
        let (record_count, source_manifest_sha256, candidate) = candidate_values_v2(source, &root, index)?;
        let reference_before = reference_identity(reference_path)?;
        let (reference, reference_rx_payload_sha256) = reference_values(reference_path)?;
        if reference_identity(reference_path)? != reference_before { return Err("reference_drift".to_owned()); }
        let candidate_prefix_sha256 = candidate_prefix_digest(&candidate);
        let pair = SelectedHighlossPrbs9WaveformPairV3::try_new(reference.clone(), candidate.clone()).map_err(|_| "diagnostic_pair".to_owned())?;
        let time = compare_selected_highloss_prbs9_waveform_only_v3(&pair).map_err(|_| "diagnostic_v3".to_owned())?.waveform_nrmse();
        let reference = &reference[THIRD_START..THIRD_START + THIRD_SAMPLES];
        let candidate = &candidate[THIRD_START..THIRD_START + THIRD_SAMPLES];
        let residual = candidate.iter().zip(reference).map(|(candidate, reference)| candidate - reference).collect::<Vec<_>>();
        let reference_spectrum = forward_dft(reference)?;
        let candidate_spectrum = forward_dft(candidate)?;
        let residual_spectrum = forward_dft(&residual)?;
        let bands = [
            band_fact(&reference_spectrum, &candidate_spectrum, &residual_spectrum, 0, 1)?,
            band_fact(&reference_spectrum, &candidate_spectrum, &residual_spectrum, 1, 256)?,
            band_fact(&reference_spectrum, &candidate_spectrum, &residual_spectrum, 256, 639)?,
            band_fact(&reference_spectrum, &candidate_spectrum, &residual_spectrum, 639, ONE_SIDED_BINS)?,
        ];
        let total = band_fact(&reference_spectrum, &candidate_spectrum, &residual_spectrum, 0, ONE_SIDED_BINS)?;
        let frequency_nrmse = f64::from_bits(u64::from_str_radix(&total.residual_to_reference_sqrt_bits, 16).map_err(|_| "dft_bits".to_owned())?);
        let absolute = (frequency_nrmse - time).abs();
        let relative = absolute / time.abs();
        if !(absolute <= ABS_INTEGRITY_LIMIT || relative <= REL_INTEGRITY_LIMIT) { return Err("parseval_integrity".to_owned()); }
        let mut maximum_energy = f64::NEG_INFINITY;
        let mut maximum_residual_energy_bin = 0;
        for (index, value) in residual_spectrum[..ONE_SIDED_BINS].iter().copied().enumerate() {
            let energy = value.norm_sqr().ok_or_else(|| "dft_numeric".to_owned())?;
            if energy > maximum_energy { maximum_energy = energy; maximum_residual_energy_bin = index; }
        }
        if !maximum_energy.is_finite() { return Err("dft_numeric".to_owned()); }
        Ok(RunFact {
            source_manifest_sha256,
            record_count,
            reference_rx_payload_sha256,
            candidate_prefix_sha256,
            time_nrmse_bits: format!("{:016x}", time.to_bits()),
            frequency_nrmse_bits: format!("{:016x}", frequency_nrmse.to_bits()),
            reference_spectrum_sha256: one_sided_digest(b"reference", &reference_spectrum)?,
            candidate_spectrum_sha256: one_sided_digest(b"candidate", &candidate_spectrum)?,
            residual_spectrum_sha256: one_sided_digest(b"residual", &residual_spectrum)?,
            maximum_residual_energy_bin,
            bands,
        })
    })();
    if fs::remove_dir_all(root).is_err() { return Err("cleanup".to_owned()); }
    result
}

fn band_json(band: &BandFact) -> String {
    format!("{{\"reference_energy_bits\":\"{}\",\"candidate_energy_bits\":\"{}\",\"residual_energy_bits\":\"{}\",\"residual_to_reference_sqrt_bits\":\"{}\"}}", band.reference_energy_bits, band.candidate_energy_bits, band.residual_energy_bits, band.residual_to_reference_sqrt_bits)
}

fn run_json(fact: &RunFact) -> String {
    format!("{{\"source_manifest_sha256\":\"{}\",\"record_count\":{},\"reference_rx_payload_sha256\":\"{}\",\"candidate_prefix_sha256\":\"{}\",\"time_nrmse_bits\":\"{}\",\"frequency_nrmse_bits\":\"{}\",\"reference_spectrum_sha256\":\"{}\",\"candidate_spectrum_sha256\":\"{}\",\"residual_spectrum_sha256\":\"{}\",\"maximum_residual_energy_bin\":{},\"bands\":[{},{},{},{}]}}", fact.source_manifest_sha256, fact.record_count, fact.reference_rx_payload_sha256, fact.candidate_prefix_sha256, fact.time_nrmse_bits, fact.frequency_nrmse_bits, fact.reference_spectrum_sha256, fact.candidate_spectrum_sha256, fact.residual_spectrum_sha256, fact.maximum_residual_energy_bin, band_json(&fact.bands[0]), band_json(&fact.bands[1]), band_json(&fact.bands[2]), band_json(&fact.bands[3]))
}

#[test]
fn factorized_dft_matches_direct_small_input() {
    let input = [1.0, -2.0, 0.5, 3.0, -1.0, 4.0];
    let complex = input.iter().copied().map(|re| Complex { re, im: 0.0 }).collect::<Vec<_>>();
    let actual = factorized_dft(&complex, &[2, 3]).unwrap();
    for (frequency, value) in actual.iter().enumerate() {
        let expected = input.iter().enumerate().fold(Complex::ZERO, |sum, (index, sample)| {
            let angle = -2.0 * std::f64::consts::PI * (frequency * index) as f64 / input.len() as f64;
            let (sin, cos) = angle.sin_cos();
            sum.add(Complex { re: *sample * cos, im: *sample * sin })
        });
        assert!((value.re - expected.re).abs() <= 1.0e-12);
        assert!((value.im - expected.im).abs() <= 1.0e-12);
    }
}

#[test]
fn one_sided_band_edges_and_parseval_weights_are_fixed() {
    let mut spectrum = vec![Complex::ZERO; THIRD_SAMPLES];
    spectrum[0] = Complex { re: 3.0, im: 0.0 };
    spectrum[THIRD_SAMPLES / 2] = Complex { re: 4.0, im: 0.0 };
    spectrum[255] = Complex { re: 5.0, im: 0.0 };
    spectrum[256] = Complex { re: 6.0, im: 0.0 };
    spectrum[638] = Complex { re: 7.0, im: 0.0 };
    spectrum[639] = Complex { re: 8.0, im: 0.0 };
    assert_eq!(weighted_energy(&spectrum, 0, 1).unwrap().to_bits(), (9.0 / (THIRD_SAMPLES as f64).powi(2)).to_bits());
    assert!(weighted_energy(&spectrum, 1, 256).unwrap() > 0.0);
    assert!(weighted_energy(&spectrum, 256, 639).unwrap() > 0.0);
    assert!(weighted_energy(&spectrum, 639, ONE_SIDED_BINS).unwrap() > 0.0);
}

#[test]
#[ignore = "external-only current-v2 residual DFT diagnostic; requires source/reference/report paths"]
fn p3c_external_ads_selected_highloss_residual_dft_runner_v2() {
    let source = required_path(SOURCE_ENV).unwrap();
    let reference = required_path(REFERENCE_ENV).unwrap();
    let report = required_path(REPORT_ENV).unwrap();
    assert!(!report.exists() && !report.starts_with(env::current_dir().unwrap()), "report_path_not_fresh_external");
    let first = run_once(&source, &reference, 1).unwrap();
    let second = run_once(&source, &reference, 2).unwrap();
    assert_ne!(first.source_manifest_sha256, second.source_manifest_sha256);
    assert_eq!(first.record_count, second.record_count);
    assert_eq!(first.reference_rx_payload_sha256, second.reference_rx_payload_sha256);
    assert_eq!(first.candidate_prefix_sha256, second.candidate_prefix_sha256);
    assert_eq!(first.time_nrmse_bits, second.time_nrmse_bits);
    assert_eq!(first.frequency_nrmse_bits, second.frequency_nrmse_bits);
    assert_eq!(first.reference_spectrum_sha256, second.reference_spectrum_sha256);
    assert_eq!(first.candidate_spectrum_sha256, second.candidate_spectrum_sha256);
    assert_eq!(first.residual_spectrum_sha256, second.residual_spectrum_sha256);
    assert_eq!(first.maximum_residual_energy_bin, second.maximum_residual_energy_bin);
    assert_eq!(first.bands, second.bands);
    let payload = format!("{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"observed\",\"source_byte_length\":{},\"source_sha256\":\"{}\",\"ads_canonical_triple_payload_sha256\":\"{ADS_CANONICAL_SHA256}\",\"contract_sha256\":\"{SELECTED_HIGHLOSS_PRBS9_WAVEFORM_ONLY_CONTRACT_SHA256_V3}\",\"fixed_dft\":{{\"samples\":{THIRD_SAMPLES},\"sample_interval_bits\":\"{DT_BITS:016x}\",\"window\":\"rectangular\",\"forward_sign\":\"negative\",\"normalization\":\"none\",\"factorization\":[32,7,73],\"bands\":[[0,1],[1,256],[256,639],[639,{ONE_SIDED_BINS}]]}},\"source_reference_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n", SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1, run_json(&first), run_json(&second));
    serde_json::from_str::<Value>(&payload).expect("report_json");
    fs::create_dir_all(report.parent().unwrap()).unwrap();
    fs::write(report, payload).unwrap();
}
