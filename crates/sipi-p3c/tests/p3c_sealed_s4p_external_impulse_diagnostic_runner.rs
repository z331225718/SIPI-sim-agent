#![forbid(unsafe_code)]

//! External-only causality diagnostic for the exact admitted P3C Hdiff.
//!
//! This evaluates a disclosed quadrature for owner review. It neither admits
//! causality nor creates a product impulse, convolution, or waveform.

use std::{
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_p3c::{
    admit_selected_p3c_sealed_s4p_v2, SelectedP3cSealedS4pIdentityV2,
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REPORT_ENV: &str = "SIPI_P3C_SEALED_S4P_IMPULSE_DIAGNOSTIC_RUNNER_REPORT";
const SCHEMA: &str = "sipi.p3c.sealed-selected-s4p-impulse-causality-diagnostic-runner.v1";
const DT_SECONDS: f64 = 9.765_625e-13;
const HALF_WINDOW_SAMPLES: usize = 49_056;

#[derive(Debug, Eq, PartialEq)]
struct RunFact {
    manifest_sha256: String,
    record_count: usize,
    impulse_sha256: String,
    negative_energy_fraction_bits: u64,
    negative_peak_fraction_bits: u64,
    signed_peak_index: isize,
}

fn sha256_reader(mut reader: impl Read) -> std::io::Result<(u64, String)> {
    let mut digest = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        length = length
            .checked_add(read as u64)
            .ok_or_else(|| std::io::Error::other("source_length_overflow"))?;
        digest.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", digest.finalize())))
}

fn source_identity(source: &Path) -> Result<(u64, String), String> {
    let identity =
        sha256_reader(File::open(source).map_err(|error| format!("source_open:{error}"))?)
            .map_err(|error| format!("source_hash:{error}"))?;
    if identity
        != (
            SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        )
    {
        return Err("source_identity_mismatch".to_owned());
    }
    Ok(identity)
}

fn fresh_root(index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock_before_epoch".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-impulse-diagnostic-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|error| format!("root_create:{error}"))?;
    Ok(root)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn diagnostic(points: &[(f64, f64, f64)]) -> Result<(String, u64, u64, isize), String> {
    if points.len() < 2
        || points[0].0.to_bits() != 0.0_f64.to_bits()
        || points
            .last()
            .is_none_or(|value| value.0.to_bits() != 40_000_000_000.0_f64.to_bits())
    {
        return Err("transfer_axis_not_exact_0_to_40ghz".to_owned());
    }
    let mut weights = Vec::with_capacity(points.len());
    for index in 0..points.len() {
        let weight = match index {
            0 => (points[1].0 - points[0].0) / 2.0,
            value if value + 1 == points.len() => (points[value].0 - points[value - 1].0) / 2.0,
            value => (points[value + 1].0 - points[value - 1].0) / 2.0,
        };
        if !weight.is_finite() || weight <= 0.0 {
            return Err("quadrature_weight_invalid".to_owned());
        }
        weights.push(weight);
    }
    let mut samples = Vec::with_capacity(2 * HALF_WINDOW_SAMPLES + 1);
    for index in -(HALF_WINDOW_SAMPLES as isize)..=(HALF_WINDOW_SAMPLES as isize) {
        let time = index as f64 * DT_SECONDS;
        let mut sum = 0.0_f64;
        for ((frequency, real, imaginary), weight) in points.iter().zip(&weights) {
            let angle = std::f64::consts::TAU * frequency * time;
            sum += 2.0 * weight * (real * angle.cos() - imaginary * angle.sin());
        }
        if !sum.is_finite() {
            return Err("nonfinite_impulse_diagnostic".to_owned());
        }
        samples.push(sum);
    }
    let peak = samples
        .iter()
        .copied()
        .map(f64::abs)
        .fold(0.0_f64, f64::max);
    if !peak.is_finite() || peak == 0.0 {
        return Err("zero_impulse_diagnostic".to_owned());
    }
    let peak_position = samples
        .iter()
        .position(|sample| sample.abs().to_bits() == peak.to_bits())
        .ok_or_else(|| "peak_position_missing".to_owned())?;
    let signed_peak_index = peak_position as isize - HALF_WINDOW_SAMPLES as isize;
    let (negative_energy, nonnegative_energy, negative_peak) =
        samples.iter().enumerate().try_fold(
            (0.0_f64, 0.0_f64, 0.0_f64),
            |(negative, nonnegative, negative_peak), (position, sample)| {
                let normalized = *sample / peak;
                let square = normalized * normalized;
                if !square.is_finite() {
                    return Err("impulse_energy_overflow".to_owned());
                }
                Ok::<_, String>(if position < HALF_WINDOW_SAMPLES {
                    (
                        negative + square,
                        nonnegative,
                        negative_peak.max(normalized.abs()),
                    )
                } else {
                    (negative, nonnegative + square, negative_peak)
                })
            },
        )?;
    let total = negative_energy + nonnegative_energy;
    if !total.is_finite() || total == 0.0 {
        return Err("zero_impulse_energy".to_owned());
    }
    let negative_energy_fraction = negative_energy / total;
    let mut digest = Sha256::new();
    digest.update(b"sipi.p3c.exact-grid-impulse-causality-diagnostic.v1\0");
    digest.update((HALF_WINDOW_SAMPLES as u64).to_be_bytes());
    for sample in samples {
        digest.update(sample.to_bits().to_be_bytes());
    }
    Ok((
        format!("{:x}", digest.finalize()),
        negative_energy_fraction.to_bits(),
        negative_peak.to_bits(),
        signed_peak_index,
    ))
}

fn observe_once(source: &Path, index: usize) -> Result<RunFact, String> {
    let before = source_identity(source)?;
    let root = fresh_root(index)?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root)
            .map_err(|error| format!("artifact_root:{error:?}"))?;
        let artifact_id = format!("selected-s4p-impulse-diagnostic-{index}");
        let mut stage = store
            .begin(&artifact_id)
            .map_err(|error| format!("artifact_begin:{error:?}"))?;
        stage
            .stage_reader(
                SELECTED_P3C_S4P_FILE_NAME_V1,
                File::open(source).map_err(|error| format!("source_reopen:{error}"))?,
                SELECTED_P3C_S4P_BYTE_LENGTH_V1,
            )
            .map_err(|error| format!("artifact_stage:{error:?}"))?;
        stage
            .seal()
            .map_err(|error| format!("artifact_seal:{error:?}"))?
            .publish_new()
            .map_err(|error| format!("artifact_publish:{error:?}"))?;
        if source_identity(source)? != before {
            return Err("source_changed_during_materialization".to_owned());
        }
        let manifest_sha256 = sha256_bytes(
            &fs::read(root.join(&artifact_id).join("success.json"))
                .map_err(|error| format!("manifest_read:{error}"))?,
        );
        let reader = ArtifactRoot::open_existing(&root)
            .map_err(|error| format!("artifact_reopen:{error:?}"))?;
        let identity = SelectedP3cSealedS4pIdentityV2::try_new(&artifact_id, &manifest_sha256)
            .map_err(|error| format!("identity:{error}"))?;
        let admitted = admit_selected_p3c_sealed_s4p_v2(&reader, &identity)
            .map_err(|error| format!("admission:{error}"))?;
        if admitted.source_byte_length() != before.0
            || admitted.source_sha256() != before.1
            || admitted.artifact_id() != artifact_id
            || admitted.manifest_sha256() != manifest_sha256
            || admitted.record_count() == 0
        {
            return Err("admission_provenance_mismatch".to_owned());
        }
        let points = admitted
            .transfer()
            .frequencies()
            .iter()
            .zip(admitted.transfer().transfer())
            .map(|(frequency, value)| (frequency.get(), value.real(), value.imaginary()))
            .collect::<Vec<_>>();
        let (
            impulse_sha256,
            negative_energy_fraction_bits,
            negative_peak_fraction_bits,
            signed_peak_index,
        ) = diagnostic(&points)?;
        Ok(RunFact {
            manifest_sha256,
            record_count: admitted.record_count(),
            impulse_sha256,
            negative_energy_fraction_bits,
            negative_peak_fraction_bits,
            signed_peak_index,
        })
    })();
    let cleanup = fs::remove_dir_all(&root).map_err(|error| format!("root_cleanup:{error}"));
    match (result, cleanup) {
        (Ok(fact), Ok(())) => Ok(fact),
        (Err(error), Ok(())) => Err(error),
        (_, Err(error)) => Err(error),
    }
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute()
        .then_some(path)
        .ok_or_else(|| format!("{name}_not_absolute"))
}

