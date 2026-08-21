//! Bounded pulse-artifact to COM-result-artifact composition (P5-08e).
//!
//! This additive consumer connects the existing P5-05g parameter ingestion,
//! P5-08a/b request execution, and P5-08d artifact report without changing
//! either legacy v1 wire. The input is one exact sealed `pulse.f64le` file;
//! the output is one sealed `result.json` artifact at the request's existing
//! root/id binding. Local artifact v1 integrity still assumes no hostile
//! concurrent writer and does not establish external origin or COM parity.

use std::io::Cursor;

use sipi_artifacts::{ArtifactError, ArtifactRoot, VerifiedConsumptionPolicyV1};

use crate::com_parameter_ingestion_v1::{
    COM_PARAMETER_INGESTION_POLICY_V1, ComParameterConsumptionReportV1, ComParameterIngestionV1,
};
use crate::com_run_admission_v1::{ComRunAdmissionErrorV1, com_run_admission_v1};
use crate::com_run_artifact_provenance_v1::{
    COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1, ComRunArtifactProvenanceErrorV1,
    ComRunArtifactProvenanceV1, inspect_com_run_artifact_provenance_v1,
    parse_com_run_artifact_binding_v1,
};
use crate::com_run_execution_v1::{
    COM_RUN_EXECUTION_POLICY_V1, ComRunExecutionErrorV1, ComRunResultEnvelopeV1, execute_com_run_v1,
};
use crate::value_consumption_v1::ResolvedDefaultV1;

pub const COM_RUN_ARTIFACT_EXECUTION_POLICY_V1: &str =
    "sipi.p5-08e.com-run-artifact-execution-v1.bounded";
pub const COM_RUN_PULSE_FILE_V1: &str = "pulse.f64le";
pub const COM_RUN_RESULT_FILE_V1: &str = "result.json";
pub const COM_RUN_ARTIFACT_EXECUTION_RESULT_SCHEMA_V1: &str =
    "sipi.com.run-artifact-execution-result.v1";
pub const COM_RUN_PULSE_MAX_BYTES_V1: u64 = 65_536 * 8;
pub const COM_RUN_RESULT_MAX_BYTES_V1: u64 = 16_384;

const MAX_MANIFEST_BYTES: u64 = 65_536;
const SEMANTICS_STATUS: &str = "product_owned_bounded_execution_complete";
const BEHAVIORAL_REPLICATION_STATUS: &str = "not_claimed";
const EXTERNAL_ACCEPTANCE_STATUS: &str = "blocked_missing_authoritative_reference";
const CAPABILITY_LABEL: &str = "bounded_artifact_execution";
const REPORT_CLAIM: &str =
    "Product-owned bounded payload execution completed; no external equivalence is asserted.";
const REPORT_DISCLAIMER: &str = "This report is not IEEE official certification, a reference implementation, or an external COM comparison result.";
const CAPABILITY_DESCRIPTION: &str = "Consumes one verified local pulse artifact and publishes one verified local COM result artifact.";
const CAPABILITY_DISCLAIMER: &str = "This capability does not establish behavioral replication, standards compliance, conformance, external equivalence, product acceptance, or release readiness.";
const EXTERNAL_ORACLE_STATEMENT: &str = "External oracle comparison remains blocked.";
const METRICS_STATEMENT: &str = "Full metric, checkpoint, and tolerance evidence remains blocked.";
const RUNTIME_STATEMENT: &str = "Bounded local pulse-to-result artifact execution is implemented.";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComRunPulseArtifactIdentityV1 {
    artifact_id: String,
    manifest_sha256: String,
}

impl ComRunPulseArtifactIdentityV1 {
    pub fn try_new(
        artifact_id: impl Into<String>,
        manifest_sha256: impl Into<String>,
    ) -> Result<Self, ComRunArtifactExecutionErrorV1> {
        let artifact_id = artifact_id.into();
        let manifest_sha256 = manifest_sha256.into();
        if artifact_id.is_empty()
            || artifact_id.len() > 128
            || !artifact_id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
            || !is_lowercase_sha256(&manifest_sha256)
        {
            return Err(ComRunArtifactExecutionErrorV1::InvalidInputIdentity);
        }
        Ok(Self {
            artifact_id,
            manifest_sha256,
        })
    }

    pub fn artifact_id(&self) -> &str {
        &self.artifact_id
    }

    pub fn manifest_sha256(&self) -> &str {
        &self.manifest_sha256
    }
}

