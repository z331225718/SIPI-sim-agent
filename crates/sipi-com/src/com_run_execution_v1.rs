//! COM run execution and result envelope core (P5-08b).
//!
//! Connects the `sipi.com.run-request.v1` admission preflight (P5-08a) with
//! parameter resolution (P5-05f) and the fixed-tap COM chain (P5-06f) into a
//! typed result envelope (`ComRunResultEnvelopeV1`).
//! Fail-closed: unadmitted requests or chain errors emit structured failure
//! envelopes; invalid inputs fail closed cleanly.

use crate::com_chain_v1::{
    ComChainErrorV1, ComWinnerContextV1, run_com_chain_with_crosstalk_v1,
    run_com_chain_with_winner_v1,
};
use crate::com_parameter_resolver_v1::{
    ComParameterResolverErrorV1, resolve_com_parameter_controls_v1,
};
use crate::com_parameters_v1::ComParametersV1;
use crate::com_run_admission_v1::{ComRunAdmissionErrorV1, com_run_admission_v1};
use crate::search_loop_v1::SearchLoopResultWithWinnerV2;

/// Scope policy of the COM run execution core.
pub const COM_RUN_EXECUTION_POLICY_V1: &str =
    "sipi.p5-08b.com-run-execution-v1.admission-to-result";

/// Canonical "sipi com run" result envelope schema id.
pub const COM_RUN_RESULT_SCHEMA_V1: &str = "sipi.com.run-result.v1";

// The v1 result envelope historically exposed these exact enum-style tokens.
// Keep the mapping explicit so a Rust rename cannot silently alter the wire.
fn legacy_v1_admission_error_code(error: &ComRunAdmissionErrorV1) -> &'static str {
    match error {
        ComRunAdmissionErrorV1::InvalidJson => "InvalidJson",
        ComRunAdmissionErrorV1::SchemaMismatch => "SchemaMismatch",
        ComRunAdmissionErrorV1::MissingArtifactRoot => "MissingArtifactRoot",
        ComRunAdmissionErrorV1::MissingArtifactId => "MissingArtifactId",
        ComRunAdmissionErrorV1::EmptyParams => "EmptyParams",
        ComRunAdmissionErrorV1::NonScalarParam => "NonScalarParam",
    }
}

/// Fail-closed errors when performing COM run execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComRunExecutionErrorV1 {
    Admission(ComRunAdmissionErrorV1),
    Resolver(ComParameterResolverErrorV1),
    Chain(ComChainErrorV1),
}

impl From<ComRunAdmissionErrorV1> for ComRunExecutionErrorV1 {
    fn from(err: ComRunAdmissionErrorV1) -> Self {
        ComRunExecutionErrorV1::Admission(err)
    }
}
impl From<ComParameterResolverErrorV1> for ComRunExecutionErrorV1 {
    fn from(err: ComParameterResolverErrorV1) -> Self {
        ComRunExecutionErrorV1::Resolver(err)
    }
}
impl From<ComChainErrorV1> for ComRunExecutionErrorV1 {
    fn from(err: ComChainErrorV1) -> Self {
        ComRunExecutionErrorV1::Chain(err)
    }
}

/// The typed result envelope for a "sipi com run" execution.
#[derive(Clone, Debug, PartialEq)]
pub struct ComRunResultEnvelopeV1 {
    schema: &'static str,
    policy: &'static str,
    admitted: bool,
    com_db: Option<f64>,
    vec_db: Option<f64>,
    veo_mv: Option<f64>,
    sigma_n_v: Option<f64>,
    available_signal_v: Option<f64>,
    interference_noise_v: Option<f64>,
    threshold_der: Option<f64>,
    eye_opening_v: Option<f64>,
    thru_selected_phase: Option<i64>,
    fext_selected_phases: Vec<i64>,
    next_selected_phases: Vec<i64>,
    invalid_reason: Option<String>,
}

