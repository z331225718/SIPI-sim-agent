//! Product-owned specified COM artifact route (P5-08f).
//!
//! This route consumes the existing P5-08a admission, P5-08b execution core,
//! P5-08d artifact verifier, and P5-08e artifact format. It has a distinct
//! product-owned parameter partition and result schema; it does not alter the
//! historical P5-08e source or legacy v1 wire. It is a specified-route
//! prerequisite, not a P5-08 acceptance claim.

use std::{collections::BTreeMap, io::Cursor};

use sipi_artifacts::{ArtifactError, ArtifactRoot, VerifiedConsumptionPolicyV1};

use crate::{
    COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1, COM_RUN_PULSE_FILE_V1, COM_RUN_PULSE_MAX_BYTES_V1,
    COM_RUN_RESULT_FILE_V1, COM_RUN_RESULT_MAX_BYTES_V1,
    COM_SPECIFIED_PARAMETER_INGESTION_POLICY_V1, ComRunAdmissionErrorV1,
    ComRunArtifactProvenanceErrorV1, ComRunArtifactProvenanceV1, ComRunExecutionErrorV1,
    ComRunPulseArtifactIdentityV1, ComRunResultEnvelopeV1,
    ComSpecifiedParameterConsumptionReportV1, ComSpecifiedParameterIngestionErrorV1,
    ComSpecifiedParameterIngestionV1, ResolvedDefaultV1, com_run_admission_v1, execute_com_run_v1,
    ingest_com_specified_parameters_v1, inspect_com_run_artifact_provenance_v1,
    parse_com_run_artifact_binding_v1,
};

pub const COM_RUN_ARTIFACT_SPECIFIED_POLICY_V1: &str =
    "sipi.p5-08f.com-run-artifact-specified-v1.product-owned-non-oracle";
pub const COM_RUN_ARTIFACT_SPECIFIED_RESULT_SCHEMA_V1: &str =
    "sipi.com.run-artifact-specified-result.v1";

const MAX_MANIFEST_BYTES: u64 = 65_536;

#[derive(Debug)]
pub enum ComSpecifiedArtifactExecutionErrorV1 {
    RequestTooLarge,
    Admission(ComRunAdmissionErrorV1),
    NotAdmitted,
    ParameterIngestion(ComSpecifiedParameterIngestionErrorV1),
    NoScalarProjection,
    InvalidPulsePayload,
    NonFinitePulse,
    Execution(ComRunExecutionErrorV1),
    OutputBinding(ComRunArtifactProvenanceErrorV1),
    Artifact(ArtifactError),
    ResultSerialization,
}

impl From<ArtifactError> for ComSpecifiedArtifactExecutionErrorV1 {
    fn from(error: ArtifactError) -> Self {
        Self::Artifact(error)
    }
}

impl From<ComRunExecutionErrorV1> for ComSpecifiedArtifactExecutionErrorV1 {
    fn from(error: ComRunExecutionErrorV1) -> Self {
        Self::Execution(error)
    }
}

