use sipi_agent_com_direct::{
    CONFIG_ERROR_EXIT_CODE_V1, DEFAULT_ATOL_V1, DirectCompareErrorV1,
    JSON_INPUT_ERROR_EXIT_CODE_V1, compare_result_paths_v1, error_exit_code_v1,
};
use std::path::PathBuf;

fn usage() {
    eprintln!("usage: sipi-com-direct-compare --golden PATH --result PATH [--atol FLOAT]");
}

fn parse_args() -> Result<(PathBuf, PathBuf, f64), i32> {
    let mut golden = None;
    let mut result = None;
    let mut atol = DEFAULT_ATOL_V1;
    let mut args = std::env::args_os().skip(1);
    while let Some(argument) = args.next() {
        match argument.to_string_lossy().as_ref() {
            "--help" | "-h" => {
                usage();
                return Err(0);
            }
            "--golden" => golden = args.next().map(PathBuf::from),
            "--result" => result = args.next().map(PathBuf::from),
            "--atol" => {
                let Some(value) = args.next() else {
                    usage();
                    return Err(JSON_INPUT_ERROR_EXIT_CODE_V1);
                };
                atol = value.to_string_lossy().parse::<f64>().map_err(|_| {
                    usage();
                    JSON_INPUT_ERROR_EXIT_CODE_V1
                })?;
            }
            _ => {
                usage();
                return Err(JSON_INPUT_ERROR_EXIT_CODE_V1);
            }
        }
    }
    match (golden, result) {
        (Some(golden), Some(result)) => Ok((golden, result, atol)),
        _ => {
            usage();
            Err(JSON_INPUT_ERROR_EXIT_CODE_V1)
        }
    }
}

fn main() -> std::process::ExitCode {
    let (golden, result, atol) = match parse_args() {
        Ok(value) => value,
        Err(code) => return std::process::ExitCode::from(code as u8),
    };
    match compare_result_paths_v1(&golden, &result, atol) {
        Ok(report) => {
            println!("{}", report.to_json());
            std::process::ExitCode::from(report.exit_code() as u8)
        }
        Err(error) => {
            eprintln!("{error}");
            let code = match error {
                DirectCompareErrorV1::Json(_) => JSON_INPUT_ERROR_EXIT_CODE_V1,
                DirectCompareErrorV1::Schema(_) | DirectCompareErrorV1::NegativeTolerance => {
                    CONFIG_ERROR_EXIT_CODE_V1
                }
                _ => error_exit_code_v1(&error),
            };
            std::process::ExitCode::from(code as u8)
        }
    }
}