#[derive(Debug)]
pub enum ComRunArtifactExecutionErrorV1 {
    RequestTooLarge,
    Admission(ComRunAdmissionErrorV1),
    NotAdmitted,
    RequestParameterMismatch,
    InvalidInputIdentity,
    InvalidPulsePayload,
    NonFinitePulse,
    Execution(ComRunExecutionErrorV1),
    OutputBinding(ComRunArtifactProvenanceErrorV1),
    Artifact(ArtifactError),
    ResultSerialization,
}

impl From<ArtifactError> for ComRunArtifactExecutionErrorV1 {
    fn from(error: ArtifactError) -> Self {
        Self::Artifact(error)
    }
}

impl From<ComRunExecutionErrorV1> for ComRunArtifactExecutionErrorV1 {
    fn from(error: ComRunExecutionErrorV1) -> Self {
        Self::Execution(error)
    }
}

/// Product report for one completed local bounded execution.
#[derive(Clone, Debug, PartialEq)]
pub struct ComRunArtifactExecutionReportV1 {
    input_artifact_id: String,
    input_manifest_sha256: String,
    pulse_sample_count: usize,
    parameter_consumption: ComParameterConsumptionReportV1,
    result: ComRunResultEnvelopeV1,
    output_provenance: ComRunArtifactProvenanceV1,
}

impl ComRunArtifactExecutionReportV1 {
    pub fn input_artifact_id(&self) -> &str {
        &self.input_artifact_id
    }

    pub fn input_manifest_sha256(&self) -> &str {
        &self.input_manifest_sha256
    }

    pub const fn pulse_sample_count(&self) -> usize {
        self.pulse_sample_count
    }

    pub fn parameter_consumption(&self) -> &ComParameterConsumptionReportV1 {
        &self.parameter_consumption
    }

    pub fn result(&self) -> &ComRunResultEnvelopeV1 {
        &self.result
    }

    pub fn output_provenance(&self) -> &ComRunArtifactProvenanceV1 {
        &self.output_provenance
    }

    pub const fn semantics_status(&self) -> &'static str {
        SEMANTICS_STATUS
    }

    pub const fn behavioral_replication_status(&self) -> &'static str {
        BEHAVIORAL_REPLICATION_STATUS
    }

    pub const fn external_acceptance_status(&self) -> &'static str {
        EXTERNAL_ACCEPTANCE_STATUS
    }
}

/// Consume one exact pulse artifact, execute the existing COM core with the
/// P5-05g DTO, publish one result artifact, and inspect that output through
/// the existing P5-08d bounded report path.
pub fn execute_com_run_artifact_v1(
    request_bytes: &[u8],
    pulse_root: &ArtifactRoot,
    pulse_identity: &ComRunPulseArtifactIdentityV1,
    parameters: &ComParameterIngestionV1,
) -> Result<ComRunArtifactExecutionReportV1, ComRunArtifactExecutionErrorV1> {
    if request_bytes.len() > COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 {
        return Err(ComRunArtifactExecutionErrorV1::RequestTooLarge);
    }
    let admission =
        com_run_admission_v1(request_bytes).map_err(ComRunArtifactExecutionErrorV1::Admission)?;
    if !admission.admitted() {
        return Err(ComRunArtifactExecutionErrorV1::NotAdmitted);
    }
    let output_binding = parse_com_run_artifact_binding_v1(request_bytes)
        .map_err(ComRunArtifactExecutionErrorV1::OutputBinding)?;
    validate_request_parameter_projection(request_bytes, parameters)?;

    let files = pulse_root.consume_exact_verified_v1(
        pulse_identity.artifact_id(),
        pulse_identity.manifest_sha256(),
        &[(COM_RUN_PULSE_FILE_V1, COM_RUN_PULSE_MAX_BYTES_V1)],
        VerifiedConsumptionPolicyV1::try_new(MAX_MANIFEST_BYTES, COM_RUN_PULSE_MAX_BYTES_V1)?,
    )?;
    let pulse = decode_pulse(
        files
            .file(COM_RUN_PULSE_FILE_V1)
            .ok_or(ComRunArtifactExecutionErrorV1::InvalidPulsePayload)?,
    )?;
    let result = execute_com_run_v1(request_bytes, &pulse, parameters.dto())?;
    if !result.admitted() {
        return Err(ComRunArtifactExecutionErrorV1::NotAdmitted);
    }

    let payload = result_payload(&result, pulse_identity, pulse.len(), parameters.report())?;
    let output_root = ArtifactRoot::open_or_create(output_binding.artifact_root())?;
    let mut staging = output_root.begin(output_binding.artifact_id())?;
    staging.stage_reader(
        COM_RUN_RESULT_FILE_V1,
        Cursor::new(payload),
        COM_RUN_RESULT_MAX_BYTES_V1,
    )?;
    staging.seal()?.publish_new()?;

    let output_provenance = inspect_com_run_artifact_provenance_v1(request_bytes)
        .map_err(ComRunArtifactExecutionErrorV1::OutputBinding)?;
    Ok(ComRunArtifactExecutionReportV1 {
        input_artifact_id: files.artifact_id().to_owned(),
        input_manifest_sha256: files.manifest_sha256().to_owned(),
        pulse_sample_count: pulse.len(),
        parameter_consumption: parameters.report().clone(),
        result,
        output_provenance,
    })
}

