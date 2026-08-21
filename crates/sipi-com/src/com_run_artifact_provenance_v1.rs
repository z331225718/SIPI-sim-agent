//! Bounded artifact binding and integrity projection for `sipi com run`.
//!
//! The legacy COM run request/result wire remains unchanged. This module only
//! adds a request-side helper that validates the existing `artifact_root` and
//! `artifact_id` bindings, then delegates to the product-owned bounded
//! metadata report reader. It does not execute COM, select a profile, return
//! payload bytes to the COM pipeline, or claim MATLAB/oracle provenance. The
//! delegated report reader may boundedly hash payload files for integrity. Its
//! local v1 store assumes no hostile concurrent writers and supplies no
//! ownership, signature, or external-origin proof.

use sipi_artifacts::{ArtifactError, ArtifactReportPolicyV1, ArtifactReportV1, ArtifactRoot};

use crate::com_run_admission_v1::COM_RUN_REQUEST_SCHEMA_V1;

/// Scope policy for the bounded local artifact projection.
pub const COM_RUN_ARTIFACT_PROVENANCE_POLICY_V1: &str =
    "sipi.p5-08d.com-run-artifact-provenance-v1.bounded";

/// Maximum request bytes parsed by this bounded helper.
pub const COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1: usize = 65_536;
/// Exact metadata-report budgets inherited from the product report-inspect
/// policy. These are I/O budgets, not COM metric tolerances.
pub const COM_RUN_ARTIFACT_MAX_MANIFEST_BYTES_V1: u64 = 65_536;
pub const COM_RUN_ARTIFACT_MAX_ENTRY_COUNT_V1: usize = 64;
pub const COM_RUN_ARTIFACT_MAX_TOTAL_PAYLOAD_BYTES_V1: u64 = 16 * 1024 * 1024;
pub const COM_RUN_ARTIFACT_MAX_REPORT_BYTES_V1: usize = 16_384;

/// A validated root/id pair from the existing COM run request.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComRunArtifactBindingV1 {
    artifact_root: String,
    artifact_id: String,
}

impl ComRunArtifactBindingV1 {
    pub fn artifact_root(&self) -> &str {
        &self.artifact_root
    }

    pub fn artifact_id(&self) -> &str {
        &self.artifact_id
    }
}

/// Fail-closed errors for binding validation and bounded report inspection.
#[derive(Debug)]
pub enum ComRunArtifactProvenanceErrorV1 {
    RequestTooLarge,
    InvalidJson,
    SchemaMismatch,
    MissingArtifactRoot,
    InvalidArtifactRoot,
    MissingArtifactId,
    InvalidArtifactId,
    Artifact(ArtifactError),
}

impl ComRunArtifactProvenanceErrorV1 {
    /// Stable diagnostic labels for local logs/tests. These are not added to
    /// the legacy `sipi.com.run-result.v1` wire.
    pub const fn code(&self) -> &'static str {
        match self {
            Self::RequestTooLarge => "request_too_large",
            Self::InvalidJson => "invalid_json",
            Self::SchemaMismatch => "schema_mismatch",
            Self::MissingArtifactRoot => "missing_artifact_root",
            Self::InvalidArtifactRoot => "invalid_artifact_root",
            Self::MissingArtifactId => "missing_artifact_id",
            Self::InvalidArtifactId => "invalid_artifact_id",
            Self::Artifact(_) => "artifact_not_verified",
        }
    }
}

/// A bounded, metadata-only projection of one local COM run artifact.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ComRunArtifactProvenanceV1 {
    binding: ComRunArtifactBindingV1,
    report: ArtifactReportV1,
}

impl ComRunArtifactProvenanceV1 {
    pub fn binding(&self) -> &ComRunArtifactBindingV1 {
        &self.binding
    }

    pub fn report(&self) -> &ArtifactReportV1 {
        &self.report
    }
}

