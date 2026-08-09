#![forbid(unsafe_code)]

use std::{
    env,
    io::{self, Read},
    process,
};

use sipi_contracts::{
    CAPABILITIES_SCHEMA, CapabilityCatalogV1, PLANNED_DOMAINS, RULE_LEDGER_V1,
    capability_schema_json, deterministic_json, validate_request_v1,
};

const VERSION: &str = env!("CARGO_PKG_VERSION");
const TARGET: &str = "x86_64-pc-windows-msvc";

struct Response {
    code: i32,
    stdout: Option<String>,
    stderr: Option<String>,
}

struct CommandService;

fn main() {
    let arguments = env::args().skip(1).collect::<Vec<_>>();
    let command = arguments.first().map_or("help", String::as_str);
    let response = if arguments == ["validate", "--stdin"] {
        ProcessAdapter::validate_stdin()
    } else {
        dispatch(&arguments)
    };
    println!("{}", envelope_json(command, &response));
    if let Some(stderr) = response.stderr.as_deref() {
        eprintln!("{}", diagnostic_json(command, stderr));
    }
    process::exit(response.code);
}

struct ProcessAdapter;

impl ProcessAdapter {
    fn validate_stdin() -> Response {
        const MAXIMUM: usize = 1_048_576;
        let mut input = Vec::with_capacity(8192);
        if io::stdin()
            .take((MAXIMUM + 1) as u64)
            .read_to_end(&mut input)
            .is_err()
        {
            return error(5, "operational_failure", "stdin could not be read");
        }
        if input.len() > MAXIMUM || input.is_empty() || input.starts_with(&[0xEF, 0xBB, 0xBF]) {
            return error(2, "invalid_input", "stdin request is invalid");
        }
        match validate_request_v1(&input) {
            Ok(()) => success("{\"subject\":\"validation-request\"}".to_owned()),
            Err(_) => error(3, "contract_rejected", "stdin request was rejected"),
        }
    }
}

fn dispatch(arguments: &[String]) -> Response {
    CommandService::execute(arguments)
}

impl CommandService {
    fn execute(arguments: &[String]) -> Response {
        match arguments {
            [command] if command == "--version" || command == "version" => success(version_json()),
            [command, format] if command == "version" && format == "--json" => {
                success(version_json())
            }
            [command, format] if command == "doctor" && format == "--json" => {
                success(doctor_json())
            }
            [command, format] if command == "capabilities" && format == "--json" => {
                success(capabilities_json())
            }
            [command, action, format]
                if command == "schema" && action == "list" && format == "--json" =>
            {
                success(schema_list_json())
            }
            [command, action, id, format]
                if command == "schema" && action == "show" && format == "--json" =>
            {
                schema_show(id)
            }
            [command, action, format]
                if command == "validate" && action == "self" && format == "--json" =>
            {
                validate_self(None)
            }
            [command, action, schema, id, format]
                if command == "validate"
                    && action == "self"
                    && schema == "--schema"
                    && format == "--json" =>
            {
                validate_self(Some(id))
            }
            [command, format] if command == "validate" && format == "--stdin" => error(
                2,
                "invalid_input",
                "stdin validation requires the process adapter",
            ),
            [command, action, format]
                if command == "inspect" && action == "self" && format == "--json" =>
            {
                success(inspect_self_json())
            }
            [command, action, id, format]
                if command == "inspect" && action == "capability" && format == "--json" =>
            {
                inspect_capability(id)
            }
            [command, action, id, format]
                if command == "inspect" && action == "schema" && format == "--json" =>
            {
                schema_show(id)
            }
            [command, ..] if command == "run" => error(
                4,
                "unsupported",
                "simulation domains are not implemented in the P1-01 foundation",
            ),
            _ => error(
                64,
                "usage",
                "supported commands are version, doctor, capabilities, schema, validate, run, and inspect with --json",
            ),
        }
    }
}

fn success(body: String) -> Response {
    Response {
        code: 0,
        stdout: Some(body),
        stderr: None,
    }
}

fn error(code: i32, name: &str, _message: &str) -> Response {
    Response {
        code,
        stdout: None,
        stderr: Some(name.to_owned()),
    }
}

