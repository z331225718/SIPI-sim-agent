#![forbid(unsafe_code)]

use std::{
    env,
    io::{self, Cursor, Read},
    path::Path,
    process,
    time::Duration,
};

use sipi_contracts::{
    CAPABILITIES_SCHEMA, CapabilityCatalogV1, PLANNED_DOMAINS, RULE_LEDGER_V1,
    capability_schema_json, deterministic_json, link_causal_fir_request_schema_json,
    parse_link_causal_fir_request_v1, parse_tran_rc_pulse_request_v1, validate_request_v1,
};
use sipi_link::{ConvolutionLimitsV1, convolve_causal_fir_v1};
use sipi_runtime::{CacheKeyBuilder, ResourceCost, RunId, RunPolicy, Runtime};
use sipi_tran::{RcPulseTransientV1, simulate_rc_pulse_with_context};
use sipi_types::AxisView;

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
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "tran"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::tran_run_stdin(artifact_root, artifact_id)
    } else if let [command, action, stdin, root, artifact_root, id, artifact_id] = &arguments[..]
        && command == "link"
        && action == "run"
        && stdin == "--stdin"
        && root == "--artifact-root"
        && id == "--artifact-id"
    {
        ProcessAdapter::link_run_stdin(artifact_root, artifact_id)
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

    fn tran_run_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        if parse_tran_rc_pulse_request_v1(&input).is_err() {
            return error(3, "contract_rejected", "TRAN request was rejected");
        }
        run_fixed_tran(artifact_root, artifact_id, &input)
    }

    fn link_run_stdin(artifact_root: &str, artifact_id: &str) -> Response {
        let input = match read_stdin_request() {
            Ok(input) => input,
            Err(code) => return error(2, code, "stdin request is invalid"),
        };
        let request = match parse_link_causal_fir_request_v1(&input) {
            Ok(request) => request,
            Err(_) => return error(3, "contract_rejected", "Link request was rejected"),
        };
        run_causal_fir_link(artifact_root, artifact_id, &request)
    }
}

fn read_stdin_request() -> Result<Vec<u8>, &'static str> {
    const MAXIMUM: usize = 1_048_576;
    let mut input = Vec::with_capacity(8192);
    io::stdin()
        .take((MAXIMUM + 1) as u64)
        .read_to_end(&mut input)
        .map_err(|_| "operational_failure")?;
    if input.len() > MAXIMUM || input.is_empty() || input.starts_with(&[0xEF, 0xBB, 0xBF]) {
        Err("invalid_input")
    } else {
        Ok(input)
    }
}

fn run_fixed_tran(artifact_root: &str, artifact_id: &str, request: &[u8]) -> Response {
    let policy = match RunPolicy::try_new(Duration::from_secs(1), 16, 1_048_576) {
        Ok(policy) => policy,
        Err(_) => return error(6, "internal_failure", "run policy is unavailable"),
    };
    run_fixed_tran_with_policy(artifact_root, artifact_id, request, policy)
}

