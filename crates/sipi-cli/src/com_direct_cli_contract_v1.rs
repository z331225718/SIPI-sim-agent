//! Bounded argv contract for the feature-gated R4.80 `sipi com run` route.

use crate::com_direct_integration::run_com_direct_for_integration_v1;
use sha2::{Digest, Sha256};
use sipi_agent_com_direct::{
    ConfigValidateErrorV1, ConfigValidateRequestV1, DEFAULT_ATOL_V1, DirectCompareErrorV1,
    DirectRunErrorV1, DirectRunRequestV1, compare_result_paths_v1, config_validate_v1,
    error_exit_code_v1,
};
use std::{fs, path::PathBuf};

pub(crate) const COM_R480_ARGV_SCHEMA_V1: &str = "sipi.com.r480.argv.v1";
pub(crate) const COM_R480_CLI_RECEIPT_SCHEMA_V1: &str = "sipi.com.r480-cli-receipt.v1";
pub(crate) const MAX_COM_R480_PATH_BYTES_V1: usize = 4_096;
pub(crate) const MAX_COM_R480_CROSSTALK_CHANNELS_V1: usize = 64;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ComR480ArgvRequestV1 {
    pub config: PathBuf,
    pub thru: PathBuf,
    pub fext: Vec<PathBuf>,
    pub next: Vec<PathBuf>,
    pub calibration_noise: Option<PathBuf>,
    pub output_dir: PathBuf,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ComR480ArgvErrorV1 {
    MissingRequired,
    MissingValue,
    DuplicateSingleton,
    UnknownOption,
    UnsafePath,
    TooManyCrosstalkChannels,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ComR480ExecutionErrorV1 {
    Argument(ComR480ArgvErrorV1),
    InvalidInput,
    OperationalFailure,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct ComConfigExecutionErrorV1 {
    exit_code: i32,
    diagnostic_code: &'static str,
}

impl ComConfigExecutionErrorV1 {
    const fn argument() -> Self {
        Self {
            exit_code: 2,
            diagnostic_code: "usage",
        }
    }

    const fn from_config(error: &ConfigValidateErrorV1) -> Self {
        match error {
            ConfigValidateErrorV1::Io(_) => Self {
                exit_code: error.exit_code(),
                diagnostic_code: "operational_failure",
            },
            ConfigValidateErrorV1::Unsupported(_) => Self {
                exit_code: error.exit_code(),
                diagnostic_code: "unsupported",
            },
            _ => Self {
                exit_code: error.exit_code(),
                diagnostic_code: "invalid_input",
            },
        }
    }

    pub(crate) const fn exit_code(self) -> i32 {
        self.exit_code
    }
    pub(crate) const fn diagnostic_code(self) -> &'static str {
        self.diagnostic_code
    }
}

impl ComR480ExecutionErrorV1 {
    pub(crate) const fn exit_code(self) -> i32 {
        match self {
            Self::Argument(_) | Self::InvalidInput => 2,
            Self::OperationalFailure => 1,
        }
    }

    pub(crate) const fn diagnostic_code(self) -> &'static str {
        match self {
            Self::Argument(error) => error.diagnostic_code(),
            Self::InvalidInput => "invalid_input",
            Self::OperationalFailure => "operational_failure",
        }
    }
}

impl ComR480ArgvErrorV1 {
    pub(crate) const fn diagnostic_code(self) -> &'static str {
        match self {
            Self::MissingRequired
            | Self::MissingValue
            | Self::DuplicateSingleton
            | Self::UnknownOption => "usage",
            Self::UnsafePath | Self::TooManyCrosstalkChannels => "invalid_input",
        }
    }
}

