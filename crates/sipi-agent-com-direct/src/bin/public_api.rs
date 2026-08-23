use sipi_agent_com_direct::{
    DirectRunErrorV1, DirectRunRequestV1, load_config_run_com_write_artifacts_v1,
};
use std::path::PathBuf;

fn main() {
    match parse_args() {
        Ok(request) => match load_config_run_com_write_artifacts_v1(&request) {
            Ok(report) => println!(
                "{}",
                serde_json::json!({
                    "schema": report.schema,
                    "workflow": report.workflow,
                    "result_json": report.artifacts.result_json,
                    "report_html": report.artifacts.report_html,
                    "diagnostics_json": report.artifacts.diagnostics_json,
                    "legacy_csv": report.artifacts.legacy_csv,
                    "impulse_sample_count": report.impulse_sample_count,
                    "impulse_sha256": report.impulse_sha256,
                    "config_sha256": report.config_sha256,
                })
            ),
            Err(error) => {
                eprintln!("{error}");
                std::process::exit(exit_code(&error));
            }
        },
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(exit_code(&error));
        }
    }
}

fn parse_args() -> Result<DirectRunRequestV1, DirectRunErrorV1> {
    let mut args = std::env::args().skip(1);
    let mut config = None;
    let mut pulse = None;
    let mut fext = Vec::new();
    let mut next = Vec::new();
    let mut output_dir = None;
    let mut artifact_id = "com-run".to_owned();
    let mut overwrite = false;
    let mut calibration_noise = None;
    let mut legacy_csv = false;
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--config" => config = Some(PathBuf::from(next_value(&mut args, "--config")?)),
            "--thru" | "--pulse" | "--s4p" | "--td-csv" => {
                pulse = Some(PathBuf::from(next_value(&mut args, "--pulse")?))
            }
            "--fext" => fext.push(PathBuf::from(next_value(&mut args, "--fext")?)),
            "--next" => next.push(PathBuf::from(next_value(&mut args, "--next")?)),
            "--output-dir" => {
                output_dir = Some(PathBuf::from(next_value(&mut args, "--output-dir")?))
            }
            "--artifact-id" => artifact_id = next_value(&mut args, "--artifact-id")?,
            "--overwrite" => overwrite = true,
            "--calibration-noise" => {
                calibration_noise =
                    Some(PathBuf::from(next_value(&mut args, "--calibration-noise")?));
            }
            "--legacy-csv" => legacy_csv = true,
            other => {
                return Err(DirectRunErrorV1::InvalidRequest(format!(
                    "unknown argument {other}"
                )));
            }
        }
    }
    let config = config
        .ok_or_else(|| DirectRunErrorV1::InvalidRequest("--config is required".to_owned()))?;
    let pulse =
        pulse.ok_or_else(|| DirectRunErrorV1::InvalidRequest("--thru is required".to_owned()))?;
    let output_dir = output_dir
        .ok_or_else(|| DirectRunErrorV1::InvalidRequest("--output-dir is required".to_owned()))?;
    Ok(DirectRunRequestV1 {
        config,
        pulse,
        fext,
        next,
        output_dir,
        artifact_id,
        profile: "r480".to_owned(),
        reader: Some("r480".to_owned()),
        fix_ids: Vec::new(),
        overrides: Vec::new(),
        overwrite,
        calibration_noise,
        legacy_csv,
    })
}

fn next_value<I: Iterator<Item = String>>(
    args: &mut I,
    name: &str,
) -> Result<String, DirectRunErrorV1> {
    args.next()
        .ok_or_else(|| DirectRunErrorV1::InvalidRequest(format!("{name} requires a value")))
}

fn exit_code(error: &DirectRunErrorV1) -> i32 {
    match error {
        DirectRunErrorV1::Unsupported(_) => 5,
        DirectRunErrorV1::InvalidRequest(_) => 2,
        DirectRunErrorV1::Config(error) => error.exit_code(),
        DirectRunErrorV1::Json(_) | DirectRunErrorV1::Parameters(_) => 3,
        DirectRunErrorV1::Input { .. }
        | DirectRunErrorV1::InputLimit { .. }
        | DirectRunErrorV1::NonFiniteImpulse { .. }
        | DirectRunErrorV1::Touchstone(_)
        | DirectRunErrorV1::Channel(_)
        | DirectRunErrorV1::Execution(_)
        | DirectRunErrorV1::Artifact(_) => 1,
    }
}
