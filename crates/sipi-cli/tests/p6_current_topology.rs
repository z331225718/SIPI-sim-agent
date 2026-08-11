//! Cross-boundary P6 negative integration gate for the one admitted topology.
//!
//! This test intentionally owns a test-only publication bridge. P6 has no
//! project executor or artifact writer, so the bridge must never become a
//! product route or a substitute for one.

use std::{
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Output, Stdio},
    time::Duration,
};

use sipi_artifacts::ArtifactRoot;
use sipi_contracts::{
    CausalFirChannelV1, WireProjectEdgeSourceV1, WireProjectEdgeV1, WireProjectInputV1,
    WireProjectNodeV1, WireProjectOutputRefV1, WireProjectPlanV1, WireProjectPortRefV1,
    WireProjectResourcePolicyV1,
};
use sipi_link::ConvolutionLimitsV1;
use sipi_pipeline::{
    CausalFirConsumerConfigV1, LINK_CAUSAL_FIR_KIND_V1, LINK_CAUSAL_FIR_REQUEST_CONTRACT_V1,
    LINK_CAUSAL_FIR_RESULT_CONTRACT_V1, ProjectPlanError, ProjectPlannerV1, TRAN_RC_PULSE_KIND_V1,
    TRAN_RC_PULSE_REQUEST_CONTRACT_V1, TranToLinkEdgeError, derive_fixed_tran_launch_v1,
    run_fixed_tran_to_causal_fir_recorded_v1, run_fixed_tran_to_causal_fir_with_context_v1,
};
use sipi_runtime::{CancelReason, RunId, RunPolicy, Runtime, RuntimeFailure};
use sipi_tran::{RcPulseTransientV1, simulate_rc_pulse};
use sipi_types::{FiniteF64, Seconds};

fn sipi() -> Command {
    Command::new(env!("CARGO_BIN_EXE_sipi"))
}

fn root(label: &str) -> PathBuf {
    std::env::temp_dir().join(format!(
        "sipi-p6-topology-{label}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system clock")
            .as_nanos()
    ))
}

fn consumer(gain: &[f64]) -> CausalFirConsumerConfigV1 {
    CausalFirConsumerConfigV1::try_new(
        CausalFirChannelV1::try_new(
            Seconds::try_new(1.0e-6).expect("interval"),
            gain.iter()
                .copied()
                .map(|value| FiniteF64::try_new(value, "test gain"))
                .collect::<Result<Vec<_>, _>>()
                .expect("finite gain"),
        )
        .expect("channel"),
        ConvolutionLimitsV1::try_new(8, 64).expect("limits"),
    )
    .expect("fixed consumer")
}

fn context(
    id: &str,
    work_units: u64,
    bytes: u64,
) -> (sipi_runtime::RunController, sipi_runtime::RunContext) {
    Runtime::start(
        RunId::try_new(id).expect("run id"),
        RunPolicy::try_new(Duration::from_secs(1), work_units, bytes).expect("policy"),
    )
    .expect("runtime")
}