fn validate_request_parameter_projection(
    request_bytes: &[u8],
    parameters: &ComParameterIngestionV1,
) -> Result<(), ComRunArtifactExecutionErrorV1> {
    let value: serde_json::Value = serde_json::from_slice(request_bytes)
        .map_err(|_| ComRunArtifactExecutionErrorV1::RequestParameterMismatch)?;
    let request_parameters = value
        .get("params")
        .and_then(serde_json::Value::as_object)
        .ok_or(ComRunArtifactExecutionErrorV1::RequestParameterMismatch)?;
    for (key, request_value) in request_parameters {
        let Some(ingested_value) = parameters.dto().consumed().get(key) else {
            return Err(ComRunArtifactExecutionErrorV1::RequestParameterMismatch);
        };
        let matches = match (request_value, ingested_value) {
            (serde_json::Value::Number(number), ResolvedDefaultV1::Scalar(value)) => {
                number.as_f64() == Some(*value)
            }
            (serde_json::Value::Bool(left), ResolvedDefaultV1::Boolean(right)) => left == right,
            (serde_json::Value::String(left), ResolvedDefaultV1::String(right)) => left == right,
            _ => false,
        };
        if !matches {
            return Err(ComRunArtifactExecutionErrorV1::RequestParameterMismatch);
        }
    }
    Ok(())
}

fn decode_pulse(bytes: &[u8]) -> Result<Vec<f64>, ComRunArtifactExecutionErrorV1> {
    if bytes.is_empty() || !bytes.len().is_multiple_of(8) {
        return Err(ComRunArtifactExecutionErrorV1::InvalidPulsePayload);
    }
    bytes
        .chunks_exact(8)
        .map(|chunk| {
            let value = f64::from_le_bytes(chunk.try_into().expect("eight-byte chunk"));
            value
                .is_finite()
                .then_some(value)
                .ok_or(ComRunArtifactExecutionErrorV1::NonFinitePulse)
        })
        .collect()
}

fn result_payload(
    result: &ComRunResultEnvelopeV1,
    input: &ComRunPulseArtifactIdentityV1,
    pulse_sample_count: usize,
    parameters: &ComParameterConsumptionReportV1,
) -> Result<Vec<u8>, ComRunArtifactExecutionErrorV1> {
    serde_json::to_vec(&serde_json::json!({
        "schema": COM_RUN_ARTIFACT_EXECUTION_RESULT_SCHEMA_V1,
        "policy": COM_RUN_ARTIFACT_EXECUTION_POLICY_V1,
        "input": {
            "artifact_id": input.artifact_id(),
            "manifest_sha256": input.manifest_sha256(),
            "payload": COM_RUN_PULSE_FILE_V1,
            "pulse_sample_count": pulse_sample_count,
            "custody": "local_exact_verified_no_hostile_writer_guarantee"
        },
        "parameters": {
            "policy": COM_PARAMETER_INGESTION_POLICY_V1,
            "consumed_keys": parameters.consumed_keys(),
            "workbook_value_keys": parameters.workbook_value_keys(),
            "defaulted_keys": parameters.defaulted_keys(),
            "unconsumed_keys": parameters.unconsumed_keys()
        },
        "result": {
            "schema": result.schema(),
            "policy": COM_RUN_EXECUTION_POLICY_V1,
            "admitted": result.admitted(),
            "com_db": result.com_db(),
            "vec_db": result.vec_db(),
            "veo_mv": result.veo_mv(),
            "sigma_n_v": result.sigma_n_v(),
            "invalid_reason": result.invalid_reason()
        },
        "scope": {
            "capability_label": CAPABILITY_LABEL,
            "capability_description": CAPABILITY_DESCRIPTION,
            "capability_disclaimer": CAPABILITY_DISCLAIMER,
            "report_claim": REPORT_CLAIM,
            "report_disclaimer": REPORT_DISCLAIMER,
            "external_oracle": EXTERNAL_ORACLE_STATEMENT,
            "metrics": METRICS_STATEMENT,
            "runtime": RUNTIME_STATEMENT,
            "semantics": SEMANTICS_STATUS,
            "behavioral_replication": BEHAVIORAL_REPLICATION_STATUS,
            "external_acceptance": EXTERNAL_ACCEPTANCE_STATUS,
            "ieee_certification": false,
            "release_evidence": false
        }
    }))
    .map_err(|_| ComRunArtifactExecutionErrorV1::ResultSerialization)
}

