#![forbid(unsafe_code)]

//! External-only observation of the selected sealed S4P through the fixed IEEE
//! interpolation, bounded causality, and truncation leaves. It creates no candidate waveform.

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
    CausalityEnforcementErrorV1, InterpSparamErrorV1, SelectedP3cTruncationTailV1,
    TruncationErrorV1, enforce_selected_p3c_causality_v1, interpolate_selected_p3c_hdiff_v1,
    truncate_selected_p3c_response_v1,
};
use sipi_p3c::{
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
    SelectedP3cSealedS4pIdentityV2, admit_selected_p3c_sealed_s4p_v2,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REPORT_ENV: &str = "SIPI_P3C_SEALED_S4P_TRUNCATION_RUNNER_REPORT";
const SCHEMA: &str = "sipi.p3c.sealed-selected-s4p-truncation-runner.v1";

#[derive(Debug, Eq, PartialEq)]
enum Outcome {
    Admitted {
        uniform_bin_count: usize,
        causal_sample_count: usize,
        iteration_count: usize,
        retained_sample_count: usize,
        sample_interval_bits: String,
        dropped_l2_over_total_l2_bits: String,
        tail: &'static str,
        truncated_response_sha256: String,
    },
    Rejected {
        stage: &'static str,
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
    let root = env::temp_dir().join(format!("sipi-p3c-truncation-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|error| format!("root_create:{error}"))?;
    Ok(root)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn interpolation_error_name(error: InterpSparamErrorV1) -> &'static str {
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

fn causality_error_name(error: CausalityEnforcementErrorV1) -> &'static str {
    match error {
        CausalityEnforcementErrorV1::RawPeriodicInput(_) => "raw_periodic_input",
        CausalityEnforcementErrorV1::InputAllZero => "input_all_zero",
        CausalityEnforcementErrorV1::NoFirstHalfThresholdCrossing => {
            "no_first_half_threshold_crossing"
        }
        CausalityEnforcementErrorV1::IterationBecameAllZero => "iteration_became_all_zero",
        CausalityEnforcementErrorV1::NonPositiveErrorDenominator => "nonpositive_error_denominator",
        CausalityEnforcementErrorV1::InverseImaginaryResidue => "inverse_imaginary_residue",
        CausalityEnforcementErrorV1::NonFiniteCalculation => "nonfinite_calculation",
        CausalityEnforcementErrorV1::IterationLimitExceeded => "iteration_limit_exceeded",
    }
}

fn truncation_error_name(error: TruncationErrorV1) -> &'static str {
    match error {
        TruncationErrorV1::EmptyInput => "empty_input",
        TruncationErrorV1::InputSampleLimitExceeded => "input_sample_limit_exceeded",
        TruncationErrorV1::NonFiniteCalculation => "nonfinite_calculation",
        TruncationErrorV1::AllZeroInput => "all_zero_input",
        TruncationErrorV1::NoThresholdCrossing => "no_threshold_crossing",
    }
}

fn outcome(admitted: &sipi_p3c::AdmittedSelectedP3cStaticTransferV2) -> Outcome {
    let uniform = match interpolate_selected_p3c_hdiff_v1(admitted.transfer()) {
        Ok(value) => value,
        Err(error) => {
            return Outcome::Rejected {
                stage: "interpolation",
                error: interpolation_error_name(error),
            };
        }
    };
    let causal = match enforce_selected_p3c_causality_v1(&uniform) {
        Ok(value) => value,
        Err(error) => {
            return Outcome::Rejected {
                stage: "causality_enforcement",
                error: causality_error_name(error),
            };
        }
    };
    let truncated = match truncate_selected_p3c_response_v1(&causal) {
        Ok(value) => value,
        Err(error) => {
            return Outcome::Rejected {
                stage: "truncation",
                error: truncation_error_name(error),
            };
        }
    };
    let mut digest = Sha256::new();
    digest.update(b"sipi.p3c.selected-truncated-response.v1\0");
    digest.update((truncated.sample_count() as u64).to_be_bytes());
    digest.update(truncated.sample_interval().get().to_bits().to_be_bytes());
    for sample in truncated.samples() {
        digest.update(sample.get().to_bits().to_be_bytes());
    }
    let tail = match truncated.tail() {
        SelectedP3cTruncationTailV1::ZeroTail => "zero_tail",
        SelectedP3cTruncationTailV1::NonZeroTail => "nonzero_tail",
    };
    Outcome::Admitted {
        uniform_bin_count: uniform.sample_count(),
        causal_sample_count: causal.sample_count(),
        iteration_count: causal.iteration_count(),
        retained_sample_count: truncated.sample_count(),
        sample_interval_bits: format!("{:016x}", causal.sample_interval().get().to_bits()),
        dropped_l2_over_total_l2_bits: format!(
            "{:016x}",
            truncated.dropped_l2_over_total_l2().get().to_bits()
        ),
        tail,
        truncated_response_sha256: format!("{:x}", digest.finalize()),
    }
}

fn observe_once(source: &Path, index: usize) -> Result<RunFact, String> {
    let before = source_identity(source)?;
    let root = fresh_root(index)?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root)
            .map_err(|error| format!("artifact_root:{error:?}"))?;
        let artifact_id = format!("selected-s4p-truncation-{index}");
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
        Outcome::Admitted {
            uniform_bin_count,
            causal_sample_count,
            iteration_count,
            retained_sample_count,
            sample_interval_bits,
            dropped_l2_over_total_l2_bits,
            tail,
            truncated_response_sha256,
        } => format!(
            "{{\"manifest_sha256\":\"{}\",\"record_count\":{},\"truncation_status\":\"admitted\",\"uniform_bin_count\":{},\"causal_sample_count\":{},\"iteration_count\":{},\"retained_sample_count\":{},\"sample_interval_bits\":\"{}\",\"dropped_l2_over_total_l2_bits\":\"{}\",\"tail\":\"{}\",\"truncated_response_sha256\":\"{}\"}}",
            fact.manifest_sha256,
            fact.record_count,
            uniform_bin_count,
            causal_sample_count,
            iteration_count,
            retained_sample_count,
            sample_interval_bits,
            dropped_l2_over_total_l2_bits,
            tail,
            truncated_response_sha256
        ),
        Outcome::Rejected { stage, error } => format!(
            "{{\"manifest_sha256\":\"{}\",\"record_count\":{},\"truncation_status\":\"rejected\",\"stage\":\"{}\",\"error\":\"{}\"}}",
            fact.manifest_sha256, fact.record_count, stage, error
        ),
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
    let payload = format!(
        "{{\"schema\":\"{}\",\"status\":\"{}\",\"source_byte_length\":{},\"source_sha256\":\"{}\",\"source_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n",
        SCHEMA,
        status,
        SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        SELECTED_P3C_S4P_SHA256_V1,
        run_json(&first),
        run_json(&second)
    );
    fs::write(report, payload).map_err(|error| format!("report_write:{error}"))
}

#[test]
#[ignore = "external-only selected S4P truncation observation; requires explicit source and report paths"]
fn p3c_sealed_s4p_external_truncation_runner_v1() {
    run().unwrap_or_else(|error| {
        panic!("p3c_sealed_s4p_external_truncation_runner_v1_failed:{error}")
    });
}
