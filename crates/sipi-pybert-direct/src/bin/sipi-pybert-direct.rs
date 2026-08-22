use std::{env, path::PathBuf, process::ExitCode};

use sipi_pybert_direct::{
    DirectRunError, LegacySimRequestV1, run_legacy_sim_v1, run_sim_native_file,
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