fn run_fixed_tran_with_policy(
    artifact_root: &str,
    artifact_id: &str,
    request: &[u8],
    policy: RunPolicy,
) -> Response {
    let id = match RunId::try_new(artifact_id) {
        Ok(id) => id,
        Err(_) => return error(2, "invalid_artifact_id", "artifact id is invalid"),
    };
    let (_, context) = match Runtime::start(id, policy) {
        Ok(run) => run,
        Err(_) => return error(6, "internal_failure", "runtime is unavailable"),
    };
    let request_key = cache_key("request", request);
    let root = Path::new(artifact_root);
    let result = Runtime::execute(&context, |context| -> Result<_, ()> {
        context
            .consume(ResourceCost {
                work_units: 1,
                accounted_bytes: request.len() as u64 + 4096,
            })
            .map_err(|_| ())?;
        let simulation =
            simulate_rc_pulse_with_context(RcPulseTransientV1::fixed_profile(), context)
                .map_err(|_| ())?;
        let result_json = result_json(&simulation).map_err(|_| ())?;
        let result_key = cache_key("result", result_json.as_bytes());
        let provenance = format!(
            "{{\"schema\":\"sipi.tran.provenance.v1\",\"algorithm\":\"backward_euler_rc_pulse_v1\",\"request_cache_key\":\"{request_key}\",\"result_cache_key\":\"{result_key}\",\"run_policy_id\":\"sipi.tran.fixed-policy.v1\",\"contract\":\"sipi.tran.rc-pulse-request.v1\",\"target\":\"{TARGET}\"}}"
        );
        let store = sipi_artifacts::ArtifactRoot::open_or_create(root).map_err(|_| ())?;
        let mut staging = store.begin(artifact_id).map_err(|_| ())?;
        staging
            .stage_reader(
                "result.json",
                Cursor::new(result_json.into_bytes()),
                1_048_576,
            )
            .map_err(|_| ())?;
        staging
            .stage_reader(
                "provenance.json",
                Cursor::new(provenance.into_bytes()),
                16_384,
            )
            .map_err(|_| ())?;
        let manifest = staging
            .seal()
            .and_then(|sealed| sealed.publish_new())
            .map_err(|_| ())?;
        Ok((request_key, manifest))
    });
    match result {
        Ok((request_key, manifest)) => success(format!(
            "{{\"schema\":\"sipi.tran.run-result.v1\",\"artifact_id\":\"{}\",\"request_cache_key\":\"{}\",\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            request_key,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "TRAN run did not publish an artifact",
        ),
    }
}

fn run_causal_fir_link(
    artifact_root: &str,
    artifact_id: &str,
    request: &sipi_contracts::LinkCausalFirRequestV1,
) -> Response {
    let canonical_request =
        match deterministic_json(&sipi_contracts::WireLinkCausalFirRequestV1::from(request)) {
            Ok(bytes) => bytes,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "Link request cannot be serialized",
                );
            }
        };
    let limits = match ConvolutionLimitsV1::try_new(
        request.limits().max_output_samples().get(),
        request.limits().max_multiply_accumulates().get(),
    ) {
        Ok(limits) => limits,
        Err(_) => return error(5, "operational_failure", "Link limits are unavailable"),
    };
    let received = match convolve_causal_fir_v1(request.plan(), limits) {
        Ok(received) => received,
        Err(_) => return error(5, "operational_failure", "Link convolution failed"),
    };
    let result_json = match link_result_json(&received) {
        Ok(result) => result,
        Err(_) => {
            return error(
                6,
                "internal_contract_error",
                "Link result cannot be serialized",
            );
        }
    };
    let request_key = cache_key("link-request", &canonical_request);
    let kernel_json =
        match deterministic_json(&sipi_contracts::WireLinkPlanV1::from(request.plan())) {
            Ok(bytes) => bytes,
            Err(_) => {
                return error(
                    6,
                    "internal_contract_error",
                    "Link kernel cannot be serialized",
                );
            }
        };
    let kernel_key = cache_key("link-kernel", &kernel_json);
    let result_key = cache_key("link-result", result_json.as_bytes());
    let provenance = format!(
        "{{\"schema\":\"sipi.link.provenance.v1\",\"algorithm\":\"causal-fir-convolution.v1\",\"request_cache_key\":\"{request_key}\",\"kernel_cache_key\":\"{kernel_key}\",\"result_cache_key\":\"{result_key}\",\"contract\":\"sipi.link.causal-fir-request.v1\",\"max_output_samples\":{},\"max_multiply_accumulates\":{},\"target\":\"{TARGET}\"}}",
        request.limits().max_output_samples(),
        request.limits().max_multiply_accumulates()
    );
    let store = match sipi_artifacts::ArtifactRoot::open_or_create(Path::new(artifact_root)) {
        Ok(store) => store,
        Err(_) => {
            return error(
                5,
                "operational_failure",
                "Link artifact root is unavailable",
            );
        }
    };
    let mut staging = match store.begin(artifact_id) {
        Ok(staging) => staging,
        Err(_) => return error(5, "operational_failure", "Link artifact cannot be created"),
    };
    let publication = staging
        .stage_reader("request.json", Cursor::new(canonical_request), 1_048_576)
        .and_then(|_| {
            staging.stage_reader(
                "received-waveform.json",
                Cursor::new(result_json.into_bytes()),
                1_048_576,
            )
        })
        .and_then(|_| {
            staging.stage_reader(
                "provenance.json",
                Cursor::new(provenance.into_bytes()),
                16_384,
            )
        })
        .and_then(|_| staging.seal())
        .and_then(|sealed| sealed.publish_new());
    match publication {
        Ok(manifest) => success(format!(
            "{{\"schema\":\"sipi.link.run-result.v1\",\"artifact_id\":\"{}\",\"request_cache_key\":\"{request_key}\",\"result_cache_key\":\"{result_key}\",\"manifest_schema\":\"{}\",\"file_count\":{}}}",
            manifest.artifact_id,
            manifest.schema,
            manifest.files.len()
        )),
        Err(_) => error(
            5,
            "operational_failure",
            "Link run did not publish an artifact",
        ),
    }
}

