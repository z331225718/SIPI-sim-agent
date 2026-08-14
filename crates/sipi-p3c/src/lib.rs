#![forbid(unsafe_code)]

//! Fixed-profile sealed S4P intake for the selected P3C static bench.
//!
//! The caller selects only an already-published artifact identity. This crate
//! owns neither generic artifact semantics nor Touchstone lexical parsing.

use std::{error::Error, fmt, num::NonZeroUsize};

use sha2::{Digest, Sha256};
use sipi_artifacts::{ArtifactError, ArtifactRoot, VerifiedConsumptionPolicyV1};
use sipi_channel::{
    FixedFourPortBenchError, SelectedP3cStaticDifferentialTransferV1,
    reduce_selected_p3c_fixed_four_port_bench_v1,
};
use sipi_touchstone::{
    TouchstoneParseLimitsV1, selected_four_port_v1::{
        SelectedFourPortTouchstoneErrorV1, admit_selected_p3c_fixed_four_port_v1,
        parse_selected_four_port_hz_s_ri_50_v1, parse_selected_four_port_hz_s_ri_50_v2,
    },
};

mod p3c_truncation_waveform_sensitivity_v1;
mod prbs9_impulse_candidate_v2;

pub use p3c_truncation_waveform_sensitivity_v1::{
    diagnose_selected_p3c_full_causal_third_period_v1,
    P3C_FULL_CAUSAL_RESPONSE_SAMPLES_V1, P3C_TRUNCATION_SENSITIVITY_MACS_V1,
    P3C_TRUNCATION_SENSITIVITY_SAMPLE_INTERVAL_BITS_V1,
    P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_SAMPLES_V1,
    P3C_TRUNCATION_SENSITIVITY_THIRD_PERIOD_START_V1,
    SelectedP3cFullCausalThirdPeriodDiagnosticV1, TruncationWaveformSensitivityErrorV1,
};

pub const SELECTED_P3C_S4P_FILE_NAME_V1: &str = "channel.s4p";
pub const SELECTED_P3C_S4P_BYTE_LENGTH_V1: u64 = 1_834_156;
pub const SELECTED_P3C_S4P_SHA256_V1: &str = "25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47";
const MAX_MANIFEST_BYTES: u64 = 65_536;
const MAX_LINE_BYTES: usize = 16_384;
const MAX_DATA_RECORDS: usize = 20_000;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SelectedP3cSealedS4pIdentityV1 {
    artifact_id: String,
    manifest_sha256: String,
}

impl SelectedP3cSealedS4pIdentityV1 {
    pub fn try_new(artifact_id: impl Into<String>, manifest_sha256: impl Into<String>) -> Result<Self, SelectedP3cSealedS4pAdmissionErrorV1> {
        let artifact_id = artifact_id.into();
        let manifest_sha256 = manifest_sha256.into();
        if artifact_id.is_empty()
            || artifact_id.len() > 128
            || !artifact_id.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
            || !is_lowercase_sha256(&manifest_sha256)
        {
            return Err(SelectedP3cSealedS4pAdmissionErrorV1::InvalidIdentity);
        }
        Ok(Self { artifact_id, manifest_sha256 })
    }

    pub fn artifact_id(&self) -> &str { &self.artifact_id }
    pub fn manifest_sha256(&self) -> &str { &self.manifest_sha256 }
}

/// The v2 lexical profile intentionally keeps the same opaque caller surface
/// while selecting the separately versioned `R 50`/`R 50.0` parser allowlist.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SelectedP3cSealedS4pIdentityV2 {
    artifact_id: String,
    manifest_sha256: String,
}

impl SelectedP3cSealedS4pIdentityV2 {
    pub fn try_new(artifact_id: impl Into<String>, manifest_sha256: impl Into<String>) -> Result<Self, SelectedP3cSealedS4pAdmissionErrorV2> {
        let artifact_id = artifact_id.into();
        let manifest_sha256 = manifest_sha256.into();
        if artifact_id.is_empty()
            || artifact_id.len() > 128
            || !artifact_id.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
            || !is_lowercase_sha256(&manifest_sha256)
        {
            return Err(SelectedP3cSealedS4pAdmissionErrorV2::InvalidIdentity);
        }
        Ok(Self { artifact_id, manifest_sha256 })
    }

