#![forbid(unsafe_code)]

//! A local, application-owned primitive for publishing immutable artifacts.
//!
//! Version 1 assumes its root has no hostile concurrent writers. It rejects
//! symlinks it encounters, but does not claim to close filesystem TOCTOU races.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicUsize, Ordering},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const MANIFEST_NAME: &str = "success.json";
const STAGING_NAME: &str = ".staging";
static NEXT_STAGING_NONCE: AtomicUsize = AtomicUsize::new(0);

pub const ARTIFACT_REPORT_SCHEMA_V1: &str = "sipi.artifact-report.v1";

/// Bounds one exact, sealed-artifact payload consumption.
///
/// This is for caller-selected roots which still obey this crate's v1
/// no-hostile-concurrent-writer assumption. It returns owned bytes only after
/// the same read has been checked against the sealed manifest.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct VerifiedConsumptionPolicyV1 {
    maximum_manifest_bytes: u64,
    maximum_total_bytes: u64,
}

impl VerifiedConsumptionPolicyV1 {
    pub fn try_new(
        maximum_manifest_bytes: u64,
        maximum_total_bytes: u64,
    ) -> Result<Self, ArtifactError> {
        if maximum_manifest_bytes == 0 || maximum_total_bytes == 0 {
            return Err(ArtifactError::LimitExceeded);
        }
        Ok(Self {
            maximum_manifest_bytes,
            maximum_total_bytes,
        })
    }
}

/// Owned bytes from one exact sealed-artifact read.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VerifiedFilesV1 {
    artifact_id: String,
    manifest_sha256: String,
    files: BTreeMap<String, Vec<u8>>,
}

impl VerifiedFilesV1 {
    pub fn artifact_id(&self) -> &str {
        &self.artifact_id
    }

    pub fn manifest_sha256(&self) -> &str {
        &self.manifest_sha256
    }

    pub fn file(&self, path: &str) -> Option<&[u8]> {
        self.files.get(path).map(Vec::as_slice)
    }
}

/// Bounds the metadata work accepted by the read-only artifact report path.
///
/// The report does not open payload content for presentation. It reads each
/// payload only to recompute the published integrity digest.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ArtifactReportPolicyV1 {
    maximum_manifest_bytes: u64,
    maximum_entry_count: usize,
    maximum_total_payload_bytes: u64,
    maximum_report_bytes: usize,
}

impl ArtifactReportPolicyV1 {
    pub fn try_new(
        maximum_manifest_bytes: u64,
        maximum_entry_count: usize,
        maximum_total_payload_bytes: u64,
        maximum_report_bytes: usize,
    ) -> Result<Self, ArtifactError> {
        if maximum_manifest_bytes == 0
            || maximum_entry_count == 0
            || maximum_total_payload_bytes == 0
            || maximum_report_bytes == 0
        {
            return Err(ArtifactError::LimitExceeded);
        }
        Ok(Self {
            maximum_manifest_bytes,
            maximum_entry_count,
            maximum_total_payload_bytes,
            maximum_report_bytes,
        })
    }
}

/// A verified metadata-only projection of one sealed artifact.
///
/// File paths, payload bytes, caller paths, and environment data are never
/// included. Entry hashes are sorted by hash rather than publication path.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ArtifactReportV1 {
    pub schema: String,
    pub artifact_id: String,
    pub verified: bool,
    pub manifest_schema: String,
    pub manifest_sha256: String,
    pub entry_count: usize,
    pub total_payload_bytes: u64,
    pub entry_content_sha256: Vec<String>,
    pub integrity_lineage: String,
    pub verifier_policy: String,
}

#[derive(Debug)]
pub enum ArtifactError {
    InvalidId,
    InvalidPath,
    DuplicatePath,
    AlreadyExists,
    LimitExceeded,
    Io(io::Error),
    HashMismatch,
    Manifest,
    PublishIndeterminate,
}

impl From<io::Error> for ArtifactError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct FileRecord {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SuccessManifest {
    pub schema: String,
    pub artifact_id: String,
    pub files: Vec<FileRecord>,
}

pub struct ArtifactRoot {
    root: PathBuf,
}

pub struct Staging {
    root: PathBuf,
    id: String,
    directory: PathBuf,
    records: BTreeMap<String, FileRecord>,
}

pub struct SealedArtifact {
    root: PathBuf,
    id: String,
    directory: PathBuf,
    manifest: SuccessManifest,
}

impl ArtifactRoot {
    pub fn open_or_create(root: impl AsRef<Path>) -> Result<Self, ArtifactError> {
        let root = root.as_ref();
        if root.exists() {
            require_directory(root)?;
        } else {
            fs::create_dir_all(root)?;
        }

        let staging = root.join(STAGING_NAME);
        if staging.exists() {
            require_directory(&staging)?;
        } else {
            fs::create_dir(&staging)?;
        }

        Ok(Self {
            root: root.to_path_buf(),
        })
    }