fn is_lowercase_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[cfg(test)]
mod tests {
    use std::collections::{BTreeMap, BTreeSet};
    use std::fs;
    use std::sync::atomic::{AtomicUsize, Ordering};

    use sha2::{Digest, Sha256};

    use super::*;
    use crate::{
        CellValueV1, ComSettingsV1, RawCellV1, classify_parameter_surface_v1,
        ingest_com_parameters_v1,
    };

    static NEXT_ROOT: AtomicUsize = AtomicUsize::new(0);

    fn temp_root(label: &str) -> std::path::PathBuf {
        let nonce = NEXT_ROOT.fetch_add(1, Ordering::Relaxed);
        std::env::temp_dir().join(format!(
            "sipi-com-artifact-execution-{label}-{}-{nonce}",
            std::process::id()
        ))
    }

    fn pulse64() -> Vec<f64> {
        (0..64)
            .map(|index| {
                let i = index as f64;
                0.5 * (-(i - 28.0) * (i - 28.0) / 80.0).exp() * (i - 28.0) * 0.4
                    + 0.002 * (i * 0.9).sin()
            })
            .collect()
    }

    fn pulse_bytes(pulse: &[f64]) -> Vec<u8> {
        pulse.iter().flat_map(|value| value.to_le_bytes()).collect()
    }

