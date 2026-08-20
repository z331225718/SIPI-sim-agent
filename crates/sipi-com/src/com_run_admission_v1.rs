//! COM run-request admission preflight core (P5-08a).
//!
//! A request-side gate for the (currently non-admitted) "sipi com run"
//! route. It validates the structural contract of a "sipi.com.run-request.v1"
//! request WITHOUT invoking any COM computation, conformance admission, or
//! artifact consumption: the schema id must match, the artifact root and id
//! caller bindings must be non-empty, and the params object must carry at
//! least one consumed scalar key. Fail-closed: any structural violation
//! yields a not-admitted verdict with a stable reason; nothing is guessed.
//!
//! This does NOT run COM, does not select a profile, and does not invoke the
//! conformance pipeline. It is the admission surface a later "sipi com run"
//! integration will call, delivered as the minimal P5-08 slice the owner
//! authorized (owner-decision-checklist P5-08: integrate in smaller slices).

/// Stable scope policy of the P5-08a COM run-request admission core.
pub const COM_RUN_ADMISSION_POLICY_V1: &str = "sipi.p5-08a.com-run-request.v1.admission";

/// The canonical "sipi com run" request schema id.
pub const COM_RUN_REQUEST_SCHEMA_V1: &str = "sipi.com.run-request.v1";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ComRunAdmissionErrorV1 {
    InvalidJson,
    SchemaMismatch,
    MissingArtifactRoot,
    MissingArtifactId,
    EmptyParams,
    NonScalarParam,
}

/// The deterministic admission verdict for a "sipi com run" request.
#[derive(Clone, Debug, PartialEq)]
pub struct ComRunAdmissionV1 {
    admitted: bool,
    schema_matched: bool,
    artifact_bound: bool,
    consumed_key_count: usize,
    invalid_reason: Option<String>,
}

impl ComRunAdmissionV1 {
    pub const fn admitted(&self) -> bool {
        self.admitted
    }
    pub const fn schema_matched(&self) -> bool {
        self.schema_matched
    }
    pub const fn artifact_bound(&self) -> bool {
        self.artifact_bound
    }
    pub const fn consumed_key_count(&self) -> usize {
        self.consumed_key_count
    }
    pub fn invalid_reason(&self) -> Option<&str> {
        self.invalid_reason.as_deref()
    }
}

/// Validates the structural contract of a COM run request.
///
/// `request_bytes` is UTF-8 JSON with fields "schema", "artifact_root",
/// "artifact_id", and "params" (an object of scalar values). A request is
/// admitted only if the schema id matches, both artifact bindings are
/// non-empty, and params has at least one scalar entry. No COM is executed.
pub fn com_run_admission_v1(
    request_bytes: &[u8],
) -> Result<ComRunAdmissionV1, ComRunAdmissionErrorV1> {
    let value: serde_json::Value =
        serde_json::from_slice(request_bytes).map_err(|_| ComRunAdmissionErrorV1::InvalidJson)?;
    let obj = match value.as_object() {
        Some(obj) => obj,
        None => return Err(ComRunAdmissionErrorV1::InvalidJson),
    };
    let schema = match obj.get("schema").and_then(|v| v.as_str()) {
        Some(s) => s,
        None => return Err(ComRunAdmissionErrorV1::InvalidJson),
    };
    if schema != COM_RUN_REQUEST_SCHEMA_V1 {
        return Err(ComRunAdmissionErrorV1::SchemaMismatch);
    }
    let root = obj
        .get("artifact_root")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let id = obj
        .get("artifact_id")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let bound = !root.is_empty() && !id.is_empty();
    let params = match obj.get("params") {
        Some(v) => v.as_object().ok_or(ComRunAdmissionErrorV1::InvalidJson)?,
        None => return Ok(not_admitted(true, bound, 0, "missing_params")),
    };
    if !params.is_empty() {
        for (_key, value) in params {
            if !value.is_number() && !value.is_boolean() && !value.is_string() {
                return Err(ComRunAdmissionErrorV1::NonScalarParam);
            }
        }
    }
    let consumed = params.len();
    if consumed == 0 {
        return Ok(not_admitted(true, bound, 0, "empty_params"));
    }
    if !bound {
        return Ok(not_admitted(true, false, consumed, "unbound_artifacts"));
    }
    Ok(ComRunAdmissionV1 {
        admitted: true,
        schema_matched: true,
        artifact_bound: true,
        consumed_key_count: consumed,
        invalid_reason: None,
    })
}