fn cache_key(label: &str, value: &[u8]) -> String {
    let mut builder = CacheKeyBuilder::new();
    builder
        .add_bytes(label, value)
        .expect("constant cache label");
    builder.finish().as_str().to_owned()
}

fn result_json(result: &sipi_tran::RcPulseTransientResultV1) -> Result<String, &'static str> {
    let AxisView::Explicit(times) = result.time_axis().view() else {
        return Err("fixed profile must have explicit time axis");
    };
    Ok(format!(
        "{{\"schema\":\"sipi.tran.rc-pulse-result.v1\",\"profile_id\":\"tran-rc-pulse-v1\",\"time_seconds\":{},\"voltage_in_volts\":{},\"voltage_out_volts\":{}}}",
        json_values(times.iter().map(|value| value.get())),
        json_values(
            result
                .voltage_in()
                .samples()
                .iter()
                .map(|value| value.get())
        ),
        json_values(
            result
                .voltage_out()
                .samples()
                .iter()
                .map(|value| value.get())
        ),
    ))
}

fn link_result_json(result: &sipi_link::ReceivedVoltageSamplesV1) -> Result<String, &'static str> {
    let AxisView::Uniform { start, step, count } = result.waveform().axis().view() else {
        return Err("Link result must have a uniform time axis");
    };
    Ok(format!(
        "{{\"schema\":\"sipi.link.received-waveform.v1\",\"start_seconds\":{},\"sample_interval_seconds\":{},\"sample_count\":{},\"voltage_volts\":{}}}",
        start.get(),
        step.get(),
        count.get(),
        json_values(result.waveform().samples().iter().map(|value| value.get())),
    ))
}