    pub fn begin(&self, id: &str) -> Result<Staging, ArtifactError> {
        validate_id(id)?;
        let final_directory = self.root.join(id);
        if entry_exists(&final_directory)? {
            return Err(ArtifactError::AlreadyExists);
        }

        let nonce = NEXT_STAGING_NONCE.fetch_add(1, Ordering::Relaxed);
        let directory = self
            .root
            .join(STAGING_NAME)
            .join(format!("{id}-{}-{nonce}", std::process::id()));
        fs::create_dir(&directory)?;
        Ok(Staging {
            root: self.root.clone(),
            id: id.to_owned(),
            directory,
            records: BTreeMap::new(),
        })
    }

    /// Opens an existing application-owned root without creating any entries.
    pub fn open_existing(root: impl AsRef<Path>) -> Result<Self, ArtifactError> {
        let root = root.as_ref();
        require_directory(root)?;
        Ok(Self {
            root: root.to_path_buf(),
        })
    }

    pub fn verify_published(&self, id: &str) -> Result<SuccessManifest, ArtifactError> {
        validate_id(id)?;
        let directory = self.root.join(id);
        require_directory(&directory)?;

        let manifest_path = directory.join(MANIFEST_NAME);
        require_regular_file(&manifest_path)?;
        let manifest: SuccessManifest = serde_json::from_slice(&fs::read(manifest_path)?)
            .map_err(|_| ArtifactError::Manifest)?;
        validate_manifest(&manifest, id)?;

        let expected = manifest
            .files
            .iter()
            .map(|record| record.path.clone())
            .chain(std::iter::once(MANIFEST_NAME.to_owned()))
            .collect::<BTreeSet<_>>();
        if list_regular_files(&directory)? != expected {
            return Err(ArtifactError::Manifest);
        }

        for record in &manifest.files {
            let path = directory.join(&record.path);
            require_regular_file(&path)?;
            let (bytes, hash) = hash_reader(File::open(path)?, u64::MAX)?;
            if bytes != record.bytes || hash != record.sha256 {
                return Err(ArtifactError::HashMismatch);
            }
        }
        Ok(manifest)
    }

    /// Consumes exactly the requested sealed files into owned memory.
    ///
    /// The root is not a hostile-writer boundary. Callers that need that
    /// property must first materialize an independently safe snapshot.
    pub fn consume_exact_verified_v1(
        &self,
        id: &str,
        expected_manifest_sha256: &str,
        expected_files: &[(&str, u64)],
        policy: VerifiedConsumptionPolicyV1,
    ) -> Result<VerifiedFilesV1, ArtifactError> {
        validate_id(id)?;
        if !is_lowercase_sha256(expected_manifest_sha256)
            || expected_files.is_empty()
            || expected_files.iter().any(|(_, maximum)| *maximum == 0)
            || expected_files.len()
                != expected_files
                    .iter()
                    .map(|(path, _)| *path)
                    .collect::<BTreeSet<_>>()
                    .len()
        {
            return Err(ArtifactError::Manifest);
        }
        for (path, _) in expected_files {
            validate_path(path)?;
        }
        let directory = self.root.join(id);
        require_directory(&directory)?;
        let manifest_path = directory.join(MANIFEST_NAME);
        let manifest_bytes =
            read_regular_file_limited(&manifest_path, policy.maximum_manifest_bytes)?;
        let manifest_sha256 = sha256_bytes(&manifest_bytes);
        if manifest_sha256 != expected_manifest_sha256 {
            return Err(ArtifactError::HashMismatch);
        }
        let manifest: SuccessManifest =
            serde_json::from_slice(&manifest_bytes).map_err(|_| ArtifactError::Manifest)?;
        validate_manifest(&manifest, id)?;
        let expected = expected_files
            .iter()
            .map(|(path, _)| (*path).to_owned())
            .collect::<BTreeSet<_>>();
        let listed = manifest
            .files
            .iter()
            .map(|record| record.path.clone())
            .collect::<BTreeSet<_>>();
        let expected_directory_files = expected
            .iter()
            .cloned()
            .chain(std::iter::once(MANIFEST_NAME.to_owned()))
            .collect();
        if listed != expected || list_regular_files(&directory)? != expected_directory_files {
            return Err(ArtifactError::Manifest);
        }
        let mut total = 0_u64;
        let mut files = BTreeMap::new();
        for record in &manifest.files {
            let maximum = expected_files
                .iter()
                .find_map(|(path, maximum)| (*path == record.path).then_some(*maximum))
                .ok_or(ArtifactError::Manifest)?;
            if record.bytes > maximum {
                return Err(ArtifactError::LimitExceeded);
            }
            total = total
                .checked_add(record.bytes)
                .ok_or(ArtifactError::LimitExceeded)?;
            if total > policy.maximum_total_bytes {
                return Err(ArtifactError::LimitExceeded);
            }
            let bytes = read_regular_file_limited(&directory.join(&record.path), record.bytes)?;
            if bytes.len() as u64 != record.bytes || sha256_bytes(&bytes) != record.sha256 {
                return Err(ArtifactError::HashMismatch);
            }
            files.insert(record.path.clone(), bytes);
        }
        let rechecked = read_regular_file_limited(&manifest_path, policy.maximum_manifest_bytes)?;
        if rechecked != manifest_bytes || sha256_bytes(&rechecked) != expected_manifest_sha256 {
            return Err(ArtifactError::HashMismatch);
        }
        Ok(VerifiedFilesV1 {
            artifact_id: id.to_owned(),
            manifest_sha256,
            files,
        })
    }