/// Parse only the arguments after `sipi com run`.
///
/// Profile, reader, fix IDs, overrides, overwrite, legacy output, stdin, and
/// URLs are intentionally absent from this contract.  Filesystem custody is
/// performed later by the direct-port execution boundary, immediately before
/// it reads or creates anything.
pub(crate) fn parse_com_r480_argv_v1(
    arguments: &[String],
) -> Result<ComR480ArgvRequestV1, ComR480ArgvErrorV1> {
    let mut config = None;
    let mut thru = None;
    let mut output_dir = None;
    let mut calibration_noise = None;
    let mut fext = Vec::new();
    let mut next = Vec::new();
    let mut index = 0usize;

    while index < arguments.len() {
        let option = arguments[index].as_str();
        let value = arguments
            .get(index + 1)
            .ok_or(ComR480ArgvErrorV1::MissingValue)?;
        if !option.starts_with("--") || value.starts_with("--") {
            return Err(ComR480ArgvErrorV1::MissingValue);
        }
        let path = parse_local_path_v1(value)?;
        match option {
            "--config" => set_singleton_v1(&mut config, path)?,
            "--thru" => set_singleton_v1(&mut thru, path)?,
            "--output-dir" => set_singleton_v1(&mut output_dir, path)?,
            "--calibration-noise" => set_singleton_v1(&mut calibration_noise, path)?,
            "--fext" => fext.push(path),
            "--next" => next.push(path),
            _ => return Err(ComR480ArgvErrorV1::UnknownOption),
        }
        if fext.len().saturating_add(next.len()) > MAX_COM_R480_CROSSTALK_CHANNELS_V1 {
            return Err(ComR480ArgvErrorV1::TooManyCrosstalkChannels);
        }
        index += 2;
    }

    Ok(ComR480ArgvRequestV1 {
        config: config.ok_or(ComR480ArgvErrorV1::MissingRequired)?,
        thru: thru.ok_or(ComR480ArgvErrorV1::MissingRequired)?,
        fext,
        next,
        calibration_noise,
        output_dir: output_dir.ok_or(ComR480ArgvErrorV1::MissingRequired)?,
    })
}

/// Execute the fixed argv surface and emit only a path-free typed receipt.
pub(crate) fn execute_com_r480_argv_v1(
    arguments: &[String],
) -> Result<String, ComR480ExecutionErrorV1> {
    let parsed = parse_com_r480_argv_v1(arguments).map_err(ComR480ExecutionErrorV1::Argument)?;
    if parsed.output_dir.exists() {
        return Err(ComR480ExecutionErrorV1::InvalidInput);
    }
    let mut request = DirectRunRequestV1::new(&parsed.config, &parsed.thru, &parsed.output_dir);
    request.artifact_id = "com-r480".to_owned();
    request.profile = "r480".to_owned();
    // The pinned r4.80 profile owns its reader choice; an explicit reader is
    // only admitted by the direct port's custom-profile branch.
    request.reader = None;
    request.fext = parsed.fext;
    request.next = parsed.next;
    request.calibration_noise = parsed.calibration_noise;
    let report = run_com_direct_for_integration_v1(&request).map_err(map_direct_error_v1)?;
    receipt_json_v1(&report)
}

