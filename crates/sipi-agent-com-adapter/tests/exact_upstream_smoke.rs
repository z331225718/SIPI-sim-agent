//! Opt-in smoke only.  It consumes caller-provided external Agent-COM assets
//! and is intentionally ignored in normal CI.

use sipi_agent_com_adapter::{
    AdapterConfig, AdapterLimits, AgentComAdapter, BackendCommand, ConfigValidateRequest,
    UPSTREAM_COMMIT,
};
use std::path::PathBuf;

#[test]
#[ignore = "requires an externally provisioned com8023 executable and workbook"]
fn exact_pinned_cli_config_validate_smoke() {
    let executable = std::env::var_os("SIPI_AGENT_COM_EXECUTABLE")
        .map(PathBuf::from)
        .expect("SIPI_AGENT_COM_EXECUTABLE");
    let workbook = std::env::var_os("SIPI_AGENT_COM_CONFIG")
        .map(PathBuf::from)
        .expect("SIPI_AGENT_COM_CONFIG");
    let adapter = AgentComAdapter::new(AdapterConfig {
        cli: BackendCommand::new(executable),
        python: BackendCommand::new("python"),
        working_directory: std::env::current_dir().expect("current working directory"),
        limits: AdapterLimits::default(),
        cancellation: Default::default(),
    })
    .unwrap();
    let response = adapter
        .config_validate(&ConfigValidateRequest {
            config: workbook,
            profile: None,
            reader: None,
            fix_ids: vec![],
            overrides: vec![],
            json: true,
            materialized_json: false,
        })
        .unwrap();
    assert!(
        response.report.is_some(),
        "pinned Agent-COM {UPSTREAM_COMMIT} did not return JSON"
    );
}