    fn sha256(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    fn publish_pulse(root: &std::path::Path, bytes: &[u8]) -> ComRunPulseArtifactIdentityV1 {
        let store = ArtifactRoot::open_or_create(root).expect("pulse root");
        let mut staging = store.begin("pulse-1").expect("pulse staging");
        staging
            .stage_reader(COM_RUN_PULSE_FILE_V1, bytes, COM_RUN_PULSE_MAX_BYTES_V1)
            .expect("pulse payload");
        staging
            .seal()
            .expect("seal")
            .publish_new()
            .expect("publish");
        let manifest = fs::read(root.join("pulse-1").join("success.json")).expect("manifest");
        ComRunPulseArtifactIdentityV1::try_new("pulse-1", sha256(&manifest)).expect("identity")
    }

    fn cell(row: usize, value: CellValueV1) -> Vec<RawCellV1> {
        vec![
            RawCellV1::new(
                "COM_Settings".to_owned(),
                format!("A{}", row + 1),
                CellValueV1::String(
                    [
                        "samples_per_ui",
                        "LEVELS",
                        "bin_size",
                        "A_v",
                        "R_LM",
                        "SNR_TX",
                        "sigma_X",
                        "sigma_RJ",
                        "h_J",
                        "sigma_N",
                        "A_DD",
                        "spec_ber",
                    ][row]
                        .to_owned(),
                ),
                None,
            ),
            RawCellV1::new(
                "COM_Settings".to_owned(),
                format!("B{}", row + 1),
                value,
                None,
            ),
        ]
    }

    fn parameters() -> ComParameterIngestionV1 {
        let values = vec![
            CellValueV1::Number(8.0),
            CellValueV1::Number(4.0),
            CellValueV1::Number(0.01),
            CellValueV1::Number(0.5),
            CellValueV1::Number(50.0),
            CellValueV1::Number(30.0),
            CellValueV1::Number(0.03),
            CellValueV1::Number(1e-4),
            CellValueV1::Array {
                dims: vec![3],
                data: vec![0.3, 0.5, 0.2],
            },
            CellValueV1::Number(0.01),
            CellValueV1::Number(0.4),
            CellValueV1::Number(1e-4),
        ];
        let settings = ComSettingsV1::from_cells(
            values
                .into_iter()
                .enumerate()
                .map(|(row, value)| cell(row, value))
                .collect(),
            None,
        );
        let keys = [
            "samples_per_ui",
            "LEVELS",
            "bin_size",
            "A_v",
            "R_LM",
            "SNR_TX",
            "sigma_X",
            "sigma_RJ",
            "h_J",
            "sigma_N",
            "A_DD",
            "spec_ber",
        ]
        .map(str::to_owned)
        .to_vec();
        let canonical = keys.iter().cloned().collect::<BTreeSet<_>>();
        let surface = classify_parameter_surface_v1(&settings, &canonical).expect("surface");
        ingest_com_parameters_v1(&settings, &surface, &keys, &BTreeMap::new())
            .expect("parameter ingestion")
    }

    fn request(output: &std::path::Path, id: &str) -> Vec<u8> {
        serde_json::json!({
            "schema": "sipi.com.run-request.v1",
            "artifact_root": output.to_string_lossy(),
            "artifact_id": id,
            "params": {"A_v": 0.5}
        })
        .to_string()
        .into_bytes()
    }

    #[test]
    fn exact_pulse_to_com_to_verified_result_artifact() {
        let pulse_root = temp_root("input");
        let output_root = temp_root("output");
        let identity = publish_pulse(&pulse_root, &pulse_bytes(&pulse64()));
        let reader = ArtifactRoot::open_existing(&pulse_root).expect("reader");
        let request = request(&output_root, "result-1");
        let report = execute_com_run_artifact_v1(&request, &reader, &identity, &parameters())
            .expect("artifact execution");

        assert!(report.result().admitted());
        assert_eq!(report.pulse_sample_count(), 64);
        assert_eq!(report.parameter_consumption().consumed_keys().len(), 12);
        assert!(report.output_provenance().report().verified);
        assert_eq!(report.output_provenance().report().entry_count, 1);
        assert_eq!(report.semantics_status(), SEMANTICS_STATUS);
        assert_eq!(
            report.behavioral_replication_status(),
            BEHAVIORAL_REPLICATION_STATUS
        );

        let payload = fs::read(output_root.join("result-1").join(COM_RUN_RESULT_FILE_V1))
            .expect("result payload");
        let value: serde_json::Value = serde_json::from_slice(&payload).expect("result json");
        assert_eq!(value["schema"], COM_RUN_ARTIFACT_EXECUTION_RESULT_SCHEMA_V1);
        assert_eq!(value["scope"]["semantics"], SEMANTICS_STATUS);
        assert_eq!(value["scope"]["capability_label"], CAPABILITY_LABEL);
        assert_eq!(
            value["scope"]["capability_description"],
            CAPABILITY_DESCRIPTION
        );
        assert_eq!(
            value["scope"]["capability_disclaimer"],
            CAPABILITY_DISCLAIMER
        );
        assert_eq!(value["scope"]["report_claim"], REPORT_CLAIM);
        assert_eq!(value["scope"]["report_disclaimer"], REPORT_DISCLAIMER);
        assert_eq!(value["scope"]["external_oracle"], EXTERNAL_ORACLE_STATEMENT);
        assert_eq!(value["scope"]["metrics"], METRICS_STATEMENT);
        assert_eq!(value["scope"]["runtime"], RUNTIME_STATEMENT);
        assert_eq!(
            value["scope"]["external_acceptance"],
            EXTERNAL_ACCEPTANCE_STATUS
        );

        fs::remove_dir_all(pulse_root).expect("remove input");
        fs::remove_dir_all(output_root).expect("remove output");
    }

    #[test]
    fn rejects_wrong_manifest_before_output_publication() {
        let pulse_root = temp_root("wrong-manifest-input");
        let output_root = temp_root("wrong-manifest-output");
        let _identity = publish_pulse(&pulse_root, &pulse_bytes(&pulse64()));
        let wrong = ComRunPulseArtifactIdentityV1::try_new("pulse-1", "0".repeat(64))
            .expect("syntactically valid identity");
        let reader = ArtifactRoot::open_existing(&pulse_root).expect("reader");
        let result = execute_com_run_artifact_v1(
            &request(&output_root, "result-1"),
            &reader,
            &wrong,
            &parameters(),
        );
        assert!(matches!(
            result,
            Err(ComRunArtifactExecutionErrorV1::Artifact(
                ArtifactError::HashMismatch
            ))
        ));
        assert!(!output_root.join("result-1").exists());
        fs::remove_dir_all(pulse_root).expect("remove input");
    }

    #[test]
    fn rejects_nonfinite_pulse_before_output_publication() {
        let pulse_root = temp_root("nonfinite-input");
        let output_root = temp_root("nonfinite-output");
        let identity = publish_pulse(&pulse_root, &pulse_bytes(&[1.0, f64::NAN]));
        let reader = ArtifactRoot::open_existing(&pulse_root).expect("reader");
        let result = execute_com_run_artifact_v1(
            &request(&output_root, "result-1"),
            &reader,
            &identity,
            &parameters(),
        );
        assert!(matches!(
            result,
            Err(ComRunArtifactExecutionErrorV1::NonFinitePulse)
        ));
        assert!(!output_root.join("result-1").exists());
        fs::remove_dir_all(pulse_root).expect("remove input");
    }

    #[test]
    fn rejects_request_parameter_that_disagrees_with_ingestion() {
        let pulse_root = temp_root("parameter-mismatch-input");
        let output_root = temp_root("parameter-mismatch-output");
        let identity = publish_pulse(&pulse_root, &pulse_bytes(&pulse64()));
        let reader = ArtifactRoot::open_existing(&pulse_root).expect("reader");
        let request = serde_json::json!({
            "schema": "sipi.com.run-request.v1",
            "artifact_root": output_root.to_string_lossy(),
            "artifact_id": "result-1",
            "params": {"A_v": 0.75}
        })
        .to_string();
        assert!(matches!(
            execute_com_run_artifact_v1(request.as_bytes(), &reader, &identity, &parameters()),
            Err(ComRunArtifactExecutionErrorV1::RequestParameterMismatch)
        ));
        assert!(!output_root.join("result-1").exists());
        fs::remove_dir_all(pulse_root).expect("remove input");
    }

    #[test]
    fn invalid_or_unadmitted_request_never_consumes_or_publishes() {
        let input_root = temp_root("unused-input");
        let missing = ArtifactRoot::open_or_create(&input_root).expect("root");
        let identity =
            ComRunPulseArtifactIdentityV1::try_new("missing", "0".repeat(64)).expect("identity");
        assert!(matches!(
            execute_com_run_artifact_v1(b"not-json", &missing, &identity, &parameters()),
            Err(ComRunArtifactExecutionErrorV1::Admission(
                ComRunAdmissionErrorV1::InvalidJson
            ))
        ));
        let unadmitted = serde_json::json!({
            "schema": "sipi.com.run-request.v1",
            "artifact_root": "unused-output",
            "artifact_id": "result-1",
            "params": {}
        })
        .to_string();
        assert!(matches!(
            execute_com_run_artifact_v1(unadmitted.as_bytes(), &missing, &identity, &parameters()),
            Err(ComRunArtifactExecutionErrorV1::NotAdmitted)
        ));
        fs::remove_dir_all(input_root).expect("remove input");
    }

    #[test]
    fn oversized_request_rejects_before_artifact_io() {
        let input_root = temp_root("oversized-unused-input");
        let missing = ArtifactRoot::open_or_create(&input_root).expect("root");
        let identity =
            ComRunPulseArtifactIdentityV1::try_new("missing", "0".repeat(64)).expect("identity");
        let request = vec![b' '; COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 + 1];
        assert!(matches!(
            execute_com_run_artifact_v1(&request, &missing, &identity, &parameters()),
            Err(ComRunArtifactExecutionErrorV1::RequestTooLarge)
        ));
        assert!(!input_root.join("missing").exists());
        fs::remove_dir_all(input_root).expect("remove input");
    }

    #[test]
    fn policy_and_identity_are_stable() {
        assert_eq!(
            COM_RUN_ARTIFACT_EXECUTION_POLICY_V1,
            "sipi.p5-08e.com-run-artifact-execution-v1.bounded"
        );
        assert_eq!(COM_RUN_PULSE_MAX_BYTES_V1, 524_288);
        assert!(ComRunPulseArtifactIdentityV1::try_new("../pulse", "0".repeat(64)).is_err());
        assert!(ComRunPulseArtifactIdentityV1::try_new("pulse-1", "A".repeat(64)).is_err());
    }
}