/// Parses and validates only the existing COM run artifact binding fields.
///
/// This performs no filesystem access. Unknown COM request fields are left to
/// the legacy admission path so this helper cannot silently tighten v1 wire
/// behavior.
pub fn parse_com_run_artifact_binding_v1(
    request_bytes: &[u8],
) -> Result<ComRunArtifactBindingV1, ComRunArtifactProvenanceErrorV1> {
    if request_bytes.len() > COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 {
        return Err(ComRunArtifactProvenanceErrorV1::RequestTooLarge);
    }
    let value: serde_json::Value = serde_json::from_slice(request_bytes)
        .map_err(|_| ComRunArtifactProvenanceErrorV1::InvalidJson)?;
    let object = value
        .as_object()
        .ok_or(ComRunArtifactProvenanceErrorV1::InvalidJson)?;
    match object.get("schema").and_then(serde_json::Value::as_str) {
        Some(schema) if schema == COM_RUN_REQUEST_SCHEMA_V1 => {}
        Some(_) => return Err(ComRunArtifactProvenanceErrorV1::SchemaMismatch),
        None => return Err(ComRunArtifactProvenanceErrorV1::InvalidJson),
    }

    let artifact_root = match object.get("artifact_root") {
        None => return Err(ComRunArtifactProvenanceErrorV1::MissingArtifactRoot),
        Some(value) => value
            .as_str()
            .ok_or(ComRunArtifactProvenanceErrorV1::InvalidArtifactRoot)?,
    };
    if !valid_artifact_root(artifact_root) {
        return Err(ComRunArtifactProvenanceErrorV1::InvalidArtifactRoot);
    }

    let artifact_id = match object.get("artifact_id") {
        None => return Err(ComRunArtifactProvenanceErrorV1::MissingArtifactId),
        Some(value) => value
            .as_str()
            .ok_or(ComRunArtifactProvenanceErrorV1::InvalidArtifactId)?,
    };
    if !valid_artifact_id(artifact_id) {
        return Err(ComRunArtifactProvenanceErrorV1::InvalidArtifactId);
    }

    Ok(ComRunArtifactBindingV1 {
        artifact_root: artifact_root.to_owned(),
        artifact_id: artifact_id.to_owned(),
    })
}

/// Verifies one bound local artifact and returns only the bounded metadata
/// report. No COM execution or payload bytes cross this API; the delegated
/// verifier may read bounded payload files only to recompute their hashes.
pub fn inspect_com_run_artifact_provenance_v1(
    request_bytes: &[u8],
) -> Result<ComRunArtifactProvenanceV1, ComRunArtifactProvenanceErrorV1> {
    let binding = parse_com_run_artifact_binding_v1(request_bytes)?;
    let root = ArtifactRoot::open_existing(binding.artifact_root())
        .map_err(ComRunArtifactProvenanceErrorV1::Artifact)?;
    let policy = ArtifactReportPolicyV1::try_new(
        COM_RUN_ARTIFACT_MAX_MANIFEST_BYTES_V1,
        COM_RUN_ARTIFACT_MAX_ENTRY_COUNT_V1,
        COM_RUN_ARTIFACT_MAX_TOTAL_PAYLOAD_BYTES_V1,
        COM_RUN_ARTIFACT_MAX_REPORT_BYTES_V1,
    )
    .map_err(ComRunArtifactProvenanceErrorV1::Artifact)?;
    let report = root
        .inspect_verified_v1(binding.artifact_id(), policy)
        .map_err(ComRunArtifactProvenanceErrorV1::Artifact)?;
    Ok(ComRunArtifactProvenanceV1 { binding, report })
}

fn valid_artifact_root(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 4096
        && !value.contains('\0')
        && !value.contains("://")
        && !value
            .split(['/', '\\'])
            .any(|segment| matches!(segment, "." | ".."))
}