fn not_admitted(
    schema_matched: bool,
    artifact_bound: bool,
    consumed: usize,
    reason: &str,
) -> ComRunAdmissionV1 {
    ComRunAdmissionV1 {
        admitted: false,
        schema_matched,
        artifact_bound,
        consumed_key_count: consumed,
        invalid_reason: Some(reason.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(fields: &str) -> Vec<u8> {
        // Build a JSON object with the given inner fields.
        format!("{{{fields}}}").into_bytes()
    }

    fn valid_params() -> String {
        "\"params\":{\"fb\":53.125e9,\"a_fext\":0.5}".to_string()
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            COM_RUN_ADMISSION_POLICY_V1,
            "sipi.p5-08a.com-run-request.v1.admission"
        );
        assert_eq!(COM_RUN_REQUEST_SCHEMA_V1, "sipi.com.run-request.v1");
    }

    #[test]
    fn admits_valid_request() {
        let body = format!(
            "\"schema\":\"sipi.com.run-request.v1\",\"artifact_root\":\"r\",\"artifact_id\":\"a\",{}",
            valid_params()
        );
        let adm = com_run_admission_v1(&request(&body)).expect("ok");
        assert!(adm.admitted());
        assert!(adm.schema_matched());
        assert!(adm.artifact_bound());
        assert_eq!(adm.consumed_key_count(), 2);
        assert!(adm.invalid_reason().is_none());
    }

    #[test]
    fn rejects_schema_mismatch() {
        let body = format!(
            "\"schema\":\"sipi.wrong\",\"artifact_root\":\"r\",\"artifact_id\":\"a\",{}",
            valid_params()
        );
        assert_eq!(
            com_run_admission_v1(&request(&body)).err(),
            Some(ComRunAdmissionErrorV1::SchemaMismatch)
        );
    }

    #[test]
    fn rejects_missing_artifacts() {
        let body = format!("\"schema\":\"sipi.com.run-request.v1\",{}", valid_params());
        let adm = com_run_admission_v1(&request(&body)).expect("ok");
        assert!(!adm.admitted());
        assert_eq!(adm.invalid_reason(), Some("unbound_artifacts"));
    }

    #[test]
    fn rejects_empty_params() {
        let body = "\"schema\":\"sipi.com.run-request.v1\",\"artifact_root\":\"r\",\"artifact_id\":\"a\",\"params\":{}";
        let adm = com_run_admission_v1(&request(body)).expect("ok");
        assert!(!adm.admitted());
        assert_eq!(adm.invalid_reason(), Some("empty_params"));
    }

    #[test]
    fn rejects_missing_params() {
        let body =
            "\"schema\":\"sipi.com.run-request.v1\",\"artifact_root\":\"r\",\"artifact_id\":\"a\"";
        let adm = com_run_admission_v1(&request(body)).expect("ok");
        assert!(!adm.admitted());
        assert_eq!(adm.invalid_reason(), Some("missing_params"));
    }

    #[test]
    fn rejects_invalid_json() {
        assert_eq!(
            com_run_admission_v1(b"not-json").err(),
            Some(ComRunAdmissionErrorV1::InvalidJson)
        );
    }

    #[test]
    fn rejects_nested_non_scalar_param() {
        let body = "\"schema\":\"sipi.com.run-request.v1\",\"artifact_root\":\"r\",\"artifact_id\":\"a\",\"params\":{\"k\":{\"nested\":1}}";
        assert_eq!(
            com_run_admission_v1(&request(body)).err(),
            Some(ComRunAdmissionErrorV1::NonScalarParam)
        );
    }
}