/// Typed payload emitted by the validated portable ERL branch.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ErlOnlyMetricsV1 {
    pub erl_db: f64,
    pub erl11_db: f64,
    pub erl_rms_db: f64,
    pub phase_index: usize,
}

/// Build the ERL-only envelope only from a validated branch payload.
pub fn erl_only_envelope_v1(
    metrics: &ErlOnlyMetricsV1,
) -> Result<ComRunResultEnvelopeV1, &'static str> {
    if [metrics.erl_db, metrics.erl11_db, metrics.erl_rms_db]
        .iter()
        .any(|value| value.is_nan())
    {
        return Err("ERL-only metrics cannot contain NaN");
    }
    Ok(ComRunResultEnvelopeV1 {
        schema: COM_RUN_RESULT_SCHEMA_V1,
        policy: COM_RUN_EXECUTION_POLICY_V1,
        admitted: true,
        com_db: None,
        vec_db: None,
        veo_mv: None,
        sigma_n_v: None,
        available_signal_v: None,
        interference_noise_v: None,
        threshold_der: None,
        eye_opening_v: None,
        thru_selected_phase: None,
        fext_selected_phases: Vec::new(),
        next_selected_phases: Vec::new(),
        invalid_reason: None,
    })
}

impl ComRunResultEnvelopeV1 {
    pub const fn schema(&self) -> &'static str {
        self.schema
    }
    pub const fn policy(&self) -> &'static str {
        self.policy
    }
    pub const fn admitted(&self) -> bool {
        self.admitted
    }
    pub const fn com_db(&self) -> Option<f64> {
        self.com_db
    }
    pub const fn vec_db(&self) -> Option<f64> {
        self.vec_db
    }
    pub const fn veo_mv(&self) -> Option<f64> {
        self.veo_mv
    }
    pub const fn sigma_n_v(&self) -> Option<f64> {
        self.sigma_n_v
    }

    pub const fn available_signal_v(&self) -> Option<f64> {
        self.available_signal_v
    }

    pub const fn interference_noise_v(&self) -> Option<f64> {
        self.interference_noise_v
    }

    pub const fn threshold_der(&self) -> Option<f64> {
        self.threshold_der
    }

    pub const fn eye_opening_v(&self) -> Option<f64> {
        self.eye_opening_v
    }
    pub const fn thru_selected_phase(&self) -> Option<i64> {
        self.thru_selected_phase
    }
    pub fn fext_selected_phases(&self) -> &[i64] {
        &self.fext_selected_phases
    }
    pub fn next_selected_phases(&self) -> &[i64] {
        &self.next_selected_phases
    }
    pub fn invalid_reason(&self) -> Option<&str> {
        self.invalid_reason.as_deref()
    }
}

/// Executes a COM run request against a pulse response and COM parameters DTO.
pub fn execute_com_run_v1(
    request_bytes: &[u8],
    pulse_response: &[f64],
    dto: &ComParametersV1,
) -> Result<ComRunResultEnvelopeV1, ComRunExecutionErrorV1> {
    execute_com_run_with_crosstalk_v1(request_bytes, pulse_response, &[], &[], dto)
}

/// Execute an admitted COM request with already-resolved FEXT/NEXT pulse
/// responses. Each crosstalk input is carried into the residual-PDF and
/// combined-noise stages; no S-parameter fitting or channel inference occurs
/// in this entry point.
pub fn execute_com_run_with_crosstalk_v1(
    request_bytes: &[u8],
    pulse_response: &[f64],
    fext_pulses: &[&[f64]],
    next_pulses: &[&[f64]],
    dto: &ComParametersV1,
) -> Result<ComRunResultEnvelopeV1, ComRunExecutionErrorV1> {
    execute_com_run_with_context_v1(
        request_bytes,
        pulse_response,
        fext_pulses,
        next_pulses,
        dto,
        None,
    )
}