fn valid_artifact_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_ROOT: AtomicUsize = AtomicUsize::new(0);

    fn root() -> std::path::PathBuf {
        let nonce = NEXT_ROOT.fetch_add(1, Ordering::Relaxed);
        std::env::temp_dir().join(format!(
            "sipi-com-provenance-{}-{nonce}",
            std::process::id()
        ))
    }

    fn request(root: &str, id: &str) -> Vec<u8> {
        serde_json::json!({
            "schema": COM_RUN_REQUEST_SCHEMA_V1,
            "artifact_root": root,
            "artifact_id": id,
            "params": {"A_v": 0.5}
        })
        .to_string()
        .into_bytes()
    }

    fn sha256(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    #[test]
    fn parses_binding_without_touching_filesystem() {
        let binding = parse_com_run_artifact_binding_v1(&request("missing-root", "result-1"))
            .expect("binding");
        assert_eq!(binding.artifact_root(), "missing-root");
        assert_eq!(binding.artifact_id(), "result-1");
    }

    #[test]
    fn rejects_unbounded_or_unsafe_bindings() {
        assert_eq!(
            parse_com_run_artifact_binding_v1(&vec![
                b' ';
                COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 + 1
            ])
            .err()
            .map(|error| error.code()),
            Some("request_too_large")
        );
        for root in [
            "https://example.invalid",
            "../outside",
            "root/./nested",
            "root/../nested",
        ] {
            assert_eq!(
                parse_com_run_artifact_binding_v1(&request(root, "result-1"))
                    .err()
                    .map(|error| error.code()),
                Some("invalid_artifact_root"),
                "root={root}"
            );
        }
        for id in ["../result", "result:name", ""] {
            assert_eq!(
                parse_com_run_artifact_binding_v1(&request("root", id))
                    .err()
                    .map(|error| error.code()),
                Some("invalid_artifact_id"),
                "id={id}"
            );
        }
    }

    #[test]
    fn reports_only_bounded_verified_metadata() {
        let root = root();
        let store = ArtifactRoot::open_or_create(&root).expect("root");
        let mut stage = store.begin("result-1").expect("stage");
        stage
            .stage_reader("report.json", &b"bounded-report"[..], 128)
            .expect("payload");
        stage.seal().expect("seal").publish_new().expect("publish");

        let request = request(&root.to_string_lossy(), "result-1");
        let result = inspect_com_run_artifact_provenance_v1(&request).expect("report");
        assert_eq!(result.binding().artifact_id(), "result-1");
        assert!(result.report().verified);
        assert_eq!(result.report().entry_count, 1);
        assert_eq!(result.report().total_payload_bytes, 14);
        assert_eq!(result.report().entry_content_sha256.len(), 1);
        assert_eq!(
            result.report().entry_content_sha256[0],
            "23bd670b3ff114c2eeec2ce27fd6def314530f33f6a46b2c4fb05964628bba9b"
        );
        assert_eq!(
            result.report().manifest_sha256,
            "dc44cc8d5ded60f3cbcf4c1b85c57fdc3e6d0b902cc5569e4a91d11f48c7d89c"
        );
        let report_bytes = serde_json::to_vec(result.report()).expect("report json");
        assert_eq!(
            sha256(&report_bytes),
            "2422c29429d48db15cf3ddb6dbba681457a367cb0c21dc0e0bb43ed2407f96f0"
        );
        assert_eq!(result.report().integrity_lineage, "unavailable");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_missing_or_tampered_artifact_without_claiming_provenance() {
        let missing = inspect_com_run_artifact_provenance_v1(&request("missing-root", "result-1"));
        assert!(matches!(
            missing,
            Err(ComRunArtifactProvenanceErrorV1::Artifact(_))
        ));

        let root = root();
        let store = ArtifactRoot::open_or_create(&root).expect("root");
        let mut stage = store.begin("result-1").expect("stage");
        stage
            .stage_reader("report.json", &b"bounded-report"[..], 128)
            .expect("payload");
        stage.seal().expect("seal").publish_new().expect("publish");
        std::fs::write(root.join("result-1").join("report.json"), b"tampered")
            .expect("tamper fixture");
        let result =
            inspect_com_run_artifact_provenance_v1(&request(&root.to_string_lossy(), "result-1"));
        assert!(matches!(
            result,
            Err(ComRunArtifactProvenanceErrorV1::Artifact(_))
        ));
        let _ = std::fs::remove_dir_all(root);
    }
}