fn report(root: &Path, artifact_id: &str) -> Output {
    let root = root.to_string_lossy().replace('\\', "\\\\");
    let request = format!(
        "{{\"schema\":\"sipi.artifact-report-request.v1\",\"artifact_root\":\"{root}\",\"artifact_id\":\"{artifact_id}\"}}"
    );
    let mut child = sipi()
        .args(["report", "inspect", "--stdin"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start report inspect");
    child
        .stdin
        .take()
        .expect("stdin")
        .write_all(request.as_bytes())
        .expect("write report request");
    child.wait_with_output().expect("wait report inspect")
}

fn assert_failed_report(output: Output, forbidden: &[&str]) {
    assert_eq!(output.status.code(), Some(5));
    let stdout = String::from_utf8(output.stdout).expect("failure stdout");
    assert!(stdout.contains("\"result\":null"));
    assert!(!stdout.contains("sipi.artifact-report.v1"));
    for value in forbidden {
        assert!(!stdout.contains(value), "stdout leaked {value}");
    }
    let stderr = String::from_utf8(output.stderr).expect("failure stderr");
    assert!(stderr.contains("\"code\":\"operational_failure\""));
    assert!(stderr.contains("\"stage\":\"runtime\""));
}

fn project_with_wrong_cross_domain_edge() -> WireProjectPlanV1 {
    WireProjectPlanV1 {
        schema: "sipi.project.v1".to_owned(),
        project_id: "p6-negative-edge".to_owned(),
        seed_hex: "00".repeat(32),
        resource_policy: WireProjectResourcePolicyV1 {
            timeout_millis: 1,
            max_work_units: 1,
            max_accounted_bytes: 1,
        },
        inputs: vec![
            WireProjectInputV1 {
                id: "tran-request".to_owned(),
                contract: TRAN_RC_PULSE_REQUEST_CONTRACT_V1.to_owned(),
            },
            WireProjectInputV1 {
                id: "link-request".to_owned(),
                contract: LINK_CAUSAL_FIR_REQUEST_CONTRACT_V1.to_owned(),
            },
        ],
        nodes: vec![
            WireProjectNodeV1 {
                id: "tran".to_owned(),
                kind: TRAN_RC_PULSE_KIND_V1.to_owned(),
            },
            WireProjectNodeV1 {
                id: "link".to_owned(),
                kind: LINK_CAUSAL_FIR_KIND_V1.to_owned(),
            },
        ],
        edges: vec![
            WireProjectEdgeV1 {
                from: WireProjectEdgeSourceV1::ProjectInput {
                    input_id: "tran-request".to_owned(),
                },
                to: WireProjectPortRefV1 {
                    node_id: "tran".to_owned(),
                    port: "request".to_owned(),
                },
                contract: TRAN_RC_PULSE_REQUEST_CONTRACT_V1.to_owned(),
            },
            WireProjectEdgeV1 {
                from: WireProjectEdgeSourceV1::NodeOutput {
                    node_id: "tran".to_owned(),
                    port: "result".to_owned(),
                },
                to: WireProjectPortRefV1 {
                    node_id: "link".to_owned(),
                    port: "request".to_owned(),
                },
                contract: LINK_CAUSAL_FIR_REQUEST_CONTRACT_V1.to_owned(),
            },
        ],
        requested_outputs: vec![WireProjectOutputRefV1 {
            node_id: "link".to_owned(),
            port: "result".to_owned(),
            contract: LINK_CAUSAL_FIR_RESULT_CONTRACT_V1.to_owned(),
        }],
    }
}

#[test]
fn current_topology_rejects_wrong_project_edge_before_any_attempt() {
    let plan = project_with_wrong_cross_domain_edge();
    assert_eq!(
        ProjectPlannerV1::validate(plan),
        Err(ProjectPlanError::ContractMismatch)
    );
}

#[test]
fn current_topology_blocks_record_drift_and_failed_attempts_before_publication() {
    let accepted = consumer(&[1.0, 0.5]);
    let recorded =
        run_fixed_tran_to_causal_fir_recorded_v1(RcPulseTransientV1::fixed_profile(), &accepted)
            .expect("recorded control");
    let launch = derive_fixed_tran_launch_v1(
        &simulate_rc_pulse(RcPulseTransientV1::fixed_profile()).expect("tran control"),
    )
    .expect("launch control");
    recorded
        .record()
        .verify_against(&launch, &accepted, recorded.received())
        .expect("control record");

    let drifted_policy = consumer(&[1.0, 0.25]);
    let drifted = run_fixed_tran_to_causal_fir_recorded_v1(
        RcPulseTransientV1::fixed_profile(),
        &drifted_policy,
    )
    .expect("drifted execution");
    assert_ne!(
        recorded.record().consumer_policy_digest(),
        drifted.record().consumer_policy_digest()
    );
    assert!(matches!(
        recorded
            .record()
            .verify_against(&launch, &drifted_policy, drifted.received()),
        Err(TranToLinkEdgeError::EdgeRecordMismatch)
    ));

    let (controller, cancelled) = context("p6-cancelled", 64, 256);
    controller.cancel(CancelReason::Requested);
    assert_eq!(
        run_fixed_tran_to_causal_fir_with_context_v1(
            RcPulseTransientV1::fixed_profile(),
            &accepted,
            &cancelled,
        ),
        Err(RuntimeFailure::Cancelled)
    );
    let (_, exhausted) = context("p6-exhausted", 1, 1);
    assert_eq!(
        run_fixed_tran_to_causal_fir_with_context_v1(
            RcPulseTransientV1::fixed_profile(),
            &accepted,
            &exhausted,
        ),
        Err(RuntimeFailure::ResourceExceeded)
    );
}

#[test]
fn current_topology_reports_only_fully_verified_test_publication() {
    let root = root("report");
    let store = ArtifactRoot::open_or_create(&root).expect("test root");
    let mut staging = store.begin("unpublished").expect("staging");
    staging
        .stage_reader("edge-record.json", &b"partial-edge-record"[..], 1024)
        .expect("partial sidecar");
    drop(staging);
    assert_failed_report(
        report(&root, "unpublished"),
        &["edge-record.json", "partial-edge-record"],
    );

    let control = run_fixed_tran_to_causal_fir_recorded_v1(
        RcPulseTransientV1::fixed_profile(),
        &consumer(&[1.0, 0.5]),
    )
    .expect("edge control");
    let payload = format!(
        "{{\"schema\":\"sipi.test.p6-edge-record.v1\",\"producer_digest\":\"{}\",\"consumer_policy_digest\":\"{}\",\"received_digest\":\"{}\"}}",
        control.record().producer_artifact_digest().hex(),
        control.record().consumer_policy_digest().hex(),
        control.record().received_output_digest().hex(),
    );
    let mut stage = store.begin("edge-attempt").expect("publish staging");
    stage
        .stage_reader("edge-record.json", payload.as_bytes(), 16_384)
        .expect("test record");
    stage.seal().expect("seal").publish_new().expect("publish");

    let verified = report(&root, "edge-attempt");
    assert!(verified.status.success());
    let stdout = String::from_utf8(verified.stdout).expect("verified stdout");
    assert!(stdout.contains("\"schema\":\"sipi.artifact-report.v1\""));
    assert!(stdout.contains("\"verified\":true"));
    assert!(!stdout.contains("edge-record.json"));
    assert!(!stdout.contains("sipi.test.p6-edge-record.v1"));
    assert!(!stdout.contains(root.to_string_lossy().as_ref()));
    assert!(verified.stderr.is_empty());

    std::fs::write(
        root.join("edge-attempt").join("edge-record.json"),
        b"tampered",
    )
    .expect("tamper test publication");
    assert_failed_report(
        report(&root, "edge-attempt"),
        &[
            "edge-record.json",
            "sipi.test.p6-edge-record.v1",
            "tampered",
        ],
    );
    let _ = std::fs::remove_dir_all(root);
}