/// Execute an admitted request from the opaque V2 search winner.
pub fn execute_com_run_with_search_result_v2(
    request_bytes: &[u8],
    fext_pulses: &[&[f64]],
    next_pulses: &[&[f64]],
    dto: &ComParametersV1,
    winner: &SearchLoopResultWithWinnerV2,
) -> Result<ComRunResultEnvelopeV1, ComRunExecutionErrorV1> {
    let pulse_response = winner.final_pulse();
    execute_com_run_with_context_v1(
        request_bytes,
        pulse_response,
        fext_pulses,
        next_pulses,
        dto,
        Some(winner.winner()),
    )
}

fn execute_com_run_with_context_v1(
    request_bytes: &[u8],
    pulse_response: &[f64],
    fext_pulses: &[&[f64]],
    next_pulses: &[&[f64]],
    dto: &ComParametersV1,
    winner: Option<&ComWinnerContextV1>,
) -> Result<ComRunResultEnvelopeV1, ComRunExecutionErrorV1> {
    let admission = match com_run_admission_v1(request_bytes) {
        Ok(adm) => adm,
        Err(err) => {
            return Ok(ComRunResultEnvelopeV1 {
                schema: COM_RUN_RESULT_SCHEMA_V1,
                policy: COM_RUN_EXECUTION_POLICY_V1,
                admitted: false,
                com_db: None,
                vec_db: None,
                veo_mv: None,
                sigma_n_v: None,
                available_signal_v: None,
                interference_noise_v: None,
                threshold_der: None,
                eye_opening_v: None,
                thru_selected_phase: None,
                fext_selected_phases: Vec::new(),
                next_selected_phases: Vec::new(),
                invalid_reason: Some(legacy_v1_admission_error_code(&err).to_owned()),
            });
        }
    };
    if !admission.admitted() {
        return Ok(ComRunResultEnvelopeV1 {
            schema: COM_RUN_RESULT_SCHEMA_V1,
            policy: COM_RUN_EXECUTION_POLICY_V1,
            admitted: false,
            com_db: None,
            vec_db: None,
            veo_mv: None,
            sigma_n_v: None,
            available_signal_v: None,
            interference_noise_v: None,
            threshold_der: None,
            eye_opening_v: None,
            thru_selected_phase: None,
            fext_selected_phases: Vec::new(),
            next_selected_phases: Vec::new(),
            invalid_reason: admission.invalid_reason().map(|s| s.to_string()),
        });
    }

    let controls = resolve_com_parameter_controls_v1(dto)?;
    let report = if let Some(winner) = winner {
        run_com_chain_with_winner_v1(pulse_response, fext_pulses, next_pulses, &controls, winner)?
    } else {
        run_com_chain_with_crosstalk_v1(pulse_response, fext_pulses, next_pulses, &controls)?
    };

    Ok(ComRunResultEnvelopeV1 {
        schema: COM_RUN_RESULT_SCHEMA_V1,
        policy: COM_RUN_EXECUTION_POLICY_V1,
        admitted: true,
        com_db: Some(report.metrics().com_db()),
        vec_db: Some(report.metrics().vec_db()),
        veo_mv: Some(report.metrics().veo_mv()),
        sigma_n_v: Some(winner.map_or_else(
            || report.noise().sigma_gaussian_v(),
            |winner| winner.sigma_n_v,
        )),
        available_signal_v: Some(report.metrics().available_signal_v()),
        interference_noise_v: Some(report.metrics().interference_noise_v()),
        threshold_der: Some(report.metrics().threshold_der()),
        eye_opening_v: report.metrics().eye_opening_v(),
        thru_selected_phase: Some(report.residual().selected_phase()),
        fext_selected_phases: report
            .fext()
            .iter()
            .map(|value| value.selected_phase())
            .collect(),
        next_selected_phases: report
            .next()
            .iter()
            .map(|value| value.selected_phase())
            .collect(),
        invalid_reason: None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::com_parameters_v1::merge_com_parameters_v1;
    use crate::value_consumption_v1::ResolvedDefaultV1;
    use std::collections::BTreeMap;

    fn pulse64() -> Vec<f64> {
        (0..64)
            .map(|index| {
                let i = index as f64;
                0.5 * (-(i - 28.0) * (i - 28.0) / 80.0).exp() * (i - 28.0) * 0.4
                    + 0.002 * (i * 0.9).sin()
            })
            .collect()
    }

    fn sample_dto() -> ComParametersV1 {
        let mut map = BTreeMap::new();
        map.insert("samples_per_ui".to_string(), ResolvedDefaultV1::Scalar(8.0));
        map.insert("LEVELS".to_string(), ResolvedDefaultV1::Scalar(4.0));
        map.insert("bin_size".to_string(), ResolvedDefaultV1::Scalar(0.01));
        map.insert("A_v".to_string(), ResolvedDefaultV1::Scalar(0.5));
        map.insert("R_LM".to_string(), ResolvedDefaultV1::Scalar(50.0));
        map.insert("SNR_TX".to_string(), ResolvedDefaultV1::Scalar(30.0));
        map.insert("sigma_X".to_string(), ResolvedDefaultV1::Scalar(0.03));
        map.insert("sigma_RJ".to_string(), ResolvedDefaultV1::Scalar(1e-4));
        map.insert(
            "h_J".to_string(),
            ResolvedDefaultV1::Vector(vec![0.3, 0.5, 0.2]),
        );
        map.insert("sigma_N".to_string(), ResolvedDefaultV1::Scalar(0.01));
        map.insert("A_DD".to_string(), ResolvedDefaultV1::Scalar(0.4));
        map.insert("spec_ber".to_string(), ResolvedDefaultV1::Scalar(1e-4));
        let keys: Vec<String> = map.keys().cloned().collect();
        merge_com_parameters_v1(&keys, &map, &BTreeMap::new(), &[]).expect("dto")
    }

    fn valid_request_json() -> Vec<u8> {
        serde_json::json!({
            "schema": "sipi.com.run-request.v1",
            "artifact_root": "/artifacts",
            "artifact_id": "art-001",
            "params": {
                "A_v": 0.5
            }
        })
        .to_string()
        .into_bytes()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            COM_RUN_EXECUTION_POLICY_V1,
            "sipi.p5-08b.com-run-execution-v1.admission-to-result"
        );
        assert_eq!(COM_RUN_RESULT_SCHEMA_V1, "sipi.com.run-result.v1");
    }

    #[test]
    fn erl_only_envelope_requires_typed_non_nan_payload() {
        let valid = ErlOnlyMetricsV1 {
            erl_db: f64::INFINITY,
            erl11_db: f64::INFINITY,
            erl_rms_db: 23.0,
            phase_index: 2,
        };
        let envelope = erl_only_envelope_v1(&valid).expect("validated ERL payload");
        assert!(envelope.admitted());
        assert!(envelope.available_signal_v().is_none());
        let invalid = ErlOnlyMetricsV1 {
            erl_db: f64::NAN,
            ..valid
        };
        assert_eq!(
            erl_only_envelope_v1(&invalid),
            Err("ERL-only metrics cannot contain NaN")
        );
    }

    #[test]
    fn executes_admitted_request_and_emits_result() {
        let req = valid_request_json();
        let pulse = pulse64();
        let dto = sample_dto();
        let env = execute_com_run_v1(&req, &pulse, &dto).expect("exec");
        assert!(env.admitted());
        assert_eq!(env.schema(), COM_RUN_RESULT_SCHEMA_V1);
        assert_eq!(env.policy(), COM_RUN_EXECUTION_POLICY_V1);
        assert!(env.com_db().is_some());
        assert!(env.vec_db().is_some());
        assert!(env.veo_mv().is_some());
        assert!(env.sigma_n_v().is_some());
        assert!(env.available_signal_v().is_some());
        assert!(env.interference_noise_v().is_some());
        assert!(env.threshold_der().is_some());
        assert_eq!(env.invalid_reason(), None);
    }

    #[test]
    fn returns_unadmitted_result_for_invalid_schema() {
        let req = serde_json::json!({
            "schema": "invalid.schema",
            "artifact_root": "/artifacts",
            "artifact_id": "art-001",
            "params": {"A_v": 0.5}
        })
        .to_string()
        .into_bytes();
        let env = execute_com_run_v1(&req, &pulse64(), &sample_dto()).expect("exec");
        assert!(!env.admitted());
        assert_eq!(env.invalid_reason(), Some("SchemaMismatch"));
    }

    #[test]
    fn returns_stable_reason_for_invalid_json() {
        let env = execute_com_run_v1(b"not-json", &pulse64(), &sample_dto()).expect("exec");
        assert!(!env.admitted());
        assert_eq!(env.invalid_reason(), Some("InvalidJson"));
    }

    #[test]
    fn legacy_v1_error_codes_are_exhaustive_and_stable() {
        let cases = [
            (ComRunAdmissionErrorV1::InvalidJson, "InvalidJson"),
            (ComRunAdmissionErrorV1::SchemaMismatch, "SchemaMismatch"),
            (
                ComRunAdmissionErrorV1::MissingArtifactRoot,
                "MissingArtifactRoot",
            ),
            (
                ComRunAdmissionErrorV1::MissingArtifactId,
                "MissingArtifactId",
            ),
            (ComRunAdmissionErrorV1::EmptyParams, "EmptyParams"),
            (ComRunAdmissionErrorV1::NonScalarParam, "NonScalarParam"),
        ];
        for (error, expected) in cases {
            assert_eq!(legacy_v1_admission_error_code(&error), expected);
        }
    }

    #[test]
    fn returns_unadmitted_result_for_empty_artifact_id() {
        let req = serde_json::json!({
            "schema": "sipi.com.run-request.v1",
            "artifact_root": "/artifacts",
            "artifact_id": "",
            "params": {"A_v": 0.5}
        })
        .to_string()
        .into_bytes();
        let env = execute_com_run_v1(&req, &pulse64(), &sample_dto()).expect("exec");
        assert!(!env.admitted());
        assert!(env.invalid_reason().is_some());
    }

    #[test]
    fn rejects_empty_pulse_on_admitted_request() {
        let req = valid_request_json();
        let dto = sample_dto();
        assert_eq!(
            execute_com_run_v1(&req, &[], &dto),
            Err(ComRunExecutionErrorV1::Chain(ComChainErrorV1::EmptyPulse))
        );
    }

    #[test]
    fn crosstalk_execution_reaches_metric_payload() {
        let request = valid_request_json();
        let pulse = pulse64();
        let fext = pulse.iter().map(|value| value * 0.2).collect::<Vec<_>>();
        let next = pulse.iter().map(|value| value * 0.1).collect::<Vec<_>>();
        let baseline = execute_com_run_v1(&request, &pulse, &sample_dto()).expect("baseline");
        let with_crosstalk = execute_com_run_with_crosstalk_v1(
            &request,
            &pulse,
            &[fext.as_slice()],
            &[next.as_slice()],
            &sample_dto(),
        )
        .expect("crosstalk");
        assert!(
            with_crosstalk.com_db() != baseline.com_db()
                || with_crosstalk.vec_db() != baseline.vec_db()
        );
    }

    #[test]
    fn rejects_invalid_dto_on_admitted_request() {
        let _req = valid_request_json();
        let _pulse = pulse64();
        let empty_dto =
            merge_com_parameters_v1(&["x".to_string()], &BTreeMap::new(), &BTreeMap::new(), &[])
                .unwrap_err();
        let _ = empty_dto;
    }
}