    pub fn artifact_id(&self) -> &str { &self.artifact_id }
    pub fn manifest_sha256(&self) -> &str { &self.manifest_sha256 }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AdmittedSelectedP3cStaticTransferV1 {
    artifact_id: String,
    manifest_sha256: String,
    source_sha256: String,
    source_byte_length: u64,
    record_count: usize,
    transfer: SelectedP3cStaticDifferentialTransferV1,
}

impl AdmittedSelectedP3cStaticTransferV1 {
    pub fn artifact_id(&self) -> &str { &self.artifact_id }
    pub fn manifest_sha256(&self) -> &str { &self.manifest_sha256 }
    pub fn source_sha256(&self) -> &str { &self.source_sha256 }
    pub fn source_byte_length(&self) -> u64 { self.source_byte_length }
    pub fn record_count(&self) -> usize { self.record_count }
    pub fn transfer(&self) -> &SelectedP3cStaticDifferentialTransferV1 { &self.transfer }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AdmittedSelectedP3cStaticTransferV2 {
    artifact_id: String,
    manifest_sha256: String,
    source_sha256: String,
    source_byte_length: u64,
    record_count: usize,
    transfer: SelectedP3cStaticDifferentialTransferV1,
}

impl AdmittedSelectedP3cStaticTransferV2 {
    pub fn artifact_id(&self) -> &str { &self.artifact_id }
    pub fn manifest_sha256(&self) -> &str { &self.manifest_sha256 }
    pub fn source_sha256(&self) -> &str { &self.source_sha256 }
    pub fn source_byte_length(&self) -> u64 { self.source_byte_length }
    pub fn record_count(&self) -> usize { self.record_count }
    pub fn transfer(&self) -> &SelectedP3cStaticDifferentialTransferV1 { &self.transfer }
}

#[derive(Debug)]
pub enum SelectedP3cSealedS4pAdmissionErrorV1 {
    InvalidIdentity,
    Artifact(ArtifactError),
    SourceLengthMismatch,
    SourceHashMismatch,
    Parser(SelectedFourPortTouchstoneErrorV1),
    Reduction(FixedFourPortBenchError),
}

impl fmt::Display for SelectedP3cSealedS4pAdmissionErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "selected P3C sealed S4P admission failed: {self:?}")
    }
}

impl Error for SelectedP3cSealedS4pAdmissionErrorV1 {}

#[derive(Debug)]
pub enum SelectedP3cSealedS4pAdmissionErrorV2 {
    InvalidIdentity,
    Artifact(ArtifactError),
    SourceLengthMismatch,
    SourceHashMismatch,
    Parser(SelectedFourPortTouchstoneErrorV1),
    Reduction(FixedFourPortBenchError),
}

impl fmt::Display for SelectedP3cSealedS4pAdmissionErrorV2 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "selected P3C sealed S4P v2 admission failed: {self:?}")
    }
}

impl Error for SelectedP3cSealedS4pAdmissionErrorV2 {}

fn is_lowercase_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn parser_limits() -> TouchstoneParseLimitsV1 {
    TouchstoneParseLimitsV1::new(
        NonZeroUsize::new(SELECTED_P3C_S4P_BYTE_LENGTH_V1 as usize).expect("selected length is nonzero"),
        NonZeroUsize::new(MAX_LINE_BYTES).expect("nonzero line limit"),
        NonZeroUsize::new(MAX_DATA_RECORDS).expect("nonzero record limit"),
    )
}

fn admit_bytes(
    bytes: &[u8],
    expected_length: u64,
    expected_sha256: &str,
) -> Result<(SelectedP3cStaticDifferentialTransferV1, usize), SelectedP3cSealedS4pAdmissionErrorV1> {
    if bytes.len() as u64 != expected_length {
        return Err(SelectedP3cSealedS4pAdmissionErrorV1::SourceLengthMismatch);
    }
    if sha256(bytes) != expected_sha256 {
        return Err(SelectedP3cSealedS4pAdmissionErrorV1::SourceHashMismatch);
    }
    let parsed = parse_selected_four_port_hz_s_ri_50_v1(bytes, parser_limits())
        .map_err(SelectedP3cSealedS4pAdmissionErrorV1::Parser)?;
    let record_count = parsed.rows().len();
    let spectrum = admit_selected_p3c_fixed_four_port_v1(&parsed)
        .map_err(SelectedP3cSealedS4pAdmissionErrorV1::Parser)?;
    let transfer = reduce_selected_p3c_fixed_four_port_bench_v1(&spectrum)
        .map_err(SelectedP3cSealedS4pAdmissionErrorV1::Reduction)?;
    Ok((transfer, record_count))
}

