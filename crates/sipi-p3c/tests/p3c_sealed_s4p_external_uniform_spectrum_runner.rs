#![forbid(unsafe_code)]

//! External-only observation of the selected sealed S4P through the fixed
//! IEEE BSD interpolation leaf. It does not create an impulse or waveform.

use std::{
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_ieee_com_sparam::{interpolate_selected_p3c_hdiff_v1, InterpSparamErrorV1};
use sipi_p3c::{
    admit_selected_p3c_sealed_s4p_v2, SelectedP3cSealedS4pIdentityV2,
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REPORT_ENV: &str = "SIPI_P3C_SEALED_S4P_UNIFORM_SPECTRUM_RUNNER_REPORT";
const SCHEMA: &str = "sipi.p3c.sealed-selected-s4p-uniform-spectrum-runner.v1";

#[derive(Debug, Eq, PartialEq)]
enum Outcome {
    Admitted {
        bin_count: usize,
        frequency_step_bits: String,
        dc_real_bits: String,
        dc_imaginary_bits: String,
        nyquist_real_bits: String,
        nyquist_imaginary_bits: String,
        spectrum_sha256: String,
    },
    Rejected {
        error: &'static str,
    },
}

#[derive(Debug, Eq, PartialEq)]
struct RunFact {
    manifest_sha256: String,
    record_count: usize,
    outcome: Outcome,
}

fn sha256_reader(mut reader: impl Read) -> Result<(u64, String), String> {
    let mut digest = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader
            .read(&mut buffer)
            .map_err(|error| format!("source_hash:{error}"))?;
        if read == 0 {
            break;
        }
        length = length
            .checked_add(read as u64)
            .ok_or_else(|| "source_length_overflow".to_owned())?;
        digest.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", digest.finalize())))
}

fn source_identity(source: &Path) -> Result<(u64, String), String> {
    let identity =
        sha256_reader(File::open(source).map_err(|error| format!("source_open:{error}"))?)?;
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
    let root = env::temp_dir().join(format!("sipi-p3c-uniform-spectrum-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|error| format!("root_create:{error}"))?;
    Ok(root)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn error_name(error: InterpSparamErrorV1) -> &'static str {
    match error {
        InterpSparamErrorV1::TooFewInputSamples => "too_few_input_samples",
        InterpSparamErrorV1::LengthMismatch => "length_mismatch",
        InterpSparamErrorV1::NonIncreasingFrequency => "non_increasing_frequency",
        InterpSparamErrorV1::NonPositiveFrequencyStep => "non_positive_frequency_step",
        InterpSparamErrorV1::OutputGridExceedsLimit => "output_grid_exceeds_limit",
        InterpSparamErrorV1::AntiCausalPhaseSlope => "anti_causal_phase_slope",
        InterpSparamErrorV1::EmptyPhaseTrendInliers => "empty_phase_trend_inliers",
        InterpSparamErrorV1::UndefinedHighFrequencyLogTrend => "undefined_high_frequency_log_trend",
        InterpSparamErrorV1::NonFiniteCalculation => "nonfinite_calculation",
    }
}

fn outcome(admitted: &sipi_p3c::AdmittedSelectedP3cStaticTransferV2) -> Outcome {
    match interpolate_selected_p3c_hdiff_v1(admitted.transfer()) {
        Ok(spectrum) => {
            let values = spectrum.values();
            let Some((dc, nyquist)) = values.first().zip(values.last()) else {
                return Outcome::Rejected {
                    error: "empty_uniform_spectrum",
                };
            };
            let mut digest = Sha256::new();
            digest.update(b"sipi.p3c.selected-uniform-spectrum.v1\0");
            digest.update((values.len() as u64).to_be_bytes());
            digest.update(spectrum.frequency_step().get().to_bits().to_be_bytes());
            for value in values {
                digest.update(value.real().to_bits().to_be_bytes());
                digest.update(value.imaginary().to_bits().to_be_bytes());
            }
            Outcome::Admitted {
                bin_count: values.len(),
                frequency_step_bits: format!("{:016x}", spectrum.frequency_step().get().to_bits()),
                dc_real_bits: format!("{:016x}", dc.real().to_bits()),
                dc_imaginary_bits: format!("{:016x}", dc.imaginary().to_bits()),
                nyquist_real_bits: format!("{:016x}", nyquist.real().to_bits()),
                nyquist_imaginary_bits: format!("{:016x}", nyquist.imaginary().to_bits()),
                spectrum_sha256: format!("{:x}", digest.finalize()),
            }
        }
        Err(error) => Outcome::Rejected {
            error: error_name(error),
        },
    }
}

fn observe_once(source: &Path, index: usize) -> Result<RunFact, String> {
    let before = source_identity(source)?;
    let root = fresh_root(index)?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root)
            .map_err(|error| format!("artifact_root:{error:?}"))?;
        let artifact_id = format!("selected-s4p-uniform-spectrum-{index}");
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
        Ok(RunFact {
            manifest_sha256,
            record_count: admitted.record_count(),
            outcome: outcome(&admitted),
        })
    })();
    let cleanup = fs::remove_dir_all(&root).map_err(|error| format!("root_cleanup:{error}"));
    match (result, cleanup) {
        (Ok(fact), Ok(())) => Ok(fact),
        (Err(error), Ok(())) | (_, Err(error)) => Err(error),
    }
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(env::var_os(name).ok_or_else(|| format!("{name}_missing"))?);
    path.is_absolute()
        .then_some(path)
        .ok_or_else(|| format!("{name}_not_absolute"))
}

fn run_json(fact: &RunFact) -> String {
    match &fact.outcome {
        Outcome::Admitted { bin_count, frequency_step_bits, dc_real_bits, dc_imaginary_bits, nyquist_real_bits, nyquist_imaginary_bits, spectrum_sha256 } => format!("{{\"manifest_sha256\":\"{}\",\"record_count\":{},\"interpolation_status\":\"admitted\",\"bin_count\":{},\"frequency_step_bits\":\"{}\",\"dc_real_bits\":\"{}\",\"dc_imaginary_bits\":\"{}\",\"nyquist_real_bits\":\"{}\",\"nyquist_imaginary_bits\":\"{}\",\"spectrum_sha256\":\"{}\"}}", fact.manifest_sha256, fact.record_count, bin_count, frequency_step_bits, dc_real_bits, dc_imaginary_bits, nyquist_real_bits, nyquist_imaginary_bits, spectrum_sha256),
        Outcome::Rejected { error } => format!("{{\"manifest_sha256\":\"{}\",\"record_count\":{},\"interpolation_status\":\"rejected\",\"error\":\"{}\"}}", fact.manifest_sha256, fact.record_count, error),
    }
}

fn run() -> Result<(), String> {
    let source = required_path(SOURCE_ENV)?;
    let report = required_path(REPORT_ENV)?;
    let first = observe_once(&source, 1)?;
    let second = observe_once(&source, 2)?;
    if first.record_count != second.record_count
        || first.manifest_sha256 == second.manifest_sha256
        || first.outcome != second.outcome
    {
        return Err("fresh_runs_not_independent_or_repeatable".to_owned());
    }
    fs::create_dir_all(
        report
            .parent()
            .ok_or_else(|| "report_parent_missing".to_owned())?,
    )
    .map_err(|error| format!("report_parent_create:{error}"))?;
    let status = match first.outcome {
        Outcome::Admitted { .. } => "observed",
        Outcome::Rejected { .. } => "rejected",
    };
    let payload = format!("{{\"schema\":\"{}\",\"status\":\"{}\",\"source_byte_length\":{},\"source_sha256\":\"{}\",\"source_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n", SCHEMA, status, SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1, run_json(&first), run_json(&second));
    fs::write(report, payload).map_err(|error| format!("report_write:{error}"))
}

#[test]
#[ignore = "external-only selected S4P uniform-spectrum observation; requires explicit source and report paths"]
fn p3c_sealed_s4p_external_uniform_spectrum_runner_v1() {
    run().unwrap_or_else(|error| {
        panic!("p3c_sealed_s4p_external_uniform_spectrum_runner_v1_failed:{error}")
    });
}