    /// Re-verifies one published artifact and projects only allowlisted
    /// integrity metadata. This never creates, changes, or enumerates roots.
    pub fn inspect_verified_v1(
        &self,
        id: &str,
        policy: ArtifactReportPolicyV1,
    ) -> Result<ArtifactReportV1, ArtifactError> {
        validate_id(id)?;
        let directory = self.root.join(id);
        require_directory(&directory)?;

        let manifest_path = directory.join(MANIFEST_NAME);
        let manifest_bytes =
            read_regular_file_limited(&manifest_path, policy.maximum_manifest_bytes)?;
        let manifest_sha256 = sha256_bytes(&manifest_bytes);
        let manifest: SuccessManifest =
            serde_json::from_slice(&manifest_bytes).map_err(|_| ArtifactError::Manifest)?;
        validate_manifest(&manifest, id)?;
        if manifest.files.len() > policy.maximum_entry_count {
            return Err(ArtifactError::LimitExceeded);
        }

        let expected = manifest
            .files
            .iter()
            .map(|record| record.path.clone())
            .chain(std::iter::once(MANIFEST_NAME.to_owned()))
            .collect::<BTreeSet<_>>();
        if list_regular_files(&directory)? != expected {
            return Err(ArtifactError::Manifest);
        }

        let mut total_payload_bytes = 0_u64;
        let mut entry_content_sha256 = Vec::with_capacity(manifest.files.len());
        for record in &manifest.files {
            total_payload_bytes = total_payload_bytes
                .checked_add(record.bytes)
                .ok_or(ArtifactError::LimitExceeded)?;
            if total_payload_bytes > policy.maximum_total_payload_bytes {
                return Err(ArtifactError::LimitExceeded);
            }

            let path = directory.join(&record.path);
            require_regular_file(&path)?;
            let (bytes, hash) = hash_reader(File::open(path)?, record.bytes)?;
            if bytes != record.bytes || hash != record.sha256 {
                return Err(ArtifactError::HashMismatch);
            }
            entry_content_sha256.push(hash);
        }
        entry_content_sha256.sort_unstable();

        let report = ArtifactReportV1 {
            schema: ARTIFACT_REPORT_SCHEMA_V1.to_owned(),
            artifact_id: id.to_owned(),
            verified: true,
            manifest_schema: manifest.schema,
            manifest_sha256,
            entry_count: entry_content_sha256.len(),
            total_payload_bytes,
            entry_content_sha256,
            integrity_lineage: "unavailable".to_owned(),
            verifier_policy: "sipi.artifact-report-policy.v1".to_owned(),
        };
        let report_bytes =
            sipi_contracts::deterministic_json(&report).map_err(|_| ArtifactError::Manifest)?;
        if report_bytes.len() > policy.maximum_report_bytes {
            return Err(ArtifactError::LimitExceeded);
        }
        Ok(report)
    }
}

impl Staging {
    pub fn stage_reader(
        &mut self,
        path: &str,
        reader: impl Read,
        maximum_bytes: u64,
    ) -> Result<(), ArtifactError> {
        validate_path(path)?;
        if self.records.contains_key(path) {
            return Err(ArtifactError::DuplicatePath);
        }

        let target = self.directory.join(path);
        ensure_parent_directories(&self.directory, path)?;
        if entry_exists(&target)? {
            return Err(ArtifactError::AlreadyExists);
        }
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)?;
        let (bytes, sha256) = copy_and_hash(reader, &mut file, maximum_bytes)?;
        file.sync_all()?;
        self.records.insert(
            path.to_owned(),
            FileRecord {
                path: path.to_owned(),
                bytes,
                sha256,
            },
        );
        Ok(())
    }

