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
        if metadata.file_type().is_symlink() {
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
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        Err(ArtifactError::InvalidPath)
    } else {
        Ok(())
    }
}

fn require_regular_file(path: &Path) -> Result<(), ArtifactError> {
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        Err(ArtifactError::InvalidPath)
    } else {
        Ok(())
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