impl From<ComSpecifiedParameterIngestionErrorV1> for ComSpecifiedArtifactExecutionErrorV1 {
    fn from(error: ComSpecifiedParameterIngestionErrorV1) -> Self {
        Self::ParameterIngestion(error)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ComSpecifiedArtifactExecutionReportV1 {
    input_artifact_id: String,
    input_manifest_sha256: String,
    pulse_sample_count: usize,
    parameter_consumption: ComSpecifiedParameterConsumptionReportV1,
    result: ComRunResultEnvelopeV1,
    output_provenance: ComRunArtifactProvenanceV1,
}

impl ComSpecifiedArtifactExecutionReportV1 {
    pub fn input_artifact_id(&self) -> &str {
        &self.input_artifact_id
    }

    pub fn input_manifest_sha256(&self) -> &str {
        &self.input_manifest_sha256
    }

    pub const fn pulse_sample_count(&self) -> usize {
        self.pulse_sample_count
    }

    pub fn parameter_consumption(&self) -> &ComSpecifiedParameterConsumptionReportV1 {
        &self.parameter_consumption
    }

    pub fn result(&self) -> &ComRunResultEnvelopeV1 {
        &self.result
    }

    pub fn output_provenance(&self) -> &ComRunArtifactProvenanceV1 {
        &self.output_provenance
    }
}

/// Execute the specified route from caller-owned typed values. The internal
/// legacy request is private to this composition and is not a new public wire.
pub fn execute_com_run_artifact_from_product_values_v1(
    output_artifact_root: &str,
    output_artifact_id: &str,
    pulse_root: &ArtifactRoot,
    pulse_identity: &ComRunPulseArtifactIdentityV1,
    consumed_keys: &[String],
    provided_values: &BTreeMap<String, ResolvedDefaultV1>,
    resolved_defaults: &BTreeMap<String, ResolvedDefaultV1>,
    unconsumed_keys: &[String],
) -> Result<ComSpecifiedArtifactExecutionReportV1, ComSpecifiedArtifactExecutionErrorV1> {
    let parameters = ingest_com_specified_parameters_v1(
        consumed_keys,
        provided_values,
        resolved_defaults,
        unconsumed_keys,
    )?;
    let projection = parameters
        .dto()
        .consumed()
        .iter()
        .find_map(|(key, value)| match value {
            ResolvedDefaultV1::Scalar(value) if value.is_finite() => Some((key, *value)),
            _ => None,
        })
        .ok_or(ComSpecifiedArtifactExecutionErrorV1::NoScalarProjection)?;
    let request = serde_json::json!({
        "schema": "sipi.com.run-request.v1",
        "artifact_root": output_artifact_root,
        "artifact_id": output_artifact_id,
        "params": {projection.0: projection.1},
    });
    execute_request_v1(
        serde_json::to_vec(&request)
            .map_err(|_| ComSpecifiedArtifactExecutionErrorV1::ResultSerialization)?,
        pulse_root,
        pulse_identity,
        &parameters,
    )
}

fn execute_request_v1(
    request_bytes: Vec<u8>,
    pulse_root: &ArtifactRoot,
    pulse_identity: &ComRunPulseArtifactIdentityV1,
    parameters: &ComSpecifiedParameterIngestionV1,
) -> Result<ComSpecifiedArtifactExecutionReportV1, ComSpecifiedArtifactExecutionErrorV1> {
    if request_bytes.len() > COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 {
        return Err(ComSpecifiedArtifactExecutionErrorV1::RequestTooLarge);
    }
    let admission = com_run_admission_v1(&request_bytes)
        .map_err(ComSpecifiedArtifactExecutionErrorV1::Admission)?;
    if !admission.admitted() {
        return Err(ComSpecifiedArtifactExecutionErrorV1::NotAdmitted);
    }
    let output_binding = parse_com_run_artifact_binding_v1(&request_bytes)
        .map_err(ComSpecifiedArtifactExecutionErrorV1::OutputBinding)?;
    let files = pulse_root.consume_exact_verified_v1(
        pulse_identity.artifact_id(),
        pulse_identity.manifest_sha256(),
        &[(COM_RUN_PULSE_FILE_V1, COM_RUN_PULSE_MAX_BYTES_V1)],
        VerifiedConsumptionPolicyV1::try_new(MAX_MANIFEST_BYTES, COM_RUN_PULSE_MAX_BYTES_V1)?,
    )?;
    let pulse = decode_pulse(
        files
            .file(COM_RUN_PULSE_FILE_V1)
            .ok_or(ComSpecifiedArtifactExecutionErrorV1::InvalidPulsePayload)?,
    )?;
    let result = execute_com_run_v1(&request_bytes, &pulse, parameters.dto())?;
    if !result.admitted() {
        return Err(ComSpecifiedArtifactExecutionErrorV1::NotAdmitted);
    }
    let payload = result_payload(
        &result,
        pulse_identity,
        output_binding.artifact_id(),
        pulse.len(),
        parameters.report(),
    )?;
    let output_root = ArtifactRoot::open_or_create(output_binding.artifact_root())?;
    let mut staging = output_root.begin(output_binding.artifact_id())?;
    staging.stage_reader(
        COM_RUN_RESULT_FILE_V1,
        Cursor::new(payload),
        COM_RUN_RESULT_MAX_BYTES_V1,
    )?;
    staging.seal()?.publish_new()?;
    let output_provenance = inspect_com_run_artifact_provenance_v1(&request_bytes)
        .map_err(ComSpecifiedArtifactExecutionErrorV1::OutputBinding)?;
    Ok(ComSpecifiedArtifactExecutionReportV1 {
        input_artifact_id: files.artifact_id().to_owned(),
        input_manifest_sha256: files.manifest_sha256().to_owned(),
        pulse_sample_count: pulse.len(),
        parameter_consumption: parameters.report().clone(),
        result,
        output_provenance,
    })
}

fn decode_pulse(bytes: &[u8]) -> Result<Vec<f64>, ComSpecifiedArtifactExecutionErrorV1> {
    if bytes.is_empty() || !bytes.len().is_multiple_of(8) {
        return Err(ComSpecifiedArtifactExecutionErrorV1::InvalidPulsePayload);
    }
    bytes
        .chunks_exact(8)
        .map(|chunk| {
            let value = f64::from_le_bytes(chunk.try_into().expect("eight-byte chunk"));
            value
                .is_finite()
                .then_some(value)
                .ok_or(ComSpecifiedArtifactExecutionErrorV1::NonFinitePulse)
        })
        .collect()
}

fn result_payload(
    result: &ComRunResultEnvelopeV1,
    input: &ComRunPulseArtifactIdentityV1,
    output_artifact_id: &str,
    pulse_sample_count: usize,
    parameters: &ComSpecifiedParameterConsumptionReportV1,
) -> Result<Vec<u8>, ComSpecifiedArtifactExecutionErrorV1> {
    serde_json::to_vec(&serde_json::json!({
        "schema": COM_RUN_ARTIFACT_SPECIFIED_RESULT_SCHEMA_V1,
        "policy": COM_RUN_ARTIFACT_SPECIFIED_POLICY_V1,
        "input": {
            "artifact_id": input.artifact_id(),
            "manifest_sha256": input.manifest_sha256(),
            "payload": COM_RUN_PULSE_FILE_V1,
            "pulse_sample_count": pulse_sample_count,
        },
        "output_artifact_id": output_artifact_id,
        "parameters": {
            "policy": COM_SPECIFIED_PARAMETER_INGESTION_POLICY_V1,
            "consumed_keys": parameters.consumed_keys(),
            "provided_value_keys": parameters.provided_value_keys(),
            "defaulted_keys": parameters.defaulted_keys(),
            "unconsumed_keys": parameters.unconsumed_keys(),
            "workbook_value_keys": [],
        },
        "result": {
            "schema": result.schema(),
            "policy": result.policy(),
            "admitted": result.admitted(),
            "com_db": result.com_db(),
            "vec_db": result.vec_db(),
            "veo_mv": result.veo_mv(),
            "sigma_n_v": result.sigma_n_v(),
            "invalid_reason": result.invalid_reason(),
        },
        "scope": {
            "behavioral_replication": "not_claimed",
            "agent_com_parity": "not_claimed",
            "external_acceptance": "blocked",
            "ieee_certification": false,
            "release_evidence": false,
        }
    }))
    .map_err(|_| ComSpecifiedArtifactExecutionErrorV1::ResultSerialization)
}