/// Execute the existing Agent-COM config validator through the root CLI.
/// The root consumes `com config`; this function consumes the original
/// validator tail beginning with `validate` so no config semantics are added.
pub(crate) fn execute_com_config_validate_argv_v1(
    arguments: &[String],
) -> Result<String, ComConfigExecutionErrorV1> {
    let mut iterator = arguments.iter();
    if iterator.next().map(String::as_str) != Some("validate") {
        return Err(ComConfigExecutionErrorV1::argument());
    }
    let config = iterator
        .next()
        .ok_or_else(ComConfigExecutionErrorV1::argument)?;
    let mut request = ConfigValidateRequestV1 {
        config: PathBuf::from(config),
        profile: "r480".to_owned(),
        reader: None,
        fix_ids: Vec::new(),
        overrides: Vec::new(),
        json: false,
        materialized_json: false,
    };
    while let Some(option) = iterator.next() {
        match option.as_str() {
            "--override" => request.overrides.push(
                iterator
                    .next()
                    .ok_or_else(ComConfigExecutionErrorV1::argument)?
                    .clone(),
            ),
            "--profile" => {
                request.profile = iterator
                    .next()
                    .ok_or_else(ComConfigExecutionErrorV1::argument)?
                    .clone()
            }
            "--reader" => {
                request.reader = Some(
                    iterator
                        .next()
                        .ok_or_else(ComConfigExecutionErrorV1::argument)?
                        .clone(),
                )
            }
            "--fix-id" => request.fix_ids.push(
                iterator
                    .next()
                    .ok_or_else(ComConfigExecutionErrorV1::argument)?
                    .clone(),
            ),
            "--json" => request.json = true,
            "--materialized-json" => request.materialized_json = true,
            _ => return Err(ComConfigExecutionErrorV1::argument()),
        }
    }
    let report = config_validate_v1(&request)
        .map_err(|error| ComConfigExecutionErrorV1::from_config(&error))?;
    Ok(if request.json || request.materialized_json {
        report.to_json()
    } else {
        report
            .value()
            .get("text")
            .and_then(serde_json::Value::as_str)
            .map_or_else(|| report.to_json(), ToOwned::to_owned)
    })
}

pub(crate) fn execute_com_compare_argv_v1(
    arguments: &[String],
) -> Result<String, ComConfigExecutionErrorV1> {
    let mut golden = None;
    let mut result = None;
    let mut atol = DEFAULT_ATOL_V1;
    let mut iterator = arguments.iter();
    while let Some(option) = iterator.next() {
        match option.as_str() {
            "--golden" => {
                golden = Some(PathBuf::from(
                    iterator
                        .next()
                        .ok_or_else(ComConfigExecutionErrorV1::argument)?,
                ))
            }
            "--result" => {
                result = Some(PathBuf::from(
                    iterator
                        .next()
                        .ok_or_else(ComConfigExecutionErrorV1::argument)?,
                ))
            }
            "--atol" => {
                atol = iterator
                    .next()
                    .ok_or_else(ComConfigExecutionErrorV1::argument)?
                    .parse()
                    .map_err(|_| ComConfigExecutionErrorV1::argument())?
            }
            _ => return Err(ComConfigExecutionErrorV1::argument()),
        }
    }
    if !atol.is_finite() {
        return Err(ComConfigExecutionErrorV1::argument());
    }
    let report = compare_result_paths_v1(
        &golden.ok_or_else(ComConfigExecutionErrorV1::argument)?,
        &result.ok_or_else(ComConfigExecutionErrorV1::argument)?,
        atol,
    )
    .map_err(|error| ComConfigExecutionErrorV1 {
        exit_code: error_exit_code_v1(&error),
        diagnostic_code: match error {
            DirectCompareErrorV1::Io { .. } => "operational_failure",
            _ => "invalid_input",
        },
    })?;
    Ok(report.to_json())
}

fn map_direct_error_v1(error: DirectRunErrorV1) -> ComR480ExecutionErrorV1 {
    match error {
        DirectRunErrorV1::InvalidRequest(_)
        | DirectRunErrorV1::Config(_)
        | DirectRunErrorV1::Json(_)
        | DirectRunErrorV1::Input { .. }
        | DirectRunErrorV1::InputLimit { .. }
        | DirectRunErrorV1::NonFiniteImpulse { .. }
        | DirectRunErrorV1::Touchstone(_)
        | DirectRunErrorV1::Channel(_)
        | DirectRunErrorV1::Parameters(_)
        | DirectRunErrorV1::Unsupported(_) => ComR480ExecutionErrorV1::InvalidInput,
        DirectRunErrorV1::Execution(_) | DirectRunErrorV1::Artifact(_) => {
            ComR480ExecutionErrorV1::OperationalFailure
        }
    }
}