    pub fn seal(self) -> Result<SealedArtifact, ArtifactError> {
        if self.records.is_empty() {
            return Err(ArtifactError::Manifest);
        }
        let mut files = Vec::with_capacity(self.records.len());
        for record in self.records.into_values() {
            let path = self.directory.join(&record.path);
            require_regular_file(&path)?;
            let (bytes, sha256) = hash_reader(File::open(path)?, u64::MAX)?;
            if bytes != record.bytes || sha256 != record.sha256 {
                return Err(ArtifactError::HashMismatch);
            }
            files.push(record);
        }
        let manifest = SuccessManifest {
            schema: "sipi.artifact-manifest.v1".to_owned(),
            artifact_id: self.id.clone(),
            files,
        };
        let bytes =
            sipi_contracts::deterministic_json(&manifest).map_err(|_| ArtifactError::Manifest)?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(self.directory.join(MANIFEST_NAME))?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        Ok(SealedArtifact {
            root: self.root,
            id: self.id,
            directory: self.directory,
            manifest,
        })
    }
}

impl SealedArtifact {
    pub fn publish_new(self) -> Result<SuccessManifest, ArtifactError> {
        let target = self.root.join(&self.id);
        if entry_exists(&target)? {
            return Err(ArtifactError::AlreadyExists);
        }
        fs::rename(&self.directory, &target).map_err(|_| ArtifactError::PublishIndeterminate)?;
        Ok(self.manifest)
    }
}

fn validate_id(value: &str) -> Result<(), ArtifactError> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        Err(ArtifactError::InvalidId)
    } else {
        Ok(())
    }
}

fn validate_path(value: &str) -> Result<(), ArtifactError> {
    if value.is_empty() || value.len() > 1024 || value.contains(['\\', ':', '\0']) {
        return Err(ArtifactError::InvalidPath);
    }
    for segment in value.split('/') {
        if segment.is_empty()
            || matches!(segment, "." | "..")
            || segment.ends_with([' ', '.'])
            || is_reserved_name(segment)
        {
            return Err(ArtifactError::InvalidPath);
        }
    }
    if value == MANIFEST_NAME {
        return Err(ArtifactError::InvalidPath);
    }
    Ok(())
}

fn is_reserved_name(value: &str) -> bool {
    let name = value
        .split('.')
        .next()
        .unwrap_or(value)
        .to_ascii_uppercase();
    matches!(name.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || name
            .strip_prefix("COM")
            .or_else(|| name.strip_prefix("LPT"))
            .and_then(|suffix| suffix.parse::<u8>().ok())
            .is_some_and(|number| (1..=9).contains(&number))
}

fn ensure_parent_directories(root: &Path, relative: &str) -> Result<(), ArtifactError> {
    let mut current = root.to_path_buf();
    let segments = relative.split('/').collect::<Vec<_>>();
    for segment in &segments[..segments.len().saturating_sub(1)] {
        current.push(segment);
        if entry_exists(&current)? {
            require_directory(&current)?;
        } else {
            fs::create_dir(&current)?;
        }
    }
    Ok(())
}

fn validate_manifest(manifest: &SuccessManifest, id: &str) -> Result<(), ArtifactError> {
    if manifest.schema != "sipi.artifact-manifest.v1"
        || manifest.artifact_id != id
        || manifest.files.is_empty()
    {
        return Err(ArtifactError::Manifest);
    }
    let mut paths = BTreeSet::new();
    for record in &manifest.files {
        validate_path(&record.path).map_err(|_| ArtifactError::Manifest)?;
        if !is_lowercase_sha256(&record.sha256) || !paths.insert(record.path.clone()) {
            return Err(ArtifactError::Manifest);
        }
    }
    Ok(())
}

fn is_lowercase_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn list_regular_files(root: &Path) -> Result<BTreeSet<String>, ArtifactError> {
    let mut files = BTreeSet::new();
    list_regular_files_inner(root, Path::new(""), &mut files)?;
    Ok(files)
}

fn list_regular_files_inner(
    directory: &Path,
    relative: &Path,
    files: &mut BTreeSet<String>,
) -> Result<(), ArtifactError> {
    require_directory(directory)?;
    for entry in fs::read_dir(directory)? {
        let entry = entry?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| ArtifactError::Manifest)?;
        if !(relative.as_os_str().is_empty() && name == MANIFEST_NAME) {
            validate_path(&name).map_err(|_| ArtifactError::Manifest)?;
        }
        let path = entry.path();
        let next_relative = if relative.as_os_str().is_empty() {
            name
        } else {
            format!("{}/{}", relative.display(), name)
        };
        let metadata = fs::symlink_metadata(&path)?;
        if is_unsafe_link(&metadata) {
            return Err(ArtifactError::Manifest);
        }
        if metadata.is_file() {
            files.insert(next_relative);
        } else if metadata.is_dir() {
            list_regular_files_inner(&path, Path::new(&next_relative), files)?;
        } else {
            return Err(ArtifactError::Manifest);
        }
    }
    Ok(())
}

