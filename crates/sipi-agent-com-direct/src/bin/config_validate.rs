use sipi_agent_com_direct::{
    ARGUMENT_ERROR_EXIT_CODE_V1, ConfigValidateRequestV1, config_validate_v1,
};
use std::path::PathBuf;

fn usage() {
    eprintln!(
        "usage: sipi-com-direct-config-validate config validate PATH [--override KEY=VALUE ...] [--profile NAME] [--reader r480|standard] [--fix-id ID ...] [--json|--materialized-json]"
    );
}

fn parse_args() -> Result<ConfigValidateRequestV1, i32> {
    let mut args = std::env::args_os().skip(1);
    if args.next().as_deref().map(|value| value.to_string_lossy()) != Some("config".into())
        || args.next().as_deref().map(|value| value.to_string_lossy()) != Some("validate".into())
    {
        usage();
        return Err(ARGUMENT_ERROR_EXIT_CODE_V1);
    }
    let Some(config) = args.next() else {
        usage();
        return Err(ARGUMENT_ERROR_EXIT_CODE_V1);
    };
    let mut request = ConfigValidateRequestV1 {
        config: PathBuf::from(config),
        profile: "r480".to_owned(),
        reader: None,
        fix_ids: Vec::new(),
        overrides: Vec::new(),
        json: false,
        materialized_json: false,
    };
    while let Some(argument) = args.next() {
        let name = argument.to_string_lossy();
        match name.as_ref() {
            "--help" | "-h" => {
                usage();
                return Err(0);
            }
            "--override" => {
                let Some(value) = args.next() else {
                    usage();
                    return Err(ARGUMENT_ERROR_EXIT_CODE_V1);
                };
                request.overrides.push(value.to_string_lossy().into_owned());
            }
            "--profile" => {
                let Some(value) = args.next() else {
                    usage();
                    return Err(ARGUMENT_ERROR_EXIT_CODE_V1);
                };
                request.profile = value.to_string_lossy().into_owned();
            }
            "--reader" => {
                let Some(value) = args.next() else {
                    usage();
                    return Err(ARGUMENT_ERROR_EXIT_CODE_V1);
                };
                request.reader = Some(value.to_string_lossy().into_owned());
            }
            "--fix-id" => {
                let Some(value) = args.next() else {
                    usage();
                    return Err(ARGUMENT_ERROR_EXIT_CODE_V1);
                };
                request.fix_ids.push(value.to_string_lossy().into_owned());
            }
            "--json" => request.json = true,
            "--materialized-json" => request.materialized_json = true,
            _ => {
                usage();
                return Err(ARGUMENT_ERROR_EXIT_CODE_V1);
            }
        }
    }
    Ok(request)
}

fn main() -> std::process::ExitCode {
    let request = match parse_args() {
        Ok(request) => request,
        Err(code) => return std::process::ExitCode::from(code as u8),
    };
    match config_validate_v1(&request) {
        Ok(report) if request.json || request.materialized_json => {
            println!("{}", report.to_json());
            std::process::ExitCode::SUCCESS
        }
        Ok(report) => {
            if let Some(text) = report.value().get("text").and_then(|value| value.as_str()) {
                println!("{text}");
            } else {
                println!("{}", report.to_json());
            }
            std::process::ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::ExitCode::from(error.exit_code() as u8)
        }
    }
}