fn receipt_json_v1(
    report: &sipi_agent_com_direct::DirectRunReportV1,
) -> Result<String, ComR480ExecutionErrorV1> {
    let cases = report
        .result
        .get("cases")
        .and_then(serde_json::Value::as_array)
        .ok_or(ComR480ExecutionErrorV1::OperationalFailure)?;
    let warnings = report
        .result
        .get("warnings")
        .and_then(serde_json::Value::as_array)
        .ok_or(ComR480ExecutionErrorV1::OperationalFailure)?;
    let artifacts = [
        ("result.json", &report.artifacts.result_json),
        ("report.html", &report.artifacts.report_html),
        ("diagnostics.json", &report.artifacts.diagnostics_json),
    ]
    .into_iter()
    .map(|(name, path)| {
        let bytes = fs::read(path).map_err(|_| ComR480ExecutionErrorV1::OperationalFailure)?;
        Ok(format!(
            "{{\"name\":\"{name}\",\"sha256\":\"{:x}\",\"byte_length\":{}}}",
            Sha256::digest(&bytes),
            bytes.len()
        ))
    })
    .collect::<Result<Vec<_>, ComR480ExecutionErrorV1>>()?
    .join(",");
    Ok(format!(
        "{{\"schema\":\"{COM_R480_CLI_RECEIPT_SCHEMA_V1}\",\"status\":\"completed\",\"profile\":\"r4.80\",\"case_count\":{},\"warning_count\":{},\"config_sha256\":\"{}\",\"input_channel_sha256\":\"{}\",\"artifacts\":[{artifacts}]}}",
        cases.len(),
        warnings.len(),
        report.config_sha256,
        report.impulse_sha256,
    ))
}

fn set_singleton_v1(slot: &mut Option<PathBuf>, value: PathBuf) -> Result<(), ComR480ArgvErrorV1> {
    if slot.replace(value).is_some() {
        return Err(ComR480ArgvErrorV1::DuplicateSingleton);
    }
    Ok(())
}

