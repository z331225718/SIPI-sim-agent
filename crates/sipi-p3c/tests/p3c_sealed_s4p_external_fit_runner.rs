#![forbid(unsafe_code)]

//! External-only observation of the fixed selected S4P admission followed by
//! the already-frozen real-constrained fit. This is not a waveform route.

use std::{
    env,
    fs::{self, File},
    io::{self, Read},
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_channel::{
    fit_selected_p3c_real_constrained_fixed_pole_v1, RealConstrainedFixedPoleFitErrorV1,
};
use sipi_p3c::{
    admit_selected_p3c_sealed_s4p_v2, SelectedP3cSealedS4pIdentityV2,
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_SHA256_V1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REPORT_ENV: &str = "SIPI_P3C_SEALED_S4P_FIT_RUNNER_REPORT";
const RUNNER_SCHEMA: &str = "sipi.p3c.sealed-selected-s4p-real-constrained-fit-runner.v1";

#[derive(Debug)]
struct RunFact {
    manifest_sha256: String,
    record_count: usize,
    outcome: FitOutcome,
}

#[derive(Debug, Eq, PartialEq)]
enum FitOutcome {
    Admitted {
        order: usize,
        model_sha256: String,
        metrics_sha256: String,
    },
    NoOrderMeetsAdmission,
}

fn sha256_reader(mut reader: impl Read) -> io::Result<(u64, String)> {
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
            .ok_or_else(|| io::Error::other("source_length_overflow"))?;
        digest.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", digest.finalize())))
}

fn source_identity(source: &Path) -> Result<(u64, String), String> {
    let file = File::open(source).map_err(|error| format!("source_open:{error}"))?;
    let identity = sha256_reader(file).map_err(|error| format!("source_hash:{error}"))?;
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
    let root = env::temp_dir().join(format!("sipi-p3c-sealed-s4p-fit-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|error| format!("root_create:{error}"))?;
    Ok(root)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn model_and_metrics_sha256(
    fit: &sipi_channel::SelectedP3cRealConstrainedFixedPoleFitV1,
) -> Result<(String, String), String> {
    let poles = fit.positive_imaginary_poles_per_second();
    let residues = fit.positive_imaginary_residues_per_second();
    if ![8, 12, 16].contains(&fit.order())
        || poles.len() != fit.order() / 2
        || residues.len() != poles.len()
    {
        return Err("fit_shape_invalid".to_owned());
    }
    let mut model = Sha256::new();
    model.update(b"sipi.p3c.real-constrained-fixed-pole-model.v1\0");
    model.update((fit.order() as u64).to_be_bytes());
    for (pole, residue) in poles.iter().zip(residues) {
        if !pole.real().is_finite()
            || !pole.imaginary().is_finite()
            || pole.real() >= 0.0
            || pole.imaginary() <= 0.0
            || !residue.real().is_finite()
            || !residue.imaginary().is_finite()
        {
            return Err("fit_model_not_canonical_real_pair".to_owned());
        }
        for value in [
            pole.real(),
            pole.imaginary(),
            residue.real(),
            residue.imaginary(),
        ] {
            model.update(value.to_bits().to_be_bytes());
        }
    }
    let metrics = fit.metrics();
    let mut metric_digest = Sha256::new();
    metric_digest.update(b"sipi.p3c.real-constrained-fixed-pole-metrics.v1\0");
    for value in [
        metrics.relative_rms_error(),
        metrics.maximum_normalized_absolute_error(),
        metrics.dc_relative_error(),
    ] {
        if !value.is_finite() {
            return Err("fit_metrics_nonfinite".to_owned());
        }
        metric_digest.update(value.to_bits().to_be_bytes());
    }
    Ok((
        format!("{:x}", model.finalize()),
        format!("{:x}", metric_digest.finalize()),
    ))
}

fn observe_once(source: &Path, index: usize) -> Result<RunFact, String> {
    let before = source_identity(source)?;
    let root = fresh_root(index)?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root)
            .map_err(|error| format!("artifact_root:{error:?}"))?;
        let artifact_id = format!("selected-s4p-fit-{index}");
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
        let outcome = match fit_selected_p3c_real_constrained_fixed_pole_v1(admitted.transfer()) {
            Ok(fit) => {
                let (model_sha256, metrics_sha256) = model_and_metrics_sha256(&fit)?;
                FitOutcome::Admitted {
                    order: fit.order(),
                    model_sha256,
                    metrics_sha256,
                }
            }
            Err(RealConstrainedFixedPoleFitErrorV1::NoOrderMeetsAdmission) => {
                FitOutcome::NoOrderMeetsAdmission
            }
            Err(error) => return Err(format!("fit:{error}")),
        };
        Ok(RunFact {
            manifest_sha256,
            record_count: admitted.record_count(),
            outcome,
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

fn run_json(fact: &RunFact) -> String {
    match &fact.outcome {
        FitOutcome::Admitted { order, model_sha256, metrics_sha256 } => format!(
            "{{\"manifest_sha256\":\"{}\",\"record_count\":{},\"fit_status\":\"admitted\",\"order\":{},\"model_sha256\":\"{}\",\"metrics_sha256\":\"{}\"}}",
            fact.manifest_sha256, fact.record_count, order, model_sha256, metrics_sha256,
        ),
        FitOutcome::NoOrderMeetsAdmission => format!(
            "{{\"manifest_sha256\":\"{}\",\"record_count\":{},\"fit_status\":\"no_order_meets_admission\"}}",
            fact.manifest_sha256, fact.record_count,
        ),
    }
}

fn write_report(
    report: &Path,
    status: &str,
    reason: Option<&str>,
    first: &RunFact,
    second: &RunFact,
) -> Result<(), String> {
    fs::create_dir_all(
        report
            .parent()
            .ok_or_else(|| "report_parent_missing".to_owned())?,
    )
    .map_err(|error| format!("report_parent_create:{error}"))?;
    let reason = reason
        .map(|value| format!("\"{value}\""))
        .unwrap_or_else(|| "null".to_owned());
    let payload = format!(
        "{{\"schema\":\"{}\",\"status\":\"{}\",\"reason\":{},\"source_byte_length\":{},\"source_sha256\":\"{}\",\"source_identity_checks\":\"before_stage_after_equal\",\"fresh_runs\":[{},{}],\"cleanup_status\":\"complete\"}}\n",
        RUNNER_SCHEMA, status, reason, SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1, run_json(first), run_json(second),
    );
    fs::write(report, payload).map_err(|error| format!("report_write:{error}"))
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
    match &first.outcome {
        FitOutcome::Admitted { .. } => write_report(&report, "observed", None, &first, &second),
        FitOutcome::NoOrderMeetsAdmission => write_report(
            &report,
            "rejected",
            Some("no_order_meets_admission"),
            &first,
            &second,
        ),
    }
}

#[test]
#[ignore = "external-only selected S4P fit observation; requires explicit source and report paths"]
fn p3c_sealed_s4p_external_fit_runner_v1() {
    run().unwrap_or_else(|error| panic!("p3c_sealed_s4p_external_fit_runner_v1_failed:{error}"));
}