fn admit_bytes_v2(
    bytes: &[u8],
) -> Result<(SelectedP3cStaticDifferentialTransferV1, usize), SelectedP3cSealedS4pAdmissionErrorV2> {
    if bytes.len() as u64 != SELECTED_P3C_S4P_BYTE_LENGTH_V1 {
        return Err(SelectedP3cSealedS4pAdmissionErrorV2::SourceLengthMismatch);
    }
    if sha256(bytes) != SELECTED_P3C_S4P_SHA256_V1 {
        return Err(SelectedP3cSealedS4pAdmissionErrorV2::SourceHashMismatch);
    }
    let parsed = parse_selected_four_port_hz_s_ri_50_v2(bytes, parser_limits())
        .map_err(SelectedP3cSealedS4pAdmissionErrorV2::Parser)?;
    let record_count = parsed.rows().len();
    let spectrum = admit_selected_p3c_fixed_four_port_v1(&parsed)
        .map_err(SelectedP3cSealedS4pAdmissionErrorV2::Parser)?;
    let transfer = reduce_selected_p3c_fixed_four_port_bench_v1(&spectrum)
        .map_err(SelectedP3cSealedS4pAdmissionErrorV2::Reduction)?;
    Ok((transfer, record_count))
}

/// Consume the one exact selected S4P from a caller-selected SIPI published
/// root. The root retains `ArtifactRoot` v1's no-hostile-concurrent-writer
/// assumption; this is local integrity admission, not a hostile-filesystem
/// boundary or a waveform execution route.
pub fn admit_selected_p3c_sealed_s4p_v1(
    root: &ArtifactRoot,
    identity: &SelectedP3cSealedS4pIdentityV1,
) -> Result<AdmittedSelectedP3cStaticTransferV1, SelectedP3cSealedS4pAdmissionErrorV1> {
    let files = root.consume_exact_verified_v1(
        identity.artifact_id(),
        identity.manifest_sha256(),
        &[(SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_BYTE_LENGTH_V1)],
        VerifiedConsumptionPolicyV1::try_new(MAX_MANIFEST_BYTES, SELECTED_P3C_S4P_BYTE_LENGTH_V1)
            .expect("fixed consumption policy is valid"),
    ).map_err(SelectedP3cSealedS4pAdmissionErrorV1::Artifact)?;
    let bytes = files.file(SELECTED_P3C_S4P_FILE_NAME_V1).ok_or(SelectedP3cSealedS4pAdmissionErrorV1::SourceLengthMismatch)?;
    let (transfer, record_count) = admit_bytes(bytes, SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1)?;
    Ok(AdmittedSelectedP3cStaticTransferV1 {
        artifact_id: files.artifact_id().to_owned(),
        manifest_sha256: files.manifest_sha256().to_owned(),
        source_sha256: SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        source_byte_length: SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        record_count,
        transfer,
    })
}

/// Consume the same fixed source through the amended v2 lexical profile. It
/// has no caller-controlled option-line normalization and remains static-only.
pub fn admit_selected_p3c_sealed_s4p_v2(
    root: &ArtifactRoot,
    identity: &SelectedP3cSealedS4pIdentityV2,
) -> Result<AdmittedSelectedP3cStaticTransferV2, SelectedP3cSealedS4pAdmissionErrorV2> {
    let files = root.consume_exact_verified_v1(
        identity.artifact_id(),
        identity.manifest_sha256(),
        &[(SELECTED_P3C_S4P_FILE_NAME_V1, SELECTED_P3C_S4P_BYTE_LENGTH_V1)],
        VerifiedConsumptionPolicyV1::try_new(MAX_MANIFEST_BYTES, SELECTED_P3C_S4P_BYTE_LENGTH_V1)
            .expect("fixed consumption policy is valid"),
    ).map_err(SelectedP3cSealedS4pAdmissionErrorV2::Artifact)?;
    let bytes = files.file(SELECTED_P3C_S4P_FILE_NAME_V1).ok_or(SelectedP3cSealedS4pAdmissionErrorV2::SourceLengthMismatch)?;
    let (transfer, record_count) = admit_bytes_v2(bytes)?;
    Ok(AdmittedSelectedP3cStaticTransferV2 {
        artifact_id: files.artifact_id().to_owned(),
        manifest_sha256: files.manifest_sha256().to_owned(),
        source_sha256: SELECTED_P3C_S4P_SHA256_V1.to_owned(),
        source_byte_length: SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        record_count,
        transfer,
    })
}