fn parse_local_path_v1(value: &str) -> Result<PathBuf, ComR480ArgvErrorV1> {
    if value.is_empty()
        || value.len() > MAX_COM_R480_PATH_BYTES_V1
        || value.contains('\0')
        || value.contains("://")
    {
        return Err(ComR480ArgvErrorV1::UnsafePath);
    }
    Ok(PathBuf::from(value))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    #[test]
    fn bounded_contract_accepts_only_fixed_r480_file_surface() {
        let request = parse_com_r480_argv_v1(&args(&[
            "--config",
            "config.xlsx",
            "--thru",
            "thru.s4p",
            "--fext",
            "fext-0.s4p",
            "--next",
            "next-0.s4p",
            "--calibration-noise",
            "noise.json",
            "--output-dir",
            "new-output",
        ]))
        .expect("bounded argv request");
        assert_eq!(request.config, PathBuf::from("config.xlsx"));
        assert_eq!(request.thru, PathBuf::from("thru.s4p"));
        assert_eq!(request.fext, vec![PathBuf::from("fext-0.s4p")]);
        assert_eq!(request.next, vec![PathBuf::from("next-0.s4p")]);
        assert_eq!(request.calibration_noise, Some(PathBuf::from("noise.json")));
        assert_eq!(request.output_dir, PathBuf::from("new-output"));
        assert_eq!(COM_R480_ARGV_SCHEMA_V1, "sipi.com.r480.argv.v1");
        assert_eq!(
            COM_R480_CLI_RECEIPT_SCHEMA_V1,
            "sipi.com.r480-cli-receipt.v1"
        );
    }

    #[test]
    fn singleton_and_unknown_options_fail_closed() {
        for values in [
            args(&[
                "--config",
                "a.xlsx",
                "--config",
                "b.xlsx",
                "--thru",
                "thru.s4p",
                "--output-dir",
                "out",
            ]),
            args(&[
                "--config",
                "a.xlsx",
                "--thru",
                "thru.s4p",
                "--output-dir",
                "out",
                "--override",
                "X=1",
            ]),
            args(&["--config", "a.xlsx", "--thru", "thru.s4p", "--output-dir"]),
        ] {
            assert!(parse_com_r480_argv_v1(&values).is_err());
        }
    }

    #[test]
    fn root_config_validate_tail_reuses_the_existing_option_surface() {
        for values in [
            args(&["validate"]),
            args(&["validate", "config.xlsx", "--unknown"]),
            args(&["validate", "config.xlsx", "--profile"]),
            args(&["other", "config.xlsx"]),
        ] {
            assert_eq!(
                execute_com_config_validate_argv_v1(&values),
                Err(ComConfigExecutionErrorV1::argument())
            );
        }
    }

    #[test]
    fn remote_paths_and_excess_channels_are_rejected() {
        let remote = args(&[
            "--config",
            "https://example.invalid/config.xlsx",
            "--thru",
            "thru.s4p",
            "--output-dir",
            "out",
        ]);
        assert_eq!(
            parse_com_r480_argv_v1(&remote),
            Err(ComR480ArgvErrorV1::UnsafePath)
        );

        let mut values = args(&[
            "--config",
            "config.xlsx",
            "--thru",
            "thru.s4p",
            "--output-dir",
            "out",
        ]);
        for index in 0..=MAX_COM_R480_CROSSTALK_CHANNELS_V1 {
            values.extend(args(&["--fext", &format!("fext-{index}.s4p")]));
        }
        assert_eq!(
            parse_com_r480_argv_v1(&values),
            Err(ComR480ArgvErrorV1::TooManyCrosstalkChannels)
        );
    }

    #[test]
    fn errors_map_to_machine_diagnostics() {
        assert_eq!(ComR480ArgvErrorV1::UnknownOption.diagnostic_code(), "usage");
        assert_eq!(
            ComR480ArgvErrorV1::UnsafePath.diagnostic_code(),
            "invalid_input"
        );
    }

    #[test]
    fn execution_emits_a_typed_path_free_receipt_and_requires_a_new_directory() {
        let root = std::env::temp_dir().join(format!(
            "sipi-com-r480-cli-contract-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&root).expect("root");
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        fs::write(
            &config,
            br#"{"parameters":{"samples_per_ui":8.0,"LEVELS":4.0,"bin_size":0.001,"A_v":0.5,"R_LM":50.0,"SNR_TX":30.0,"sigma_X":0.03,"sigma_RJ":0.0001,"h_J":[0.3,0.5,0.2],"sigma_N":0.01,"A_DD":0.4,"spec_ber":0.0001,"f2":50000000000.0}}"#,
        )
        .expect("config");
        let samples = (0..64)
            .map(|index| 0.02 * (index as f64 * 0.21).sin())
            .flat_map(f64::to_le_bytes)
            .collect::<Vec<_>>();
        fs::write(&pulse, samples).expect("pulse");
        let output = root.join("out");
        let command = vec![
            "--config".to_owned(),
            config.to_string_lossy().into_owned(),
            "--thru".to_owned(),
            pulse.to_string_lossy().into_owned(),
            "--output-dir".to_owned(),
            output.to_string_lossy().into_owned(),
        ];
        let mut routed = vec!["com".to_owned(), "run".to_owned()];
        routed.extend(command.clone());
        let response = crate::CommandService::execute(&routed);
        assert_eq!(response.code, 0);
        assert_eq!(response.stderr, None);
        let receipt = response.stdout.expect("execution receipt");
        assert!(!receipt.contains(root.to_string_lossy().as_ref()));
        let value: serde_json::Value = serde_json::from_str(&receipt).expect("receipt JSON");
        assert_eq!(value["schema"], COM_R480_CLI_RECEIPT_SCHEMA_V1);
        assert_eq!(value["status"], "completed");
        assert_eq!(value["profile"], "r4.80");
        assert_eq!(value["artifacts"].as_array().map(Vec::len), Some(3));
        assert_eq!(crate::CommandService::execute(&routed).code, 2);
        let _ = fs::remove_dir_all(root);
    }
}