fn entry_exists(path: &Path) -> Result<bool, ArtifactError> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn require_directory(path: &Path) -> Result<(), ArtifactError> {
    let metadata = fs::symlink_metadata(path)?;
    if is_unsafe_link(&metadata) || !metadata.is_dir() {
        Err(ArtifactError::InvalidPath)
    } else {
        Ok(())
    }
}

fn require_regular_file(path: &Path) -> Result<(), ArtifactError> {
    let metadata = fs::symlink_metadata(path)?;
    if is_unsafe_link(&metadata) || !metadata.is_file() {
        Err(ArtifactError::InvalidPath)
    } else {
        Ok(())
    }
}

fn is_unsafe_link(metadata: &fs::Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        return metadata.file_attributes() & 0x400 != 0;
    }
    #[cfg(not(windows))]
    {
        false
    }
}

fn copy_and_hash(
    mut reader: impl Read,
    mut output: impl Write,
    maximum: u64,
) -> Result<(u64, String), ArtifactError> {
    let mut hash = Sha256::new();
    let mut total: u64 = 0;
    let mut buffer = [0_u8; 8192];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        total = total
            .checked_add(read as u64)
            .ok_or(ArtifactError::LimitExceeded)?;
        if total > maximum {
            return Err(ArtifactError::LimitExceeded);
        }
        output.write_all(&buffer[..read])?;
        hash.update(&buffer[..read]);
    }
    output.flush()?;
    Ok((total, format!("{:x}", hash.finalize())))
}

fn hash_reader(reader: impl Read, maximum: u64) -> Result<(u64, String), ArtifactError> {
    copy_and_hash(reader, io::sink(), maximum)
}

