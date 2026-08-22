use std::{env, path::PathBuf, process::ExitCode};

use sipi_pybert_direct::{DirectRunError, run_sim_native_file};

fn main() -> ExitCode {
    let (input_file, output_dir) = match arguments() {
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

fn arguments() -> Result<(PathBuf, PathBuf), DirectRunError> {
    let mut arguments = env::args_os().skip(1);
    let Some(input_file) = arguments.next() else {
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
