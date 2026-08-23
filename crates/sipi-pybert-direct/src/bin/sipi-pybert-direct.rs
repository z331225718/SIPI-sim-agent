use std::{env, ffi::OsString, path::PathBuf, process::ExitCode};

use sipi_pybert_direct::{
    DirectRunError, LegacySimRequestV1, WorkflowError, run_legacy_sim_v1, run_sim_auto_file,
    run_sim_compare_file, run_sim_native_file, run_sim_rust_file,
};

fn main() -> ExitCode {
    let mut arguments = env::args_os().skip(1);
    let first = arguments.next();
    if first.as_deref() == Some("--version".as_ref()) {
        println!("sipi-pybert-direct 0.1.0");
        return ExitCode::SUCCESS;
    }
    if first.as_deref() == Some("sim".as_ref()) {
        return run_legacy(arguments);
    }
    if let Some(command) = first.as_deref() {
        let command = command.to_string_lossy();
        if matches!(
            command.as_ref(),
            "sim-native" | "sim-rust" | "sim-auto" | "sim-compare"
        ) {
            let values = arguments.collect::<Vec<_>>();
            return run_projected(command.as_ref(), values);
        }
    }
    let (input_file, output_dir) = match native_arguments_from(first, arguments) {
        Ok(arguments) => arguments,
        Err(error) => {
            eprintln!("{}", error.error_json());
            return ExitCode::from(2);
        }
    };
    match run_sim_native_file(&input_file, &output_dir) {
        Ok(report) => {
            println!("{}", output_dir.display());
            let _ = report;
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{}", error.error_json());
            ExitCode::from(1)
        }
    }
}

fn run_projected(command: &str, arguments: Vec<OsString>) -> ExitCode {
    let (config_file, output_dir, statistical_time_points, reference_json) =
        match projected_arguments(command, arguments) {
            Ok(value) => value,
            Err(error) => {
                eprintln!("{}", error.error_json());
                return ExitCode::from(2);
            }
        };
    let result = match command {
        "sim-rust" => run_sim_rust_file(&config_file, &output_dir, statistical_time_points),
        "sim-auto" => run_sim_auto_file(&config_file, &output_dir, statistical_time_points),
        "sim-compare" => run_sim_compare_file(
            &config_file,
            &output_dir,
            statistical_time_points,
            reference_json.as_deref(),
        ),
        "sim-native" => run_sim_native_file(&config_file, &output_dir)
            .map_err(|error| WorkflowError::Artifact(error.to_string())),
        _ => unreachable!("command was checked before dispatch"),
    };
    match result {
        Ok(_) => {
            println!("{}", output_dir.display());
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{}", error.error_json());
            ExitCode::from(1)
        }
    }
}

fn projected_arguments(
    command: &str,
    arguments: Vec<OsString>,
) -> Result<(PathBuf, PathBuf, Option<u32>, Option<PathBuf>), WorkflowError> {
    let mut values = arguments.into_iter();
    let config_file = values.next().map(PathBuf::from).ok_or_else(|| {
        WorkflowError::InvalidInput(format!("usage: {command} CONFIG --output-dir OUTPUT"))
    })?;
    let mut output_dir = None;
    let mut statistical_time_points = None;
    let mut reference_json = None;
    while let Some(flag) = values.next() {
        match flag.to_string_lossy().as_ref() {
            "--output-dir" => {
                if output_dir.is_some() {
                    return Err(WorkflowError::InvalidInput(
                        "--output-dir may be specified only once".into(),
                    ));
                }
                output_dir = values.next().map(PathBuf::from);
                if output_dir.is_none() {
                    return Err(WorkflowError::InvalidInput(
                        "--output-dir requires a directory".into(),
                    ));
                }
            }
            "--statistical-time-points"
                if matches!(command, "sim-rust" | "sim-auto" | "sim-compare") =>
            {
                if statistical_time_points.is_some() {
                    return Err(WorkflowError::InvalidInput(
                        "--statistical-time-points may be specified only once".into(),
                    ));
                }
                let raw = values.next().ok_or_else(|| {
                    WorkflowError::InvalidInput(
                        "--statistical-time-points requires an integer".into(),
                    )
                })?;
                let value = raw.to_string_lossy().parse::<u32>().map_err(|_| {
                    WorkflowError::InvalidInput(
                        "--statistical-time-points requires an integer".into(),
                    )
                })?;
                statistical_time_points = Some(value);
            }
            "--statistical-time-points" => {
                return Err(WorkflowError::InvalidInput(format!(
                    "--statistical-time-points is not supported by {command}"
                )));
            }
            "--reference-json" if command == "sim-compare" => {
                if reference_json.is_some() {
                    return Err(WorkflowError::InvalidInput(
                        "--reference-json may be specified only once".into(),
                    ));
                }
                reference_json = values.next().map(PathBuf::from);
                if reference_json.is_none() {
                    return Err(WorkflowError::InvalidInput(
                        "--reference-json requires a file".into(),
                    ));
                }
            }
            _ => {
                return Err(WorkflowError::InvalidInput(format!(
                    "unknown {command} option: {}",
                    flag.to_string_lossy()
                )));
            }
        }
    }
    let output_dir = output_dir.ok_or_else(|| {
        WorkflowError::InvalidInput(format!("usage: {command} CONFIG --output-dir OUTPUT"))
    })?;
    Ok((
        config_file,
        output_dir,
        statistical_time_points,
        reference_json,
    ))
}

fn native_arguments_from(
    first: Option<std::ffi::OsString>,
    mut arguments: impl Iterator<Item = std::ffi::OsString>,
) -> Result<(PathBuf, PathBuf), DirectRunError> {
    let Some(input_file) = first else {
        return Err(DirectRunError::Usage);
    };
    if arguments.next().as_deref() != Some("--output-dir".as_ref()) {
        return Err(DirectRunError::Usage);
    }
    let Some(output_dir) = arguments.next() else {
        return Err(DirectRunError::Usage);
    };
    if arguments.next().is_some() {
        return Err(DirectRunError::Usage);
    }
    Ok((input_file.into(), output_dir.into()))
}

fn run_legacy(mut arguments: impl Iterator<Item = std::ffi::OsString>) -> ExitCode {
    let Some(config_file) = arguments.next().map(PathBuf::from) else {
        eprintln!("usage: sipi-pybert-direct sim CONFIG [--results RESULTS]");
        return ExitCode::from(2);
    };
    let results = match arguments.next() {
        None => None,
        Some(flag) if flag == "--results" => {
            let Some(path) = arguments.next() else {
                eprintln!("usage: sipi-pybert-direct sim CONFIG [--results RESULTS]");
                return ExitCode::from(2);
            };
            Some(PathBuf::from(path))
        }
        Some(_) => {
            eprintln!("usage: sipi-pybert-direct sim CONFIG [--results RESULTS]");
            return ExitCode::from(2);
        }
    };
    if arguments.next().is_some() {
        eprintln!("usage: sipi-pybert-direct sim CONFIG [--results RESULTS]");
        return ExitCode::from(2);
    }
    let request = LegacySimRequestV1 {
        config_file,
        results,
    };
    match run_legacy_sim_v1(&request) {
        Ok(report) => {
            println!("{}", report.result_path.display());
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::from(1)
        }
    }
}