fn read_regular_file_limited(path: &Path, maximum: u64) -> Result<Vec<u8>, ArtifactError> {
    require_regular_file(path)?;
    let metadata = fs::metadata(path)?;
    if metadata.len() > maximum {
        return Err(ArtifactError::LimitExceeded);
    }
    let mut bytes = Vec::new();
    File::open(path)?
        .take(maximum.saturating_add(1))
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > maximum {
        return Err(ArtifactError::LimitExceeded);
    }
    Ok(bytes)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut hash = Sha256::new();
    hash.update(bytes);
    format!("{:x}", hash.finalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn root() -> PathBuf {
        let nonce = NEXT_STAGING_NONCE.fetch_add(1, Ordering::Relaxed);
        std::env::temp_dir().join(format!("sipi-artifact-test-{}-{nonce}", std::process::id()))
    }

    #[test]
    fn publishes_and_verifies_nested_files() {
        let root = root();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut stage = store.begin("result-1").unwrap();
        stage
            .stage_reader("payload/data.bin", &b"abc"[..], 10)
            .unwrap();
        stage.seal().unwrap().publish_new().unwrap();
        assert_eq!(
            store.verify_published("result-1").unwrap().files[0].sha256,
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_unsafe_duplicate_and_limited_payloads() {
        let root = root();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut stage = store.begin("result-1").unwrap();
        for path in ["../bad", "bad//name", "CON", "bad:name", "success.json"] {
            assert!(stage.stage_reader(path, &b"x"[..], 1).is_err(), "{path}");
        }
        stage.stage_reader("a", &b"x"[..], 1).unwrap();
        assert!(stage.stage_reader("a", &b"x"[..], 1).is_err());
        assert!(matches!(
            stage.stage_reader("limited", &b"ab"[..], 1),
            Err(ArtifactError::LimitExceeded)
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn verification_rejects_extra_or_tampered_content() {
        let root = root();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut stage = store.begin("result-1").unwrap();
        stage.stage_reader("data.bin", &b"abc"[..], 10).unwrap();
        stage.seal().unwrap().publish_new().unwrap();
        fs::write(root.join("result-1").join("extra.bin"), b"x").unwrap();
        assert!(matches!(
            store.verify_published("result-1"),
            Err(ArtifactError::Manifest)
        ));
        fs::remove_file(root.join("result-1").join("extra.bin")).unwrap();
        fs::write(root.join("result-1").join("data.bin"), b"changed").unwrap();
        assert!(matches!(
            store.verify_published("result-1"),
            Err(ArtifactError::HashMismatch)
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn exact_verified_consumption_returns_only_sealed_requested_bytes() {
        let root = root();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut stage = store.begin("pair-1").unwrap();
        stage
            .stage_reader("waveform.json", &b"metadata"[..], 100)
            .unwrap();
        stage
            .stage_reader("waveform.f64le", &b"payload"[..], 100)
            .unwrap();
        stage.seal().unwrap().publish_new().unwrap();
        let manifest = fs::read(root.join("pair-1").join(MANIFEST_NAME)).unwrap();
        let digest = sha256_bytes(&manifest);
        let reader = ArtifactRoot::open_existing(&root).unwrap();
        let files = reader
            .consume_exact_verified_v1(
                "pair-1",
                &digest,
                &[("waveform.json", 100), ("waveform.f64le", 100)],
                VerifiedConsumptionPolicyV1::try_new(4096, 200).unwrap(),
            )
            .unwrap();
        assert_eq!(files.artifact_id(), "pair-1");
        assert_eq!(files.manifest_sha256(), digest);
        assert_eq!(files.file("waveform.json"), Some(&b"metadata"[..]));
        assert_eq!(files.file("waveform.f64le"), Some(&b"payload"[..]));

        assert!(matches!(
            reader.consume_exact_verified_v1(
                "pair-1",
                &digest,
                &[("waveform.json", 100)],
                VerifiedConsumptionPolicyV1::try_new(4096, 200).unwrap(),
            ),
            Err(ArtifactError::Manifest)
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn verified_report_is_metadata_only_and_rejects_tampering_or_excess() {
        let root = root();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut stage = store.begin("result-1").unwrap();
        stage
            .stage_reader("private-name.json", &b"payload-content"[..], 100)
            .unwrap();
        stage.seal().unwrap().publish_new().unwrap();
        let success_before = fs::read(root.join("result-1").join(MANIFEST_NAME)).unwrap();

        let reader = ArtifactRoot::open_existing(&root).unwrap();
        let policy = ArtifactReportPolicyV1::try_new(4096, 4, 100, 4096).unwrap();
        let report = reader.inspect_verified_v1("result-1", policy).unwrap();
        assert_eq!(report.schema, ARTIFACT_REPORT_SCHEMA_V1);
        assert!(report.verified);
        assert_eq!(report.entry_count, 1);
        let bytes = sipi_contracts::deterministic_json(&report).unwrap();
        assert!(
            !String::from_utf8(bytes)
                .unwrap()
                .contains("private-name.json")
        );
        assert_eq!(
            fs::read(root.join("result-1").join(MANIFEST_NAME)).unwrap(),
            success_before
        );
        assert!(matches!(
            reader.inspect_verified_v1(
                "result-1",
                ArtifactReportPolicyV1::try_new(4096, 4, 1, 4096).unwrap()
            ),
            Err(ArtifactError::LimitExceeded)
        ));
        fs::write(root.join("result-1").join("private-name.json"), b"changed").unwrap();
        assert!(matches!(
            reader.inspect_verified_v1("result-1", policy),
            Err(ArtifactError::HashMismatch)
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn never_overwrites_an_existing_artifact() {
        let root = root();
        let store = ArtifactRoot::open_or_create(&root).unwrap();
        let mut first = store.begin("result-1").unwrap();
        first.stage_reader("data.bin", &b"abc"[..], 10).unwrap();
        first.seal().unwrap().publish_new().unwrap();
        assert!(matches!(
            store.begin("result-1"),
            Err(ArtifactError::AlreadyExists)
        ));
        let _ = fs::remove_dir_all(root);
    }
}