fn envelope_json(command: &str, response: &Response) -> String {
    let status = match response.code {
        0 => "ok",
        2 | 3 => "invalid",
        4 => "unsupported",
        _ => "failed",
    };
    let result = response.stdout.as_deref().unwrap_or("null");
    format!(
        "{{\"schema\":\"sipi.cli.response.v1\",\"protocol\":1,\"command\":\"{command}\",\"request_id\":null,\"status\":\"{status}\",\"result\":{result},\"diagnostic_count\":{}}}",
        usize::from(response.stderr.is_some())
    )
}

fn diagnostic_json(command: &str, message: &str) -> String {
    format!(
        "{{\"schema\":\"sipi.cli.diagnostic.v1\",\"sequence\":1,\"severity\":\"error\",\"code\":\"{message}\",\"command\":\"{command}\",\"request_id\":null,\"location\":null,\"message\":\"command failed\"}}"
    )
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

fn doctor_json() -> String {
    format!(
        "{{\"schema\":\"sipi.cli-doctor.v1\",\"target\":\"{TARGET}\",\"checks\":[{{\"id\":\"contract_registry\",\"status\":\"ok\"}},{{\"id\":\"rule_ledger\",\"status\":\"ok\"}},{{\"id\":\"external_runtime\",\"status\":\"not_checked\"}}]}}"
    )
}

fn schema_list_json() -> String {
    format!("{{\"schema\":\"sipi.cli-schema-list.v1\",\"schemas\":[\"{CAPABILITIES_SCHEMA}\"]}}")
}

fn schema_show(id: &str) -> Response {
    if id != CAPABILITIES_SCHEMA {
        return error(64, "unknown_schema", "schema is not registered");
    }
    match capability_schema_json().and_then(|bytes| {
        String::from_utf8(bytes)
            .map_err(|_| sipi_contracts::ContractError::Json("schema is not UTF-8".to_owned()))
    }) {
        Ok(schema) => success(schema),
        Err(_) => error(
            70,
            "internal_contract_error",
            "registered schema is unavailable",
        ),
    }
}

fn validate_self(schema: Option<&str>) -> Response {
    if schema.is_some_and(|id| id != CAPABILITIES_SCHEMA) {
        return error(64, "unknown_schema", "schema is not registered");
    }
    let catalog = CapabilityCatalogV1::unsupported();
    let valid = catalog.schema == CAPABILITIES_SCHEMA
        && catalog.capabilities.len() == PLANNED_DOMAINS.len()
        && catalog
            .capabilities
            .iter()
            .all(|item| item.status == "unsupported")
        && deterministic_json(&catalog).is_ok()
        && !RULE_LEDGER_V1.is_empty();
    if valid {
        success(
            "{\"schema\":\"sipi.cli-validate.v1\",\"subject\":\"self\",\"status\":\"ok\"}"
                .to_owned(),
        )
    } else {
        error(
            70,
            "self_check_failed",
            "built-in contract self-check failed",
        )
    }
}

fn inspect_self_json() -> String {
    "{\"schema\":\"sipi.cli-inspect.v1\",\"subject\":\"self\",\"scope\":\"static_discovery\",\"status\":\"quarantine\"}".to_owned()
}

fn inspect_capability(id: &str) -> Response {
    if PLANNED_DOMAINS.contains(&id) {
        success(format!(
            "{{\"schema\":\"sipi.cli-inspect.v1\",\"subject\":\"capability\",\"id\":\"{id}\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}}"
        ))
    } else {
        error(64, "unknown_capability", "capability is not registered")
    }
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

        assert_eq!(response.code, 4);
        assert_eq!(response.stdout, None);
        assert_eq!(response.stderr.as_deref(), Some("unsupported"));
    }

    #[test]
    fn discovery_and_self_commands_are_static_and_fail_closed() {
        for command in [
            args(&["doctor", "--json"]),
            args(&["schema", "list", "--json"]),
            args(&["schema", "show", "sipi.capabilities.v1", "--json"]),
            args(&["validate", "self", "--json"]),
            args(&["inspect", "self", "--json"]),
            args(&["inspect", "capability", "tran", "--json"]),
        ] {
            let response = dispatch(&command);
            assert_eq!(response.code, 0);
            assert!(response.stderr.is_none());
        }
        assert_eq!(
            dispatch(&args(&["schema", "show", "unknown", "--json"])).code,
            64
        );
        assert_eq!(
            dispatch(&args(&["inspect", "capability", "unknown", "--json"])).code,
            64
        );
    }
}