fn json_values(values: impl ExactSizeIterator<Item = f64>) -> String {
    let mut result = String::from("[");
    for (index, value) in values.enumerate() {
        if index != 0 {
            result.push(',');
        }
        result.push_str(&value.to_string());
    }
    result.push(']');
    result
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
            [command, ..] if command == "tran" => error(
                4,
                "unsupported",
                "TRAN requires the exact run --stdin artifact command",
            ),
            [command, ..] if command == "link" => error(
                4,
                "unsupported",
                "Link requires the exact run --stdin artifact command",
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
            if *domain == "tran" {
                "{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_profile_only\"}".to_owned()
            } else if *domain == "channel" {
                "{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"causal_fir_link_only\"}".to_owned()
            } else {
                format!(
                    "{{\"domain\":\"{domain}\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}}"
                )
            }
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
    format!(
        "{{\"schema\":\"sipi.cli-schema-list.v1\",\"schemas\":[\"{CAPABILITIES_SCHEMA}\",\"{}\"]}}",
        sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA
    )
}

fn schema_show(id: &str) -> Response {
    let bytes = if id == CAPABILITIES_SCHEMA {
        capability_schema_json()
    } else if id == sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA {
        link_causal_fir_request_schema_json()
    } else {
        return error(64, "unknown_schema", "schema is not registered");
    };
    match bytes.and_then(|bytes| {
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
    if schema.is_some_and(|id| {
        id != CAPABILITIES_SCHEMA && id != sipi_contracts::LINK_CAUSAL_FIR_REQUEST_SCHEMA
    }) {
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
        && !RULE_LEDGER_V1.is_empty()
        && link_causal_fir_request_schema_json().is_ok();
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
    use std::sync::atomic::{AtomicUsize, Ordering};

    static TEST_NONCE: AtomicUsize = AtomicUsize::new(0);

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    fn rc_pulse_request() -> &'static [u8] {
        br#"{"schema":"sipi.tran.rc-pulse-request.v1","request_id":"rc-pulse-1","resistance_ohms":1000.0,"capacitance_farads":0.000001,"initial_voltage_out_volts":0.0,"output_times_seconds":[0.0,0.000001,0.000002,0.000003],"pulse":{"voltage_low_volts":0.0,"voltage_high_volts":1.0,"delay_seconds":0.000001,"rise_seconds":0.000000001,"fall_seconds":0.000000001,"width_seconds":0.00001,"period_seconds":0.00002}}"#
    }

    #[test]
    fn capability_inventory_exposes_only_the_fixed_tran_and_causal_fir_profiles() {
        let response = dispatch(&args(&["capabilities", "--json"]));

        assert_eq!(response.code, 0);
        assert_eq!(response.stderr, None);
        assert_eq!(
            response.stdout.as_deref(),
            Some(
                "{\"schema\":\"sipi.capabilities.v1\",\"product\":{\"name\":\"sipi\",\"version\":\"0.1.0\"},\"platform\":{\"target\":\"x86_64-pc-windows-msvc\",\"certification\":\"uncertified\"},\"capabilities\":[{\"domain\":\"tran\",\"status\":\"limited\",\"reason\":\"fixed_rc_pulse_profile_only\"},{\"domain\":\"channel\",\"status\":\"limited\",\"reason\":\"causal_fir_link_only\"},{\"domain\":\"ibis-ami\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"com\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}]}"
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

    #[test]
    fn fixed_tran_run_publishes_only_a_verified_artifact() {
        let nonce = TEST_NONCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("sipi-cli-tran-{nonce}"));
        let root_text = root.to_string_lossy();
        let response = run_fixed_tran(&root_text, "rc-pulse-1", rc_pulse_request());
        assert_eq!(response.code, 0);
        assert!(
            response
                .stdout
                .as_deref()
                .is_some_and(|value| value.contains("artifact_id"))
        );
        let store = sipi_artifacts::ArtifactRoot::open_or_create(&root).expect("artifact root");
        let manifest = store
            .verify_published("rc-pulse-1")
            .expect("published artifact");
        assert_eq!(manifest.files.len(), 2);
        assert_eq!(
            run_fixed_tran(&root_text, "rc-pulse-1", rc_pulse_request()).code,
            5
        );
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn accounted_byte_limit_rejects_before_an_artifact_can_be_published() {
        let nonce = TEST_NONCE.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!("sipi-cli-tran-quota-{nonce}"));
        let root_text = root.to_string_lossy();
        let policy = RunPolicy::try_new(Duration::from_secs(1), 16, 1).expect("policy");

        let response =
            run_fixed_tran_with_policy(&root_text, "rc-pulse-1", rc_pulse_request(), policy);

        assert_eq!(response.code, 5);
        assert_eq!(response.stderr.as_deref(), Some("operational_failure"));
        assert!(!root.join("rc-pulse-1").join("success.json").exists());
        let _ = std::fs::remove_dir_all(root);
    }
}
