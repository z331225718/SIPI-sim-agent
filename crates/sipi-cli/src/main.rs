#![forbid(unsafe_code)]

use std::{env, process};

use sipi_contracts::{CAPABILITIES_SCHEMA, PLANNED_DOMAINS};

const VERSION: &str = env!("CARGO_PKG_VERSION");
const TARGET: &str = "x86_64-pc-windows-msvc";

struct Response {
    code: i32,
    stdout: Option<String>,
    stderr: Option<String>,
}

fn main() {
    let response = dispatch(&env::args().skip(1).collect::<Vec<_>>());
    if let Some(stdout) = response.stdout {
        println!("{stdout}");
    }
    if let Some(stderr) = response.stderr {
        eprintln!("{stderr}");
    }
    process::exit(response.code);
}

fn dispatch(arguments: &[String]) -> Response {
    match arguments {
        [command] if command == "--version" || command == "version" => success(version_json()),
        [command, format] if command == "version" && format == "--json" => success(version_json()),
        [command, format] if command == "capabilities" && format == "--json" => {
            success(capabilities_json())
        }
        [command, ..] if command == "run" => error(
            69,
            "unsupported",
            "simulation domains are not implemented in the P1-01 foundation",
        ),
        _ => error(
            64,
            "usage",
            "supported commands are --version, version --json, and capabilities --json",
        ),
    }
}

fn success(body: String) -> Response {
    Response {
        code: 0,
        stdout: Some(body),
        stderr: None,
    }
}

fn error(code: i32, name: &str, message: &str) -> Response {
    Response {
        code,
        stdout: None,
        stderr: Some(format!(
            "{{\"schema\":\"sipi.cli-error.v1\",\"code\":\"{name}\",\"message\":\"{message}\"}}"
        )),
    }
}

fn version_json() -> String {
    format!(
        "{{\"schema\":\"sipi.cli-version.v1\",\"name\":\"sipi\",\"version\":\"{VERSION}\",\"foundation_stage\":\"{}\"}}",
        sipi_types::FOUNDATION_STAGE
    )
}

fn capabilities_json() -> String {
    let capabilities = PLANNED_DOMAINS
        .iter()
        .map(|domain| {
            format!(
                "{{\"domain\":\"{domain}\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}}"
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "{{\"schema\":\"{CAPABILITIES_SCHEMA}\",\"product\":{{\"name\":\"sipi\",\"version\":\"{VERSION}\"}},\"platform\":{{\"target\":\"{TARGET}\",\"certification\":\"uncertified\"}},\"capabilities\":[{capabilities}]}}"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    #[test]
    fn capability_inventory_is_explicitly_unsupported() {
        let response = dispatch(&args(&["capabilities", "--json"]));

        assert_eq!(response.code, 0);
        assert_eq!(response.stderr, None);
        assert_eq!(
            response.stdout.as_deref(),
            Some(
                "{\"schema\":\"sipi.capabilities.v1\",\"product\":{\"name\":\"sipi\",\"version\":\"0.1.0\"},\"platform\":{\"target\":\"x86_64-pc-windows-msvc\",\"certification\":\"uncertified\"},\"capabilities\":[{\"domain\":\"tran\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"channel\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"ibis-ami\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"com\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}]}"
            )
        );
    }

    #[test]
    fn run_is_fail_closed() {
        let response = dispatch(&args(&["run"]));

        assert_eq!(response.code, 69);
        assert_eq!(response.stdout, None);
        assert_eq!(
            response.stderr.as_deref(),
            Some(
                "{\"schema\":\"sipi.cli-error.v1\",\"code\":\"unsupported\",\"message\":\"simulation domains are not implemented in the P1-01 foundation\"}"
            )
        );
    }
}