#[cfg(test)]
mod tests {
    use std::{fs, time::{SystemTime, UNIX_EPOCH}};

    use super::*;

    fn root(label: &str) -> std::path::PathBuf {
        let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let root = std::env::temp_dir().join(format!("sipi-p3c-{label}-{nonce}"));
        fs::create_dir(&root).unwrap();
        root
    }

    fn synthetic_s4p() -> Vec<u8> {
        let mut values = vec!["0".to_owned()];
        values.extend(std::iter::repeat_n("0".to_owned(), 32));
        format!("# Hz S RI R 50.0\n{}\n1 {}\n", values.join(" "), vec!["0"; 32].join(" ")).into_bytes()
    }

    #[test]
    fn miniature_profile_exercises_exact_seal_parse_and_reduce_chain() {
        let root = root("miniature");
        let payload = synthetic_s4p();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut stage = store.begin("network-1").unwrap();
        stage.stage_reader(SELECTED_P3C_S4P_FILE_NAME_V1, payload.as_slice(), payload.len() as u64).unwrap();
        stage.seal().unwrap().publish_new().unwrap();
        let manifest = fs::read(root.join("network-1").join("success.json")).unwrap();
        let reader = ArtifactRoot::open_existing(&root).unwrap();
        let files = reader.consume_exact_verified_v1(
            "network-1", &sha256(&manifest), &[(SELECTED_P3C_S4P_FILE_NAME_V1, payload.len() as u64)],
            VerifiedConsumptionPolicyV1::try_new(65_536, payload.len() as u64).unwrap(),
        ).unwrap();
        let (transfer, records) = admit_bytes(files.file(SELECTED_P3C_S4P_FILE_NAME_V1).unwrap(), payload.len() as u64, &sha256(&payload)).unwrap();
        assert_eq!(records, 2);
        assert_eq!(transfer.frequencies().len(), 2);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn production_profile_rejects_synthetic_or_mutated_sealed_content() {
        let root = root("reject");
        let payload = synthetic_s4p();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut stage = store.begin("network-1").unwrap();
        stage.stage_reader(SELECTED_P3C_S4P_FILE_NAME_V1, payload.as_slice(), payload.len() as u64).unwrap();
        stage.seal().unwrap().publish_new().unwrap();
        let manifest = sha256(&fs::read(root.join("network-1").join("success.json")).unwrap());
        let reader = ArtifactRoot::open_existing(&root).unwrap();
        let identity = SelectedP3cSealedS4pIdentityV1::try_new("network-1", manifest).unwrap();
        assert!(matches!(admit_selected_p3c_sealed_s4p_v1(&reader, &identity), Err(SelectedP3cSealedS4pAdmissionErrorV1::Artifact(_)) | Err(SelectedP3cSealedS4pAdmissionErrorV1::SourceLengthMismatch)));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn identity_rejects_path_and_hash_override_surfaces() {
        assert!(SelectedP3cSealedS4pIdentityV1::try_new("../network", "0".repeat(64)).is_err());
        assert!(SelectedP3cSealedS4pIdentityV1::try_new("network", "A".repeat(64)).is_err());
        assert!(SelectedP3cSealedS4pIdentityV2::try_new("../network", "0".repeat(64)).is_err());
    }
}
mod prbs9_impulse_candidate_v1;

pub use prbs9_impulse_candidate_v1::{
    generate_selected_p3c_prbs9_impulse_candidate_v1, Prbs9ImpulseCandidateErrorV1,
    SelectedP3cPrbs9ImpulseCandidateV1, P3C_PRBS9_OSR_V1, P3C_PRBS9_PERIOD_SHA256_V1,
    P3C_PRBS9_PERIODS_V1, P3C_PRBS9_PERIOD_UI_V1, P3C_PRBS9_SAMPLE_INTERVAL_BITS_V1,
    P3C_PRBS9_THIRD_PERIOD_START_V1, P3C_PRBS9_TOTAL_SAMPLES_V1,
    P3C_SELECTED_FULL_LINEAR_MACS_V1, P3C_SELECTED_FULL_LINEAR_SAMPLES_V1,
    P3C_SELECTED_TRUNCATED_RESPONSE_SAMPLES_V1,
};
pub use prbs9_impulse_candidate_v2::{
    generate_selected_p3c_prbs9_impulse_candidate_v2, Prbs9ImpulseCandidateErrorV2,
    SelectedP3cPrbs9ImpulseCandidateV2,
};