fn write_report(report: &Path, first: &RunFact, second: &RunFact) -> Result<(), String> {
    fs::create_dir_all(
        report
            .parent()
            .ok_or_else(|| "report_parent_missing".to_owned())?,
    )
    .map_err(|error| format!("report_parent_create:{error}"))?;
    let row = |fact: &RunFact| {
        format!("{{\"manifest_sha256\":\"{}\",\"record_count\":{},\"impulse_sha256\":\"{}\",\"negative_energy_fraction_bits\":\"{:016x}\",\"negative_peak_fraction_bits\":\"{:016x}\",\"signed_peak_index\":{}}}", fact.manifest_sha256, fact.record_count, fact.impulse_sha256, fact.negative_energy_fraction_bits, fact.negative_peak_fraction_bits, fact.signed_peak_index)
    };
    let payload = format!("{{\"schema\":\"{}\",\"status\":\"observed\",\"source_byte_length\":{},\"source_sha256\":\"{}\",\"source_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n", SCHEMA, SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1, row(first), row(second));
    fs::write(report, payload).map_err(|error| format!("report_write:{error}"))
}

fn run() -> Result<(), String> {
    let source = required_path(SOURCE_ENV)?;
    let report = required_path(REPORT_ENV)?;
    let first = observe_once(&source, 1)?;
    let second = observe_once(&source, 2)?;
    if first.record_count != second.record_count
        || first.impulse_sha256 != second.impulse_sha256
        || first.negative_energy_fraction_bits != second.negative_energy_fraction_bits
        || first.negative_peak_fraction_bits != second.negative_peak_fraction_bits
        || first.signed_peak_index != second.signed_peak_index
        || first.manifest_sha256 == second.manifest_sha256
    {
        return Err("fresh_runs_not_independent_or_repeatable".to_owned());
    }
    write_report(&report, &first, &second)
}

#[test]
#[ignore = "external-only impulse causality diagnostic; requires explicit source and report paths"]
fn p3c_sealed_s4p_external_impulse_diagnostic_runner_v1() {
    run().unwrap_or_else(|error| {
        panic!("p3c_sealed_s4p_external_impulse_diagnostic_runner_v1_failed:{error}")
    });
}
