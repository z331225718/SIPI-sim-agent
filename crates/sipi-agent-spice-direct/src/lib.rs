#![forbid(unsafe_code)]
#![recursion_limit = "512"]

//! AS-05 admission model plus the lane-local AS-01 `fit-sparam` direct port.
//!
//! The portable control and artifact paths are executable for deck splitting,
//! audit, conversion, dependency admission, and backend dispatch. Solver
//! processes remain caller-owned external runtimes, and numerical parity is
//! not claimed without the pinned differential gate.

pub mod as02_fit_sparam_cascade;
pub mod as03_fit_yparam;
pub mod as04_tune_yparam_tran;
pub mod as06_run_rfm;
pub mod fit_sparam;

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::{Display, Formatter};
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};
use std::sync::{
    Arc,
    atomic::{AtomicBool, AtomicUsize, Ordering},
};
use std::thread;
use std::time::{Duration, Instant, SystemTime};

use serde_json::json;
use sha2::{Digest, Sha256};

pub const UPSTREAM_REPOSITORY: &str = "agent-spice";
pub const UPSTREAM_COMMIT: &str = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5";
pub const UPSTREAM_TREE: &str = "b6bde97128030d6cea0d68b2f0a35d807be8c402";
pub const UPSTREAM_LICENSE: &str = "MIT";
pub const UPSTREAM_MEASURE_SOURCE_SHA256: &str =
    "cbb851db87c951e1d3a76cc99f6d1bb9fc31a3c4c20234d25507cd85d71695f4";
pub const WORKFLOW_ID: &str = "AS-05";
pub const WORKFLOW_NAME: &str = "run-hspice";

const SUPPORTED_DIRECTIVES: &[&str] = &[
    ".ac",
    ".alter",
    ".dc",
    ".elif",
    ".else",
    ".elseif",
    ".endl",
    ".end",
    ".endif",
    ".ends",
    ".global",
    ".inc",
    ".include",
    ".if",
    ".lib",
    ".model",
    ".measure",
    ".meas",
    ".op",
    ".option",
    ".options",
    ".param",
    ".print",
    ".probe",
    ".subckt",
    ".temp",
    ".tran",
    ".endcomment",
    ".end*comment",
];
const MAX_DECK_BYTES: u64 = 16 * 1024 * 1024;
const MAX_PROJECT_MANIFEST_BYTES: u64 = 1024 * 1024;
const MAX_EXECUTABLE_BYTES: u64 = 256 * 1024 * 1024;
const EXTERNAL_TIMEOUT: Duration = Duration::from_secs(120);
const MAX_EXTERNAL_PIPE_BYTES: usize = 8 * 1024 * 1024;
const MAX_EXTERNAL_TRANSCRIPT_BYTES: usize = 8 * 1024 * 1024;
const MAX_EXTERNAL_COMBINED_PARSE_BYTES: usize = 16 * 1024 * 1024;
const MAX_EXTERNAL_ARTIFACT_BYTES: usize = 8 * 1024 * 1024;
const MAX_DEPENDENCY_FILE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_STAGED_DEPENDENCY_FILE_BYTES: u64 = MAX_DEPENDENCY_FILE_BYTES;

/// Project-level input accepted by the pinned `project.py` path.
///
/// This is intentionally a manifest and dispatch contract only.  It does not
/// imply that a native, ngspice, Xyce, or XDM executable is bundled here.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProjectManifest {
    pub name: String,
    pub hspice_deck: Option<PathBuf>,
    pub backend: Backend,
    pub output_root: PathBuf,
}

impl ProjectManifest {
    pub fn from_yaml(path: impl AsRef<Path>) -> Result<Self, DirectPortError> {
        let path = path.as_ref();
        let metadata = fs::metadata(path)
            .map_err(|error| DirectPortError::ProjectManifestIo(error.to_string()))?;
        if metadata.len() > MAX_PROJECT_MANIFEST_BYTES {
            return Err(DirectPortError::InvalidProjectManifest(
                "manifest exceeds the bounded 1 MiB input budget".to_owned(),
            ));
        }
        let text = fs::read_to_string(path)
            .map_err(|error| DirectPortError::ProjectManifestIo(error.to_string()))?;
        let value: serde_yaml::Value = serde_yaml::from_str(&text)
            .map_err(|error| DirectPortError::InvalidProjectManifest(error.to_string()))?;
        Self::from_mapping(&value)
    }

    pub fn from_mapping(value: &serde_yaml::Value) -> Result<Self, DirectPortError> {
        let mapping = value.as_mapping().ok_or_else(|| {
            DirectPortError::InvalidProjectManifest("manifest must contain a mapping".to_owned())
        })?;
        let key = |name: &str| serde_yaml::Value::String(name.to_owned());
        let required_string = |field: &str| {
            mapping
                .get(key(field))
                .and_then(serde_yaml::Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .map(ToOwned::to_owned)
                .ok_or_else(|| {
                    DirectPortError::InvalidProjectManifest(format!(
                        "manifest field '{field}' must be a non-empty string"
                    ))
                })
        };
        let name = required_string("name")?;
        let backend_name =
            mapping
                .get(key("backend"))
                .map_or(Ok("native".to_owned()), |value| {
                    value.as_str().map(str::to_ascii_lowercase).ok_or_else(|| {
                        DirectPortError::InvalidProjectManifest(
                            "manifest field 'backend' must be a string".to_owned(),
                        )
                    })
                })?;
        let backend = Backend::parse(&backend_name)?;
        let optional_mapping = |field: &str| {
            mapping.get(key(field)).map_or_else(
                || Ok(None),
                |value| {
                    value.as_mapping().map(Some).ok_or_else(|| {
                        DirectPortError::InvalidProjectManifest(format!(
                            "manifest field '{field}' must be a mapping"
                        ))
                    })
                },
            )
        };
        let inputs = optional_mapping("inputs")?;
        let outputs = optional_mapping("outputs")?;
        let hspice_deck = match inputs.and_then(|mapping| mapping.get(key("hspice_deck"))) {
            None | Some(serde_yaml::Value::Null) => None,
            Some(value) => {
                let raw = value.as_str().ok_or_else(|| {
                    DirectPortError::InvalidProjectManifest(
                        "inputs.hspice_deck must be a string".to_owned(),
                    )
                })?;
                (!raw.is_empty()).then(|| PathBuf::from(raw))
            }
        };
        let output_root = outputs
            .and_then(|mapping| mapping.get(key("root")))
            .map(|value| {
                value.as_str().map(PathBuf::from).ok_or_else(|| {
                    DirectPortError::InvalidProjectManifest(
                        "outputs.root must be a string".to_owned(),
                    )
                })
            })
            .transpose()?
            .unwrap_or_else(|| PathBuf::from("runs"));
        Ok(Self {
            name,
            hspice_deck,
            backend,
            output_root,
        })
    }
}

/// Match `project.prepare_run_directory` without silently launching a solver.
pub fn prepare_project_run_directory(
    root: impl AsRef<Path>,
    project_name: &str,
    case_name: &str,
) -> Result<PathBuf, DirectPortError> {
    if project_name.is_empty() || case_name.is_empty() {
        return Err(DirectPortError::InvalidProjectManifest(
            "project and case names must be non-empty".to_owned(),
        ));
    }
    let run_dir = root.as_ref().join(project_name).join(case_name);
    fs::create_dir_all(&run_dir).map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    Ok(run_dir)
}

pub(crate) fn absolute_path(path: &Path) -> Result<PathBuf, std::io::Error> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        Ok(std::env::current_dir()?.join(path))
    }
}

pub(crate) fn file_sha256(path: &Path) -> Result<String, DirectPortError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(DirectPortError::InputIo(
            "hashed file must be a regular non-symlink file".to_owned(),
        ));
    }
    if metadata.len() > MAX_EXECUTABLE_BYTES {
        return Err(DirectPortError::InputIo(
            "hashed file exceeds the bounded 256 MiB budget".to_owned(),
        ));
    }
    let mut file =
        fs::File::open(path).map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut total = 0_u64;
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| DirectPortError::InputIo(error.to_string()))?;
        if count == 0 {
            break;
        }
        total = total
            .checked_add(count as u64)
            .ok_or_else(|| DirectPortError::InputIo("hashed file size overflow".to_owned()))?;
        if total > MAX_EXECUTABLE_BYTES {
            return Err(DirectPortError::InputIo(
                "hashed file exceeds the bounded 256 MiB budget".to_owned(),
            ));
        }
        digest.update(&buffer[..count]);
    }
    let after =
        fs::symlink_metadata(path).map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    if after.file_type().is_symlink() || !after.is_file() || after.len() != metadata.len() {
        return Err(DirectPortError::InputIo(
            "hashed file changed during bounded read".to_owned(),
        ));
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn dependency_reference_is_absolute(reference: &str) -> bool {
    let bytes = reference.as_bytes();
    Path::new(reference).is_absolute()
        || reference.starts_with('/')
        || reference.starts_with('\\')
        || (bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':')
}

fn redacted_dependency_reference(reference: &str) -> String {
    if !dependency_reference_is_absolute(reference) {
        return reference.to_owned();
    }
    let basename = reference
        .replace('\\', "/")
        .rsplit('/')
        .next()
        .filter(|value| !value.is_empty())
        .unwrap_or("unnamed")
        .chars()
        .map(|value| {
            if value.is_ascii_alphanumeric() || matches!(value, '.' | '-' | '_') {
                value
            } else {
                '_'
            }
        })
        .collect::<String>();
    let digest = Sha256::digest(reference.as_bytes());
    format!("<absolute:{basename}:{:x}>", digest)
}

fn redact_deck_line(line: &str) -> String {
    let leading = line.len() - line.trim_start().len();
    let trimmed = &line[leading..];
    let Some((directive, rest)) = trimmed.split_once(char::is_whitespace) else {
        return line.to_owned();
    };
    if !matches!(
        directive.to_ascii_lowercase().as_str(),
        ".include" | ".inc" | ".lib"
    ) {
        return line.to_owned();
    }
    let rest_start = trimmed.len() - rest.len();
    let rest_trimmed = rest.trim_start();
    let token_offset = rest_start + (rest.len() - rest_trimmed.len());
    let quote = rest_trimmed
        .chars()
        .next()
        .filter(|value| *value == '\'' || *value == '"');
    let token_len = if let Some(quote) = quote {
        rest_trimmed[quote.len_utf8()..]
            .find(quote)
            .map(|index| index + quote.len_utf8())
            .unwrap_or(rest_trimmed.len())
            + quote.len_utf8()
    } else {
        rest_trimmed
            .find(char::is_whitespace)
            .unwrap_or(rest_trimmed.len())
    };
    let raw_token = &rest_trimmed[..token_len.min(rest_trimmed.len())];
    let unquoted = raw_token.trim_matches(['\'', '"']);
    if !dependency_reference_is_absolute(unquoted) {
        return line.to_owned();
    }
    let replacement = if let Some(quote) = quote {
        format!(
            "{}{}{}",
            quote,
            redacted_dependency_reference(unquoted),
            quote
        )
    } else {
        redacted_dependency_reference(unquoted)
    };
    let token_end = token_offset + raw_token.len();
    format!(
        "{}{}{}{}",
        &line[..leading + token_offset],
        replacement,
        &line[leading + token_end..],
        ""
    )
}

fn redact_deck_text(text: &str) -> String {
    let mut result = text
        .lines()
        .map(redact_deck_line)
        .collect::<Vec<_>>()
        .join("\n");
    if text.ends_with('\n') {
        result.push('\n');
    }
    result
}

fn redacted_audit(audit: &DeckAudit) -> DeckAudit {
    DeckAudit {
        directive_counts: audit.directive_counts.clone(),
        includes: audit
            .includes
            .iter()
            .map(|value| redacted_dependency_reference(value))
            .collect(),
        libraries: audit
            .libraries
            .iter()
            .map(|library| LibraryReference {
                path: redacted_dependency_reference(&library.path),
                section: library.section.clone(),
            })
            .collect(),
        unsupported_directives: audit.unsupported_directives.clone(),
    }
}

#[derive(Debug, Eq, PartialEq)]
struct DependencyIdentity {
    bytes: u64,
    modified: Option<SystemTime>,
    file_id: same_file::Handle,
}

fn dependency_file_id(path: &Path) -> Result<same_file::Handle, DirectPortError> {
    // same-file uses the native dev/inode identity on Unix and the native
    // volume serial/file index pair on Windows, without unstable MetadataExt
    // methods. Failure is typed rather than falling back to path strings.
    same_file::Handle::from_path(path).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "dependency file identity unavailable: {error}"
        ))
    })
}

fn dependency_file_id_from_handle(file: &fs::File) -> Result<same_file::Handle, DirectPortError> {
    same_file::Handle::from_file(file.try_clone().map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "dependency file identity unavailable: {error}"
        ))
    })?)
    .map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "dependency file identity unavailable: {error}"
        ))
    })
}

fn dependency_identity(
    path: &Path,
    metadata: &fs::Metadata,
) -> Result<DependencyIdentity, DirectPortError> {
    Ok(DependencyIdentity {
        bytes: metadata.len(),
        modified: metadata.modified().ok(),
        file_id: dependency_file_id(path)?,
    })
}

fn dependency_identity_for_handle(
    file: &fs::File,
    metadata: &fs::Metadata,
) -> Result<DependencyIdentity, DirectPortError> {
    Ok(DependencyIdentity {
        bytes: metadata.len(),
        modified: metadata.modified().ok(),
        file_id: dependency_file_id_from_handle(file)?,
    })
}

fn metadata_is_reparse(metadata: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        metadata.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    {
        let _ = metadata;
        false
    }
}

fn reject_dependency_reparse_chain(path: &Path) -> Result<(), DirectPortError> {
    for ancestor in path.ancestors() {
        match fs::symlink_metadata(ancestor) {
            Ok(metadata) if metadata.file_type().is_symlink() || metadata_is_reparse(&metadata) => {
                return Err(DirectPortError::UnsupportedExecution(
                    "dependency path contains a symlink or reparse component".to_owned(),
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(DirectPortError::UnsupportedExecution(format!(
                    "dependency path identity could not be inspected: {error}"
                )));
            }
        }
    }
    Ok(())
}

fn read_dependency_once(path: &Path) -> Result<(Vec<u8>, DependencyIdentity), DirectPortError> {
    reject_dependency_reparse_chain(path)?;
    let before_path = fs::symlink_metadata(path).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!("dependency identity unavailable: {error}"))
    })?;
    if !before_path.is_file()
        || before_path.file_type().is_symlink()
        || metadata_is_reparse(&before_path)
    {
        return Err(DirectPortError::UnsupportedExecution(
            "dependency must be a regular non-symlink file".to_owned(),
        ));
    }
    let before = dependency_identity(path, &before_path)?;
    if before.bytes > MAX_DEPENDENCY_FILE_BYTES {
        return Err(DirectPortError::UnsupportedExecution(
            "dependency exceeds the bounded 16 MiB file budget".to_owned(),
        ));
    }
    let mut file = fs::File::open(path).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!("dependency could not be opened: {error}"))
    })?;
    let handle_before = dependency_identity_for_handle(
        &file,
        &file.metadata().map_err(|error| {
            DirectPortError::UnsupportedExecution(format!(
                "dependency handle identity unavailable: {error}"
            ))
        })?,
    )?;
    if handle_before != before {
        return Err(DirectPortError::UnsupportedExecution(
            "dependency changed before bounded read".to_owned(),
        ));
    }
    let mut bytes = Vec::new();
    (&mut file)
        .take(MAX_DEPENDENCY_FILE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| {
            DirectPortError::UnsupportedExecution(format!("dependency read failed: {error}"))
        })?;
    if bytes.len() as u64 > MAX_DEPENDENCY_FILE_BYTES {
        return Err(DirectPortError::UnsupportedExecution(
            "dependency exceeds the bounded 16 MiB file budget".to_owned(),
        ));
    }
    let handle_after = dependency_identity_for_handle(
        &file,
        &file.metadata().map_err(|error| {
            DirectPortError::UnsupportedExecution(format!(
                "dependency handle identity unavailable: {error}"
            ))
        })?,
    )?;
    let after_path = fs::symlink_metadata(path).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "dependency post-read identity unavailable: {error}"
        ))
    })?;
    let after = dependency_identity(path, &after_path)?;
    if handle_after != before
        || after != before
        || !after_path.is_file()
        || after_path.file_type().is_symlink()
        || metadata_is_reparse(&after_path)
    {
        return Err(DirectPortError::UnsupportedExecution(
            "dependency changed during bounded read".to_owned(),
        ));
    }
    if bytes.len() as u64 != before.bytes {
        return Err(DirectPortError::UnsupportedExecution(
            "dependency size changed during bounded read".to_owned(),
        ));
    }
    Ok((bytes, before))
}

fn normalized_relative_path(path: &Path) -> Result<PathBuf, ()> {
    let mut output = PathBuf::new();
    for component in path.components() {
        match component {
            std::path::Component::CurDir => {}
            std::path::Component::Normal(value) => {
                let value = value.to_str().ok_or(())?;
                let portable = value.replace('\\', "/");
                for segment in portable.split('/') {
                    if segment.is_empty()
                        || segment == "."
                        || segment == ".."
                        || segment.contains(':')
                        || segment.ends_with('.')
                        || segment.ends_with(' ')
                        || is_windows_device_name(segment)
                    {
                        return Err(());
                    }
                }
                output.push(value);
            }
            std::path::Component::ParentDir => {
                if !output.pop() {
                    return Err(());
                }
            }
            std::path::Component::RootDir | std::path::Component::Prefix(_) => return Err(()),
        }
    }
    if output.as_os_str().is_empty() {
        return Err(());
    }
    Ok(output)
}

fn is_windows_device_name(value: &str) -> bool {
    let stem = value
        .split_once('.')
        .map_or(value, |(stem, _)| stem)
        .to_ascii_uppercase();
    matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (stem.len() == 4
            && (stem.starts_with("COM") || stem.starts_with("LPT"))
            && stem.as_bytes()[3].is_ascii_digit()
            && stem.as_bytes()[3] != b'0')
}

fn dependency_owned_collision(relative: &Path) -> bool {
    const OWNED: &[&str] = &[
        "case.cir",
        "case.source.sp",
        "dependencies.json",
        "compat_report.json",
        "preflight.log",
        "run_report.json",
        "run_summary.json",
        "waveform.csv",
        "stdout.log",
        "stderr.log",
        "case",
    ];
    relative.components().any(|component| {
        let std::path::Component::Normal(value) = component else {
            return false;
        };
        let Some(value) = value.to_str() else {
            return false;
        };
        OWNED.iter().any(|name| value.eq_ignore_ascii_case(name))
    })
}

fn write_dependency_create_new(
    path: &Path,
    bytes: &[u8],
) -> Result<(u64, String, DependencyIdentity), DirectPortError> {
    let byte_count = u64::try_from(bytes.len()).map_err(|_| {
        DirectPortError::UnsupportedExecution("staged dependency byte count overflow".to_owned())
    })?;
    if byte_count > MAX_STAGED_DEPENDENCY_FILE_BYTES {
        return Err(DirectPortError::UnsupportedExecution(
            "staged dependency exceeds the bounded 16 MiB file budget".to_owned(),
        ));
    }
    if let Some(parent) = path.parent() {
        reject_dependency_reparse_chain(parent)?;
        fs::create_dir_all(parent).map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        reject_dependency_reparse_chain(parent)?;
    }
    let mut created = false;
    let result = (|| {
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(path)
            .map_err(|error| {
                DirectPortError::UnsupportedExecution(format!(
                    "dependency staging target is not fresh: {error}"
                ))
            })?;
        created = true;
        file.write_all(bytes)
            .and_then(|_| file.flush())
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        file.sync_all()
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        reject_dependency_reparse_chain(path)?;
        let metadata = file
            .metadata()
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        let written = dependency_identity_for_handle(&file, &metadata)?;
        if written.bytes != byte_count {
            return Err(DirectPortError::OutputIo(
                "dependency staged byte count changed during write".to_owned(),
            ));
        }
        file.seek(SeekFrom::Start(0))
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        let mut physical = Vec::new();
        (&mut file)
            .take(MAX_STAGED_DEPENDENCY_FILE_BYTES + 1)
            .read_to_end(&mut physical)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        if physical.len() as u64 != written.bytes || physical != bytes {
            return Err(DirectPortError::OutputIo(
                "dependency staged bytes changed during physical readback".to_owned(),
            ));
        }
        let post_metadata = file
            .metadata()
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        let post_handle = dependency_identity_for_handle(&file, &post_metadata)?;
        let post_path = fs::symlink_metadata(path)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        let post_path_identity = dependency_identity(path, &post_path)?;
        if post_handle != written
            || post_path_identity != written
            || post_metadata.len() != physical.len() as u64
        {
            return Err(DirectPortError::OutputIo(
                "dependency staged identity changed during physical readback".to_owned(),
            ));
        }
        let sha256 = format!("{:x}", Sha256::digest(&physical));
        Ok((physical.len() as u64, sha256, written))
    })();
    match result {
        Err(original) if created => match fs::remove_file(path) {
            Ok(()) => Err(original),
            Err(cleanup) => Err(DirectPortError::OutputIo(format!(
                "dependency staging failed ({original}); cleanup failed ({cleanup})"
            ))),
        },
        other => other,
    }
}

pub(crate) fn attest_external_executable(
    path: &Path,
    expected_sha256: Option<&str>,
    label: &str,
) -> Result<(PathBuf, String), DirectPortError> {
    if !path.is_absolute() {
        return Err(DirectPortError::UnsupportedExecution(format!(
            "{label} requires an absolute executable path"
        )));
    }
    let path = absolute_path(path).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!("{label} path resolution failed: {error}"))
    })?;
    let metadata = fs::symlink_metadata(&path).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!("{label} is unavailable: {error}"))
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(DirectPortError::UnsupportedExecution(format!(
            "{label} must be a regular non-symlink executable"
        )));
    }
    if metadata.len() > MAX_EXECUTABLE_BYTES {
        return Err(DirectPortError::UnsupportedExecution(format!(
            "{label} exceeds the executable byte budget"
        )));
    }
    let expected = expected_sha256.ok_or_else(|| {
        DirectPortError::UnsupportedExecution(format!("{label} requires a caller-supplied SHA-256"))
    })?;
    if expected.len() != 64 || !expected.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(DirectPortError::UnsupportedExecution(format!(
            "{label} SHA-256 must be exactly 64 hexadecimal characters"
        )));
    }
    let actual = file_sha256(&path)?;
    if actual != expected.to_ascii_lowercase() {
        return Err(DirectPortError::UnsupportedExecution(format!(
            "{label} SHA-256 does not match caller attestation"
        )));
    }
    Ok((path, actual))
}

pub(crate) struct ExternalProcessResult {
    pub(crate) status: ExitStatus,
    pub(crate) stdout: Vec<u8>,
    pub(crate) stderr: Vec<u8>,
}

fn external_file_stamp(path: &Path) -> Option<(u64, SystemTime)> {
    let metadata = fs::metadata(path).ok()?;
    Some((metadata.len(), metadata.modified().ok()?))
}

fn external_artifact_changed(path: &Path, before: Option<(u64, SystemTime)>) -> bool {
    let Some(after) = external_file_stamp(path) else {
        return false;
    };
    before.is_none_or(|value| value != after)
}

fn external_artifact_record(
    path: &Path,
    relative: &str,
) -> Result<serde_json::Value, DirectPortError> {
    let bytes = fs::metadata(path)
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
        .len();
    if bytes as usize > MAX_EXTERNAL_ARTIFACT_BYTES {
        return Err(DirectPortError::OutputIo(format!(
            "external artifact '{relative}' exceeds the bounded 8 MiB output budget"
        )));
    }
    Ok(json!({
        "path": relative,
        "bytes": bytes,
        "sha256": file_sha256(path)?,
    }))
}

fn read_external_output<R: Read>(
    mut reader: R,
    total: Arc<AtomicUsize>,
    overflow: Arc<AtomicBool>,
    read_error: Arc<AtomicBool>,
) -> Result<Vec<u8>, io::Error> {
    let mut output = Vec::new();
    let mut chunk = [0_u8; 16 * 1024];
    loop {
        match reader.read(&mut chunk) {
            Ok(0) => break,
            Ok(count) => {
                let mut reserved = false;
                loop {
                    let current = total.load(Ordering::Acquire);
                    let Some(next) = current.checked_add(count) else {
                        overflow.store(true, Ordering::Release);
                        break;
                    };
                    if next > MAX_EXTERNAL_PIPE_BYTES {
                        overflow.store(true, Ordering::Release);
                        break;
                    }
                    if total
                        .compare_exchange(current, next, Ordering::AcqRel, Ordering::Acquire)
                        .is_ok()
                    {
                        reserved = true;
                        break;
                    }
                }
                if !reserved {
                    break;
                }
                output.extend_from_slice(&chunk[..count]);
            }
            Err(error) => {
                read_error.store(true, Ordering::Release);
                return Err(error);
            }
        }
    }
    Ok(output)
}

pub(crate) fn run_external_process(
    program: &Path,
    arguments: &[PathBuf],
    current_dir: &Path,
) -> Result<ExternalProcessResult, DirectPortError> {
    run_external_process_inner(program, arguments, current_dir, None, false)
}

/// Run an external solver with one caller-staged SPICE_SCRIPTS directory.
/// Ambient initialization variables remain cleared; only this explicit,
/// already-created directory is admitted.
pub(crate) fn run_external_process_with_spice_scripts(
    program: &Path,
    arguments: &[PathBuf],
    current_dir: &Path,
    spice_scripts: &Path,
) -> Result<ExternalProcessResult, DirectPortError> {
    run_external_process_inner(program, arguments, current_dir, Some(spice_scripts), false)
}

/// Run the AS-06 native engine with the native-loader allowlist boundary.
/// The ordinary external-process helper deliberately keeps its historical
/// environment behavior; only this native entry removes managed profiler and
/// dynamic-loader injection variables.
pub(crate) fn run_native_external_process(
    program: &Path,
    arguments: &[PathBuf],
    current_dir: &Path,
) -> Result<ExternalProcessResult, DirectPortError> {
    run_external_process_inner(program, arguments, current_dir, None, true)
}

fn fresh_external_user_init_root(current_dir: &Path) -> Result<PathBuf, DirectPortError> {
    let current = absolute_path(current_dir).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "external process working-directory resolution failed: {error}"
        ))
    })?;
    let metadata = fs::symlink_metadata(&current).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "external process working directory is unavailable: {error}"
        ))
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(DirectPortError::UnsupportedExecution(
            "external process working directory must be a regular directory".to_owned(),
        ));
    }
    let user_root = current.join(".sipi-spice-user-init");
    fs::create_dir(&user_root).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "external user-init root must be fresh and create-new: {error}"
        ))
    })?;
    let user_metadata = fs::symlink_metadata(&user_root).map_err(|error| {
        DirectPortError::UnsupportedExecution(format!(
            "external user-init root could not be rechecked: {error}"
        ))
    })?;
    if user_metadata.file_type().is_symlink() || !user_metadata.is_dir() {
        return Err(DirectPortError::UnsupportedExecution(
            "external user-init root must be a regular directory".to_owned(),
        ));
    }
    if fs::read_dir(&user_root)
        .map_err(|error| DirectPortError::UnsupportedExecution(error.to_string()))?
        .next()
        .is_some()
    {
        return Err(DirectPortError::UnsupportedExecution(
            "external user-init root is not empty".to_owned(),
        ));
    }
    Ok(user_root)
}

fn run_external_process_inner(
    program: &Path,
    arguments: &[PathBuf],
    current_dir: &Path,
    spice_scripts: Option<&Path>,
    native_environment: bool,
) -> Result<ExternalProcessResult, DirectPortError> {
    if spice_scripts.is_some_and(|path| !path.is_absolute() || !path.is_dir()) {
        return Err(DirectPortError::UnsupportedExecution(
            "explicit SPICE_SCRIPTS directory must be absolute and existing".to_owned(),
        ));
    }
    let user_init_root = fresh_external_user_init_root(current_dir)?;
    let mut command = Command::new(program);
    command
        .args(arguments.iter().map(|value| value.as_os_str()))
        .current_dir(current_dir)
        .env_remove("SPICE_SCRIPTS")
        .env_remove("SPICEINIT")
        .env_remove("SPICE_INIT")
        .env_remove("SPICE_PATH")
        .env_remove("NGSPICE_INPUT_DIR")
        .env_remove("NGSPICE_INPUT_PATH")
        .env_remove("NGSPICE_SCRIPTS")
        .env_remove("NGSPICE_USERINIT")
        .env_remove("NGSPICE_USERINIT_DIR")
        .env_remove("SPICE_USERINIT")
        .env_remove("HOME")
        .env_remove("USERPROFILE")
        .env_remove("HOMEDRIVE")
        .env_remove("HOMEPATH")
        .env_remove("APPDATA")
        .env_remove("LOCALAPPDATA")
        .env_remove("XDG_CONFIG_HOME")
        .env_remove("XDG_CONFIG_DIRS")
        .env_remove("XDG_DATA_HOME")
        .env("HOME", &user_init_root)
        .env("USERPROFILE", &user_init_root)
        .env("XDG_CONFIG_HOME", &user_init_root)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    if let Some(path) = spice_scripts {
        command.env("SPICE_SCRIPTS", path);
    }
    if native_environment {
        command
            .env_remove("DOTNET_STARTUP_HOOKS")
            .env_remove("DOTNET_ADDITIONAL_DEPS")
            .env_remove("DOTNET_SHARED_STORE")
            .env_remove("COREHOST_TRACEFILE")
            .env_remove("COREHOST_TRACE")
            .env_remove("CORECLR_ENABLE_PROFILING")
            .env_remove("CORECLR_PROFILER")
            .env_remove("CORECLR_PROFILER_PATH")
            .env_remove("LD_PRELOAD")
            .env_remove("LD_LIBRARY_PATH")
            .env_remove("DYLD_INSERT_LIBRARIES")
            .env_remove("DYLD_LIBRARY_PATH");
    }
    let mut child = command
        .spawn()
        .map_err(|error| DirectPortError::UnsupportedExecution(error.to_string()))?;
    let overflow = Arc::new(AtomicBool::new(false));
    let total = Arc::new(AtomicUsize::new(0));
    let read_error = Arc::new(AtomicBool::new(false));
    let Some(stdout) = child.stdout.take() else {
        let _ = child.kill();
        let _ = child.wait();
        return Err(DirectPortError::UnsupportedExecution(
            "external stdout pipe unavailable".to_owned(),
        ));
    };
    let Some(stderr) = child.stderr.take() else {
        let _ = child.kill();
        let _ = child.wait();
        return Err(DirectPortError::UnsupportedExecution(
            "external stderr pipe unavailable".to_owned(),
        ));
    };
    let stdout_overflow = Arc::clone(&overflow);
    let stdout_total = Arc::clone(&total);
    let stdout_read_error = Arc::clone(&read_error);
    let stdout_thread = thread::spawn(move || {
        read_external_output(stdout, stdout_total, stdout_overflow, stdout_read_error)
    });
    let stderr_overflow = Arc::clone(&overflow);
    let stderr_total = Arc::clone(&total);
    let stderr_read_error = Arc::clone(&read_error);
    let stderr_thread = thread::spawn(move || {
        read_external_output(stderr, stderr_total, stderr_overflow, stderr_read_error)
    });
    let deadline = Instant::now() + EXTERNAL_TIMEOUT;
    let mut failure = None;
    let status = loop {
        if overflow.load(Ordering::Acquire) {
            failure = Some("external solver output exceeded the bounded 8 MiB budget".to_owned());
            break None;
        }
        if read_error.load(Ordering::Acquire) {
            failure = Some("external solver output read failed".to_owned());
            break None;
        }
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if Instant::now() >= deadline => {
                failure = Some("external solver exceeded the 120 second timeout".to_owned());
                break None;
            }
            Ok(None) => thread::sleep(Duration::from_millis(10)),
            Err(error) => {
                failure = Some(error.to_string());
                break None;
            }
        }
    };
    if failure.is_some() {
        let _ = child.kill();
    }
    if failure.is_some() || status.is_none() {
        let _ = child.wait();
    }
    let stdout = stdout_thread
        .join()
        .map_err(|_| {
            DirectPortError::UnsupportedExecution("external stdout reader failed".to_owned())
        })?
        .map_err(|error| {
            DirectPortError::UnsupportedExecution(format!("external stdout read failed: {error}"))
        })?;
    let stderr = stderr_thread
        .join()
        .map_err(|_| {
            DirectPortError::UnsupportedExecution("external stderr reader failed".to_owned())
        })?
        .map_err(|error| {
            DirectPortError::UnsupportedExecution(format!("external stderr read failed: {error}"))
        })?;
    if let Some(error) = failure {
        return Err(DirectPortError::UnsupportedExecution(error));
    }
    if overflow.load(Ordering::Acquire) {
        return Err(DirectPortError::UnsupportedExecution(
            "external solver output exceeded the bounded 8 MiB budget".to_owned(),
        ));
    }
    Ok(ExternalProcessResult {
        status: status.expect("successful external process must have a status"),
        stdout,
        stderr,
    })
}

type StagedCaseDependencies = (
    Vec<serde_json::Value>,
    Vec<ConversionAction>,
    Vec<UnsupportedIssue>,
);

fn stage_case_dependencies(
    source_root: &Path,
    run_root: &Path,
    text: &str,
    backend: Backend,
) -> Result<StagedCaseDependencies, DirectPortError> {
    let mut created_targets = Vec::new();
    let result =
        stage_case_dependencies_inner(source_root, run_root, text, backend, &mut created_targets);
    let error = match result {
        Ok(value) => return Ok(value),
        Err(error) => error,
    };
    let mut cleanup_failures = Vec::new();
    for target in created_targets.iter().rev() {
        if let Err(cleanup_error) = fs::remove_file(target) {
            cleanup_failures.push(format!("{}: {cleanup_error}", target.display()));
        }
    }
    if cleanup_failures.is_empty() {
        Err(error)
    } else {
        Err(DirectPortError::OutputIo(format!(
            "dependency staging failed: {error}; cleanup failures: {}",
            cleanup_failures.join("; ")
        )))
    }
}

fn stage_case_dependencies_inner(
    source_root: &Path,
    run_root: &Path,
    text: &str,
    backend: Backend,
    created_targets: &mut Vec<PathBuf>,
) -> Result<StagedCaseDependencies, DirectPortError> {
    const MAX_FILES: usize = 4096;
    const MAX_BYTES: u64 = 64 * 1024 * 1024;
    reject_dependency_reparse_chain(source_root)?;
    reject_dependency_reparse_chain(run_root)?;
    let root = source_root
        .canonicalize()
        .map_err(|e| DirectPortError::InputIo(e.to_string()))?;
    let run_root = run_root
        .canonicalize()
        .map_err(|e| DirectPortError::OutputIo(e.to_string()))?;
    let mut queue = audit_deck(text)
        .includes
        .into_iter()
        .map(|reference| (root.clone(), PathBuf::new(), reference))
        .chain(
            audit_deck(text)
                .libraries
                .into_iter()
                .map(|library| (root.clone(), PathBuf::new(), library.path)),
        )
        .collect::<Vec<_>>();
    let mut seen = BTreeSet::new();
    let mut seen_requests = BTreeSet::new();
    let mut staged = Vec::new();
    let mut actions = Vec::new();
    let mut unsupported = Vec::new();
    let mut total = 0u64;
    while let Some((parent, lexical_parent, reference)) = queue.pop() {
        let path = Path::new(&reference);
        if dependency_reference_is_absolute(&reference) {
            unsupported.push(UnsupportedIssue {
                line: redacted_dependency_reference(&reference),
                reason: "absolute_include_path_not_staged".to_owned(),
            });
            continue;
        }
        let lexical_path = match normalized_relative_path(&lexical_parent.join(path)) {
            Ok(path) if !path.as_os_str().is_empty() => path,
            _ => {
                unsupported.push(UnsupportedIssue {
                    line: redacted_dependency_reference(&reference),
                    reason: "include_outside_source_directory".to_owned(),
                });
                continue;
            }
        };
        if dependency_owned_collision(&lexical_path) {
            unsupported.push(UnsupportedIssue {
                line: redacted_dependency_reference(&reference),
                reason: "dependency_output_path_collision".to_owned(),
            });
            continue;
        }
        let candidate = parent.join(path);
        let request_key = candidate.to_string_lossy().into_owned();
        if !seen_requests.insert(request_key) {
            continue;
        }
        if let Err(error) = reject_dependency_reparse_chain(&candidate) {
            unsupported.push(UnsupportedIssue {
                line: redacted_dependency_reference(&reference),
                reason: match error {
                    DirectPortError::UnsupportedExecution(reason) => reason,
                    other => other.to_string(),
                },
            });
            continue;
        }
        let source = match candidate.canonicalize() {
            Ok(source) => source,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                unsupported.push(UnsupportedIssue {
                    line: redacted_dependency_reference(&reference),
                    reason: "include_not_found".to_owned(),
                });
                continue;
            }
            Err(error) => {
                return Err(DirectPortError::UnsupportedExecution(format!(
                    "dependency {reference} is unavailable: {error}"
                )));
            }
        };
        if source.strip_prefix(&root).is_err() {
            unsupported.push(UnsupportedIssue {
                line: redacted_dependency_reference(&reference),
                reason: "include_outside_source_directory".to_owned(),
            });
            continue;
        }
        if !seen.insert(source.clone()) {
            continue;
        }
        if seen.len() > MAX_FILES {
            return Err(DirectPortError::UnsupportedExecution(
                "dependency file budget exceeded".to_owned(),
            ));
        }
        let target = run_root.join(&lexical_path);
        if target.exists() {
            unsupported.push(UnsupportedIssue {
                line: redacted_dependency_reference(&reference),
                reason: "dependency_output_path_collision".to_owned(),
            });
            continue;
        }
        let (source_bytes, source_identity) = read_dependency_once(&source)?;
        total = total
            .checked_add(source_bytes.len() as u64)
            .ok_or_else(|| {
                DirectPortError::UnsupportedExecution("dependency byte budget overflow".to_owned())
            })?;
        if total > MAX_BYTES {
            return Err(DirectPortError::UnsupportedExecution(
                "dependency byte budget exceeded".to_owned(),
            ));
        }
        let nested = String::from_utf8(source_bytes.clone()).map_err(|error| {
            DirectPortError::UnsupportedExecution(format!("dependency is not UTF-8: {error}"))
        })?;
        let safe_nested = redact_deck_text(&nested);
        let (converted_text, nested_actions, nested_unsupported) =
            convert_deck(&safe_nested, backend);
        let staged_text = redact_deck_text(&converted_text);
        actions.extend(nested_actions);
        unsupported.extend(nested_unsupported);
        for directive in audit_deck(&nested).unsupported_directives {
            unsupported.push(UnsupportedIssue {
                line: directive,
                reason: "unsupported_directive_in_dependency".to_owned(),
            });
        }
        let staged_bytes = staged_text.as_bytes();
        let staged_len = u64::try_from(staged_bytes.len()).map_err(|_| {
            DirectPortError::UnsupportedExecution("dependency byte budget overflow".to_owned())
        })?;
        total = total.checked_add(staged_len).ok_or_else(|| {
            DirectPortError::UnsupportedExecution("dependency byte budget overflow".to_owned())
        })?;
        if total > MAX_BYTES {
            return Err(DirectPortError::UnsupportedExecution(
                "dependency source and staged byte budget exceeded".to_owned(),
            ));
        }
        reject_dependency_reparse_chain(target.parent().unwrap_or(&run_root))?;
        let (staged_bytes_len, staged_sha256, _staged_identity) =
            write_dependency_create_new(&target, staged_bytes)?;
        created_targets.push(target.clone());
        let nested_audit = audit_deck(&nested);
        for child in nested_audit.includes {
            queue.push((
                source.parent().unwrap_or(&root).to_path_buf(),
                lexical_path
                    .parent()
                    .unwrap_or(Path::new("."))
                    .to_path_buf(),
                child,
            ));
        }
        for child in nested_audit.libraries {
            queue.push((
                source.parent().unwrap_or(&root).to_path_buf(),
                lexical_path
                    .parent()
                    .unwrap_or(Path::new("."))
                    .to_path_buf(),
                child.path,
            ));
        }
        let lexical = lexical_path.to_string_lossy().replace('\\', "/");
        let source_sha256 = format!("{:x}", Sha256::digest(&source_bytes));
        staged.push(json!({
            "source": lexical,
            "staged": lexical,
            "source_sha256": source_sha256,
            "staged_sha256": staged_sha256,
            "source_bytes": source_identity.bytes,
            "staged_bytes": staged_bytes_len,
        }));
    }
    staged.sort_by(|a, b| a["staged"].as_str().cmp(&b["staged"].as_str()));
    Ok((staged, actions, unsupported))
}

/// The two retained backend selectors supported by this direct port.
///
/// Xyce/XDM existed in the upstream project, but this lane deliberately does
/// not retain those runtime branches.  Keeping the historical variants lets
/// old serialized/request values be diagnosed by the admission boundary
/// without making them executable capabilities.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum Backend {
    Native,
    Ngspice,
    Xyce,
    XyceXdm,
}

impl Backend {
    pub const ALL: [Self; 2] = [Self::Native, Self::Ngspice];

    pub const fn name(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Ngspice => "ngspice",
            Self::Xyce => "xyce",
            Self::XyceXdm => "xyce-xdm",
        }
    }

    pub fn parse(value: &str) -> Result<Self, DirectPortError> {
        match value {
            "native" => Ok(Self::Native),
            "ngspice" => Ok(Self::Ngspice),
            other => Err(DirectPortError::UnsupportedBackend(other.to_owned())),
        }
    }
}

impl Display for Backend {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.name())
    }
}

/// Caller-visible options that affect the upstream branch graph.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceRequest {
    pub backend: Backend,
    pub output_root: PathBuf,
    pub execute: bool,
    pub native_engine: Option<PathBuf>,
    pub rfm: Option<PathBuf>,
    pub rfm_subcircuit: String,
    pub dotnet_executable: String,
}

impl RunHspiceRequest {
    pub fn new(
        backend: &str,
        output_root: impl Into<PathBuf>,
        execute: bool,
    ) -> Result<Self, DirectPortError> {
        let output_root = output_root.into();
        if output_root.as_os_str().is_empty() {
            return Err(DirectPortError::EmptyOutputRoot);
        }
        Ok(Self {
            backend: Backend::parse(backend)?,
            output_root,
            execute,
            native_engine: None,
            rfm: None,
            rfm_subcircuit: "rfm_direct".to_owned(),
            dotnet_executable: "dotnet".to_owned(),
        })
    }

    pub fn with_native_engine(mut self, path: impl Into<PathBuf>) -> Self {
        self.native_engine = Some(path.into());
        self
    }

    pub fn with_rfm(mut self, path: impl Into<PathBuf>, subcircuit: impl Into<String>) -> Self {
        self.rfm = Some(path.into());
        self.rfm_subcircuit = subcircuit.into();
        self
    }

    pub fn with_dotnet(mut self, executable: impl Into<String>) -> Self {
        self.dotnet_executable = executable.into();
        self
    }
}

/// Caller-custodied ngspice runtime identity.  The executable is never
/// resolved through `PATH`; the supplied digest is checked before and after
/// the child process runs.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NgspiceCustody {
    pub executable: PathBuf,
    pub sha256: String,
}

impl NgspiceCustody {
    pub fn new(executable: impl Into<PathBuf>, sha256: impl Into<String>) -> Self {
        Self {
            executable: executable.into(),
            sha256: sha256.into(),
        }
    }
}

/// Stable rejection categories for this admission layer.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DirectPortError {
    UnsupportedBackend(String),
    EmptyOutputRoot,
    EmptyDeckStem,
    ProjectManifestIo(String),
    InvalidProjectManifest(String),
    InputIo(String),
    OutputIo(String),
    UnsupportedExecution(String),
}

impl Display for DirectPortError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnsupportedBackend(value) => write!(formatter, "unsupported backend '{value}'"),
            Self::EmptyOutputRoot => formatter.write_str("output root must not be empty"),
            Self::EmptyDeckStem => formatter.write_str("deck stem must not be empty"),
            Self::ProjectManifestIo(value) => {
                write!(formatter, "project manifest I/O failed: {value}")
            }
            Self::InvalidProjectManifest(value) => {
                write!(formatter, "invalid project manifest: {value}")
            }
            Self::InputIo(value) => write!(formatter, "input I/O failed: {value}"),
            Self::OutputIo(value) => write!(formatter, "output I/O failed: {value}"),
            Self::UnsupportedExecution(value) => {
                write!(formatter, "execution unavailable: {value}")
            }
        }
    }
}

impl std::error::Error for DirectPortError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CaseKind {
    Base,
    Alter,
    Other,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeckCase {
    pub name: String,
    pub text: String,
    pub kind: CaseKind,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LibraryReference {
    pub path: String,
    pub section: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeckAudit {
    pub directive_counts: BTreeMap<String, usize>,
    pub includes: Vec<String>,
    pub libraries: Vec<LibraryReference>,
    pub unsupported_directives: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DependencyAdmission {
    RelativeRequiresSourceRoot,
    AbsoluteNotStaged,
    LexicallyEscapesSourceRoot,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DependencyReference {
    pub reference: String,
    pub admission: DependencyAdmission,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConversionAction {
    pub kind: String,
    pub source: String,
    pub target: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnsupportedIssue {
    pub line: String,
    pub reason: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PreparationStatus {
    Compatible,
    AutoConverted,
    Blocked,
}

impl PreparationStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Compatible => "compatible",
            Self::AutoConverted => "auto_converted",
            Self::Blocked => "blocked",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PreparedCase {
    pub case: DeckCase,
    pub deck_text: String,
    pub audit: DeckAudit,
    pub dependencies: Vec<DependencyReference>,
    pub actions: Vec<ConversionAction>,
    pub unsupported: Vec<UnsupportedIssue>,
    pub preparation_status: PreparationStatus,
    pub output_paths: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecutionStage {
    NotExecuted,
    NativeEngine,
    Ngspice,
    Xyce,
    XdmThenXyce,
}

impl ExecutionStage {
    pub const fn for_request(request: &RunHspiceRequest) -> Self {
        if !request.execute {
            return Self::NotExecuted;
        }
        match request.backend {
            Backend::Native => Self::NativeEngine,
            Backend::Ngspice => Self::Ngspice,
            Backend::Xyce => Self::Xyce,
            Backend::XyceXdm => Self::XdmThenXyce,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceAdmission {
    pub deck_id: String,
    pub backend: Backend,
    pub execute: bool,
    pub execution_stage: ExecutionStage,
    pub cases: Vec<PreparedCase>,
    pub external_solver_required: bool,
    pub numerical_parity: ParityStatus,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ParityStatus {
    NotEvaluated,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RunHspiceResult {
    pub status: PreparationStatus,
    pub output_root: PathBuf,
    pub case_count: usize,
    pub execution_returncodes: Vec<Option<i32>>,
    pub numerical_parity: ParityStatus,
}

/// Build the AS-05 branch plan from the same deck text accepted by upstream.
/// No file is opened and no backend process is launched here.
pub fn admit_run_hspice(
    deck_stem: &str,
    deck_text: &str,
    request: RunHspiceRequest,
) -> Result<RunHspiceAdmission, DirectPortError> {
    if deck_stem.is_empty() {
        return Err(DirectPortError::EmptyDeckStem);
    }
    if matches!(request.backend, Backend::Xyce | Backend::XyceXdm) {
        return Err(DirectPortError::UnsupportedBackend(
            request.backend.name().to_owned(),
        ));
    }
    let cases = split_alter_cases(deck_text, deck_stem);
    let prepared = cases
        .into_iter()
        .map(|case| prepare_case(case, request.backend))
        .collect();
    Ok(RunHspiceAdmission {
        deck_id: deck_stem.to_owned(),
        backend: request.backend,
        execute: request.execute,
        execution_stage: ExecutionStage::for_request(&request),
        cases: prepared,
        external_solver_required: request.execute,
        numerical_parity: ParityStatus::NotEvaluated,
    })
}

/// Execute the portable AS-05 preparation path and, only when explicitly
/// requested with a caller-provided executable, the selected solver branch.
///
/// The function writes source, converted deck, and compatibility JSON for
/// every case.  Dependency staging, runtime identity attestation, and solver
/// waveform parity remain open; unsupported cases are reported as BLOCKED and
/// never turned into successful artifacts.
pub fn run_hspice(
    deck_path: impl AsRef<Path>,
    request: RunHspiceRequest,
) -> Result<RunHspiceResult, DirectPortError> {
    run_hspice_internal(deck_path.as_ref(), request, None)
}

/// Execute the ngspice branch with an explicitly attested caller-owned
/// executable. The ordinary `run_hspice` API deliberately fails closed for
/// ngspice execution because it has no runtime custody parameter.
pub fn run_hspice_with_ngspice_custody(
    deck_path: impl AsRef<Path>,
    request: RunHspiceRequest,
    custody: NgspiceCustody,
) -> Result<RunHspiceResult, DirectPortError> {
    run_hspice_internal(deck_path.as_ref(), request, Some(custody))
}

fn run_hspice_internal(
    deck_path: &Path,
    request: RunHspiceRequest,
    ngspice_custody: Option<NgspiceCustody>,
) -> Result<RunHspiceResult, DirectPortError> {
    let attested_ngspice = if request.execute && request.backend == Backend::Ngspice {
        let custody = ngspice_custody.as_ref().ok_or_else(|| {
            DirectPortError::UnsupportedExecution(
                "ngspice execution requires explicit caller custody".to_owned(),
            )
        })?;
        Some(attest_external_executable(
            &custody.executable,
            Some(&custody.sha256),
            "ngspice",
        )?)
    } else {
        None
    };
    if request.execute && request.backend != Backend::Ngspice {
        return Err(DirectPortError::UnsupportedExecution(
            "only attested ngspice execution is available; other solver custody remains external"
                .to_owned(),
        ));
    }
    let deck_path =
        absolute_path(deck_path).map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    if deck_path
        .metadata()
        .map(|metadata| metadata.len() > MAX_DECK_BYTES)
        .unwrap_or(false)
    {
        return Err(DirectPortError::InputIo(
            "deck exceeds the bounded 16 MiB input budget".to_owned(),
        ));
    }
    let source = fs::read_to_string(&deck_path)
        .map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    let stem = deck_path
        .file_stem()
        .and_then(|value| value.to_str())
        .ok_or(DirectPortError::EmptyDeckStem)?;
    if stem.is_empty() {
        return Err(DirectPortError::EmptyDeckStem);
    }
    fs::create_dir_all(&request.output_root)
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    let output_root = absolute_path(&request.output_root)
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    let rfm = request
        .rfm
        .as_ref()
        .map(|path| absolute_path(path))
        .transpose()
        .map_err(|error| DirectPortError::InputIo(error.to_string()))?;
    let admission = admit_run_hspice(stem, &source, request.clone())?;
    let source_hash = format!("{:x}", Sha256::digest(source.as_bytes()));
    let source_name = stable_source_path(&deck_path, stem);
    let mut returncodes = Vec::with_capacity(admission.cases.len());
    let mut overall_status = PreparationStatus::Compatible;
    let project_root = output_root.join(stem);
    if project_root.exists() {
        return Err(DirectPortError::UnsupportedExecution(
            "run-hspice output project directory must be fresh".to_owned(),
        ));
    }
    for case in &admission.cases {
        let mut case_status = case.preparation_status;
        if case_status == PreparationStatus::Blocked {
            overall_status = PreparationStatus::Blocked;
        } else if case_status == PreparationStatus::AutoConverted
            && overall_status == PreparationStatus::Compatible
        {
            overall_status = PreparationStatus::AutoConverted;
        }
        let directory = output_root.join(stem).join(&case.case.name);
        fs::create_dir_all(directory.parent().unwrap_or_else(|| Path::new(".")))
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        fs::create_dir(&directory).map_err(|error| {
            if error.kind() == std::io::ErrorKind::AlreadyExists {
                DirectPortError::UnsupportedExecution(
                    "run-hspice case execution directory must be fresh".to_owned(),
                )
            } else {
                DirectPortError::OutputIo(error.to_string())
            }
        })?;
        let (runtime_deck, sparam_actions, sparam_unsupported) =
            if admission.backend == Backend::Ngspice {
                compile_touchstone_s_elements(
                    &case.deck_text,
                    deck_path.parent().unwrap_or_else(|| Path::new(".")),
                    &directory,
                )?
            } else {
                (case.deck_text.clone(), Vec::new(), Vec::new())
            };
        if !sparam_unsupported.is_empty() {
            case_status = PreparationStatus::Blocked;
            overall_status = PreparationStatus::Blocked;
        } else if !sparam_actions.is_empty() && case_status == PreparationStatus::Compatible {
            case_status = PreparationStatus::AutoConverted;
            if overall_status == PreparationStatus::Compatible {
                overall_status = PreparationStatus::AutoConverted;
            }
        }
        let safe_case_text = redact_deck_text(&case.case.text);
        let safe_runtime_deck = redact_deck_text(&runtime_deck);
        let safe_audit = redacted_audit(&case.audit);
        fs::write(directory.join("case.source.sp"), &safe_case_text)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        fs::write(directory.join("case.cir"), &safe_runtime_deck)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        if admission.backend == Backend::XyceXdm {
            fs::write(directory.join("case.sp"), &safe_case_text)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        }
        let (staged_dependencies, dependency_actions, dependency_unsupported) =
            stage_case_dependencies(
                deck_path.parent().unwrap_or_else(|| Path::new(".")),
                &directory,
                &case.case.text,
                admission.backend,
            )?;
        if !dependency_unsupported.is_empty() {
            case_status = PreparationStatus::Blocked;
            overall_status = PreparationStatus::Blocked;
        } else if !dependency_actions.is_empty() && case_status == PreparationStatus::Compatible {
            case_status = PreparationStatus::AutoConverted;
            if overall_status == PreparationStatus::Compatible {
                overall_status = PreparationStatus::AutoConverted;
            }
        }
        let safe_actions = case
            .actions
            .iter()
            .chain(&sparam_actions)
            .chain(&dependency_actions)
            .map(|action| {
                json!({
                    "kind": action.kind,
                    "source": redact_deck_line(&action.source),
                    "target": redact_deck_line(&action.target),
                })
            })
            .collect::<Vec<_>>();
        let safe_unsupported = case
            .audit
            .unsupported_directives
            .iter()
            .map(|line| json!({"line": line, "reason": "unsupported_directive"}))
            .chain(case.unsupported.iter().chain(&sparam_unsupported).chain(&dependency_unsupported).map(|issue| {
                json!({"line": redact_deck_line(&issue.line), "reason": issue.reason})
            }))
            .collect::<Vec<_>>();
        fs::write(
            directory.join("dependencies.json"),
            serde_json::to_string_pretty(&staged_dependencies)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                + "\n",
        )
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        let case_source_sha = file_sha256(&directory.join("case.source.sp"))?;
        let prepared_sha = file_sha256(&directory.join("case.cir"))?;
        let compatibility = json!({
            "schema": "sipi.agent-spice-as-05-compatibility-report.v2",
            "schema_version": 2,
            "case": {"name": case.case.name, "kind": match case.case.kind { CaseKind::Base => "base", CaseKind::Alter => "alter", CaseKind::Other => "other" }},
            "backend": admission.backend.name(),
            "status": case_status.as_str(),
            "deck": {"id": stem, "source": source_name, "sha256": source_hash, "case_source": "case.source.sp", "case_source_sha256": case_source_sha, "prepared": "case.cir", "prepared_sha256": prepared_sha},
            "audit": {"directive_counts": safe_audit.directive_counts, "includes": safe_audit.includes, "libraries": safe_audit.libraries.iter().map(|library| json!([library.path, library.section])).collect::<Vec<_>>(), "unsupported_directives": safe_audit.unsupported_directives},
            "outputs": {"probes": output_probes(&case.case.text), "measures": output_measures(&case.case.text)},
            "actions": safe_actions,
            "unsupported": safe_unsupported,
            "dependencies": staged_dependencies,
            "summary": {"status": case_status.as_str(), "rewrites": case.actions.len() + sparam_actions.len() + dependency_actions.len(), "drops": case.actions.iter().chain(&dependency_actions).filter(|action| action.kind == "drop_option").count(), "unsupported": case.unsupported.len() + sparam_unsupported.len() + dependency_unsupported.len() + case.audit.unsupported_directives.len()},
        });
        let report_text = serde_json::to_string_pretty(&compatibility)
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        fs::write(directory.join("compat_report.json"), report_text + "\n")
            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        if !sparam_actions.is_empty()
            || !sparam_unsupported.is_empty()
            || !dependency_actions.is_empty()
            || !dependency_unsupported.is_empty()
        {
            let mut preflight = sparam_actions
                .iter()
                .map(|action| {
                    format!(
                        "{}: {} -> {}",
                        action.kind,
                        redact_deck_line(&action.source),
                        redact_deck_line(&action.target)
                    )
                })
                .collect::<Vec<_>>();
            preflight.extend(dependency_actions.iter().map(|action| {
                format!(
                    "dependency {}: {} -> {}",
                    action.kind,
                    redact_deck_line(&action.source),
                    redact_deck_line(&action.target)
                )
            }));
            preflight.extend(sparam_unsupported.iter().map(|issue| {
                format!(
                    "BLOCKED: {} ({})",
                    redact_deck_line(&issue.line),
                    issue.reason
                )
            }));
            preflight.extend(dependency_unsupported.iter().map(|issue| {
                format!(
                    "BLOCKED: dependency {} ({})",
                    redact_deck_line(&issue.line),
                    issue.reason
                )
            }));
            fs::write(directory.join("preflight.log"), preflight.join("\n") + "\n")
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
        }

        let returncode = if request.execute
            && case_status != PreparationStatus::Blocked
            && sparam_unsupported.is_empty()
        {
            let (program, args): (PathBuf, Vec<PathBuf>) = match admission.backend {
                Backend::Native => {
                    let engine = request
                        .native_engine
                        .as_ref()
                        .map(|path| absolute_path(path))
                        .transpose()
                        .map_err(|error| DirectPortError::InputIo(error.to_string()))?
                        .ok_or_else(|| {
                            DirectPortError::UnsupportedExecution(
                                "native backend requires --native-engine".to_owned(),
                            )
                        })?;
                    let mut args = Vec::new();
                    let program = if engine
                        .extension()
                        .is_some_and(|value| value.eq_ignore_ascii_case("dll"))
                    {
                        args.push(engine);
                        PathBuf::from(&request.dotnet_executable)
                    } else {
                        engine
                    };
                    args.extend([
                        directory.join("case.cir"),
                        PathBuf::from("--waveform-csv"),
                        directory.join("waveform.csv"),
                        PathBuf::from("--output-json"),
                        directory.join("native_result.json"),
                    ]);
                    if let Some(rfm) = &rfm {
                        args.push(PathBuf::from("--rfm"));
                        args.push(rfm.clone());
                        args.push(PathBuf::from("--rfm-subckt"));
                        args.push(PathBuf::from(&request.rfm_subcircuit));
                    }
                    (program, args)
                }
                Backend::Ngspice => (
                    attested_ngspice
                        .as_ref()
                        .expect("attested ngspice was checked before dispatch")
                        .0
                        .clone(),
                    vec![
                        PathBuf::from("-n"),
                        PathBuf::from("-b"),
                        PathBuf::from("case.cir"),
                        PathBuf::from("-o"),
                        PathBuf::from("case"),
                    ],
                ),
                Backend::Xyce => (PathBuf::from("Xyce"), vec![directory.join("case.cir")]),
                Backend::XyceXdm => (
                    PathBuf::from("xdm_bdl"),
                    vec![
                        PathBuf::from("-s"),
                        PathBuf::from("hspice"),
                        PathBuf::from("-d"),
                        directory.join("xdm-out"),
                        PathBuf::from("-o"),
                        PathBuf::from("xyce"),
                        directory.join("case.sp"),
                    ],
                ),
            };
            let transcript_path = directory.join("case");
            if admission.backend == Backend::Ngspice
                && (transcript_path.exists() || directory.join("waveform.csv").exists())
            {
                return Err(DirectPortError::UnsupportedExecution(
                    "ngspice output directory contains pre-existing result artifacts".to_owned(),
                ));
            }
            let transcript_before = external_file_stamp(&transcript_path);
            let waveform_before = external_file_stamp(&directory.join("waveform.csv"));
            let executable_before = if admission.backend == Backend::Ngspice {
                Some((external_file_stamp(&program), file_sha256(&program)?))
            } else {
                None
            };
            let output = run_external_process(&program, &args, &directory)?;
            if let Some((before_stamp, before_sha256)) = executable_before {
                let after_stamp = external_file_stamp(&program);
                let after_sha256 = file_sha256(&program)?;
                if after_stamp != before_stamp || after_sha256 != before_sha256 {
                    return Err(DirectPortError::UnsupportedExecution(
                        "external solver identity changed during execution".to_owned(),
                    ));
                }
            }
            if admission.backend == Backend::Ngspice
                && !external_artifact_changed(&transcript_path, transcript_before)
            {
                return Err(DirectPortError::UnsupportedExecution(
                    "ngspice completed without a fresh bounded transcript".to_owned(),
                ));
            }
            if admission.backend == Backend::Ngspice
                && fs::metadata(&transcript_path)
                    .map(|metadata| metadata.len() as usize > MAX_EXTERNAL_TRANSCRIPT_BYTES)
                    .unwrap_or(true)
            {
                return Err(DirectPortError::UnsupportedExecution(
                    "ngspice transcript exceeds the bounded 8 MiB artifact budget".to_owned(),
                ));
            }
            fs::write(directory.join("stdout.log"), &output.stdout)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
            fs::write(directory.join("stderr.log"), &output.stderr)
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
            if admission.backend == Backend::XyceXdm {
                fs::write(directory.join("xdm.stdout.log"), &output.stdout)
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                fs::write(directory.join("xdm.stderr.log"), &output.stderr)
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                let generated = directory.join("xdm-out").join("case.sp");
                let xdm_returncode = output.status.code().unwrap_or(-1);
                if !output.status.success() {
                    let summary = json!({
                        "schema_version": 1,
                        "backend": "xyce-xdm",
                        "ok": false,
                        "returncode": xdm_returncode,
                        "stages": {
                            "xdm": {"ok": false, "returncode": xdm_returncode, "stdout": "xdm.stdout.log", "stderr": "xdm.stderr.log"},
                            "xyce": null,
                        },
                    });
                    fs::write(
                        directory.join("run_summary.json"),
                        serde_json::to_string_pretty(&summary)
                            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                            + "\n",
                    )
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    Some(xdm_returncode)
                } else if !generated.is_file() {
                    let message = format!(
                        "xdm_bdl completed without a generated Xyce deck: {}",
                        generated.display()
                    );
                    fs::write(directory.join("xdm.stderr.log"), &message)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    let summary = json!({
                        "schema_version": 1,
                        "backend": "xyce-xdm",
                        "ok": false,
                        "returncode": 1,
                        "stages": {
                            "xdm": {"ok": false, "returncode": 1, "stdout": "xdm.stdout.log", "stderr": "xdm.stderr.log"},
                            "xyce": null,
                        },
                    });
                    fs::write(
                        directory.join("run_summary.json"),
                        serde_json::to_string_pretty(&summary)
                            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                            + "\n",
                    )
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    Some(1)
                } else {
                    // The upstream XDM backend feeds `case.sp` and receives
                    // a generated deck with the same basename before Xyce.
                    let xyce_deck = directory.join("case.cir");
                    fs::copy(&generated, &xyce_deck)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    let xyce = Command::new("Xyce")
                        .arg(&xyce_deck)
                        .current_dir(&directory)
                        .output()
                        .map_err(|error| {
                            DirectPortError::UnsupportedExecution(error.to_string())
                        })?;
                    fs::write(directory.join("xyce.stdout.log"), &xyce.stdout)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    fs::write(directory.join("xyce.stderr.log"), &xyce.stderr)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    let summary = json!({
                        "schema_version": 1,
                        "backend": "xyce-xdm",
                        "ok": xyce.status.success(),
                        "returncode": xyce.status.code().unwrap_or(-1),
                        "stages": {
                            "xdm": {"ok": true, "returncode": xdm_returncode, "stdout": "xdm.stdout.log", "stderr": "xdm.stderr.log"},
                            "xyce": {"ok": xyce.status.success(), "returncode": xyce.status.code().unwrap_or(-1), "stdout": "xyce.stdout.log", "stderr": "xyce.stderr.log"},
                        },
                    });
                    fs::write(
                        directory.join("run_summary.json"),
                        serde_json::to_string_pretty(&summary)
                            .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                            + "\n",
                    )
                    .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                    Some(xyce.status.code().unwrap_or(-1))
                }
            } else {
                let error_text = if output.status.success() {
                    serde_json::Value::Null
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    let stdout = String::from_utf8_lossy(&output.stdout);
                    serde_json::Value::String(if !stderr.trim().is_empty() {
                        stderr.trim().to_owned()
                    } else if !stdout.trim().is_empty() {
                        stdout.trim().to_owned()
                    } else {
                        "backend failed without output".to_owned()
                    })
                };
                let mut summary = json!({"schema_version":1,"backend":admission.backend.name(),"returncode":output.status.code(),"ok":output.status.success(),"logs":{"stdout":"stdout.log","stderr":"stderr.log"},"waveform":null,"measurements":[],"error":error_text});
                if let Some((solver, solver_sha256)) = &attested_ngspice {
                    summary["external_runtime"] = json!({
                        "basename": solver.file_name().and_then(|value| value.to_str()).unwrap_or("ngspice"),
                        "sha256": solver_sha256,
                        "path_redacted": true,
                        "timeout_seconds": EXTERNAL_TIMEOUT.as_secs(),
                        "pipe_output_budget_bytes": MAX_EXTERNAL_PIPE_BYTES,
                        "transcript_budget_bytes": MAX_EXTERNAL_TRANSCRIPT_BYTES,
                        "combined_parse_budget_bytes": MAX_EXTERNAL_COMBINED_PARSE_BYTES,
                        "custody": "caller_custody",
                        "writer_safety": "non_hostile_writer_safe",
                        "identity_check": "absolute_regular_non_symlink_sha256_attested_process_identity_rechecked",
                        "sandbox": "none_external_process",
                    });
                }
                let backend_text = if admission.backend == Backend::Ngspice {
                    let mut text = String::from_utf8(output.stdout.clone()).map_err(|error| {
                        DirectPortError::UnsupportedExecution(format!(
                            "ngspice stdout is not valid UTF-8: {error}"
                        ))
                    })?;
                    let transcript = directory.join("case");
                    if transcript.is_file() {
                        let transcript_bytes = fs::metadata(&transcript)
                            .map_err(|error| DirectPortError::InputIo(error.to_string()))?
                            .len()
                            .try_into()
                            .map_err(|_| {
                                DirectPortError::UnsupportedExecution(
                                    "ngspice transcript size does not fit the bounded parser budget"
                                        .to_owned(),
                                )
                            })?;
                        if transcript_bytes > MAX_EXTERNAL_TRANSCRIPT_BYTES {
                            return Err(DirectPortError::UnsupportedExecution(
                                "ngspice transcript exceeds the bounded 8 MiB artifact budget"
                                    .to_owned(),
                            ));
                        }
                        let combined_bytes = text
                            .len()
                            .checked_add(transcript_bytes)
                            .and_then(|value| value.checked_add(usize::from(!text.is_empty())))
                            .ok_or_else(|| {
                                DirectPortError::UnsupportedExecution(
                                    "ngspice combined parse size overflows the bounded budget"
                                        .to_owned(),
                                )
                            })?;
                        if combined_bytes > MAX_EXTERNAL_COMBINED_PARSE_BYTES {
                            return Err(DirectPortError::UnsupportedExecution(
                                "ngspice stdout/transcript combined parse exceeds the bounded 16 MiB budget"
                                    .to_owned(),
                            ));
                        }
                        let value = fs::read_to_string(transcript)
                            .map_err(|error| DirectPortError::InputIo(error.to_string()))?;
                        if !text.is_empty() {
                            text.push('\n');
                        }
                        text.push_str(&value);
                    }
                    text
                } else {
                    String::from_utf8_lossy(&output.stdout).into_owned()
                };
                if admission.backend == Backend::Ngspice {
                    let waveform = directory.join("waveform.csv");
                    let waveform_payload = parse_ngspice_waveform(&backend_text)?;
                    let requested_probes = output_probes(&case.case.text);
                    validate_ngspice_waveform_columns(
                        waveform_payload.as_ref(),
                        &requested_probes,
                    )?;
                    let rows = write_ngspice_waveform_csv(waveform_payload.as_ref(), &waveform)?;
                    if rows == 0 {
                        if waveform.exists() {
                            fs::remove_file(&waveform)
                                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                        }
                    } else if !external_artifact_changed(&waveform, waveform_before) {
                        return Err(DirectPortError::UnsupportedExecution(
                            "ngspice waveform artifact is not fresh".to_owned(),
                        ));
                    }
                    if !requested_probes.is_empty() && rows == 0 {
                        return Err(DirectPortError::UnsupportedExecution(
                            "ngspice returned no waveform for requested probes".to_owned(),
                        ));
                    }
                    let requested_measures = output_measures(&case.case.text);
                    let measurements = parse_ngspice_measurements(&backend_text);
                    validate_ngspice_measurements(&requested_measures, &measurements)?;
                    summary["waveform"] = if rows > 0 {
                        json!({"kind":"ngspice_print_table_observation","path":"waveform.csv","format":"csv","exists":true,"rows":rows})
                    } else {
                        serde_json::Value::Null
                    };
                    summary["measurements"] = json!(measurements);
                    summary["output_contract"] = json!({
                        "normalizer": {
                            "upstream_path": "src/agent_spice/hspice/measure.py::normalize_outputs",
                            "upstream_sha256": UPSTREAM_MEASURE_SOURCE_SHA256,
                        },
                        "requested": {"probes": requested_probes, "measures": requested_measures},
                        "returned": {"waveform_rows": rows, "measurements": summary["measurements"]},
                        "result_kind": "ngspice_print_table_observation",
                        "verification": "external_solver_not_verified",
                        "caller_input_attestation": "caller_input_unattested",
                    });
                    let mut artifacts = vec![
                        external_artifact_record(&transcript_path, "case")?,
                        external_artifact_record(&directory.join("stdout.log"), "stdout.log")?,
                        external_artifact_record(&directory.join("stderr.log"), "stderr.log")?,
                    ];
                    if rows > 0 {
                        artifacts.push(external_artifact_record(&waveform, "waveform.csv")?);
                    }
                    summary["artifacts"] = json!(artifacts);
                }
                if admission.backend == Backend::Native {
                    let result_path = directory.join("native_result.json");
                    if output.status.success() && !result_path.is_file() {
                        return Err(DirectPortError::UnsupportedExecution(
                            "native engine returned success without native_result.json".to_owned(),
                        ));
                    }
                    if output.status.success() && result_path.is_file() {
                        let result: serde_json::Value = serde_json::from_slice(
                            &fs::read(&result_path)
                                .map_err(|error| DirectPortError::InputIo(error.to_string()))?,
                        )
                        .map_err(|error| {
                            DirectPortError::UnsupportedExecution(format!(
                                "native result JSON is invalid: {error}"
                            ))
                        })?;
                        if !result.is_object() {
                            return Err(DirectPortError::UnsupportedExecution(
                                "native result must be a JSON object".to_owned(),
                            ));
                        }
                        let waveform_rows = result
                            .get("waveformRows")
                            .and_then(serde_json::Value::as_u64)
                            .unwrap_or(0);
                        summary["waveform"] = json!({
                            "path": "waveform.csv",
                            "format": "csv",
                            "exists": directory.join("waveform.csv").is_file(),
                            "rows": waveform_rows,
                        });
                        if let Some(measurements) = result.get("measurements")
                            && measurements.is_array()
                        {
                            summary["measurements"] = measurements.clone();
                        }
                        summary["native_result"] = json!({
                            "path": "native_result.json",
                            "exists": true,
                        });
                    }
                    if !summary
                        .get("native_result")
                        .is_some_and(|value| value.is_object())
                    {
                        summary["native_result"] = json!({
                            "path": "native_result.json",
                            "exists": result_path.is_file(),
                        });
                    }
                }
                fs::write(
                    directory.join("run_summary.json"),
                    serde_json::to_string_pretty(&summary)
                        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?
                        + "\n",
                )
                .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
                Some(output.status.code().unwrap_or(-1))
            }
        } else {
            None
        };
        returncodes.push(returncode);
        if returncode.is_some_and(|code| code != 0) {
            overall_status = PreparationStatus::Blocked;
        }
    }
    let run_report = json!({
        "schema": "sipi.agent-spice-as-05-run-hspice-result.v2",
        "schema_version": 2,
        "workflow": WORKFLOW_NAME,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_tree": UPSTREAM_TREE,
        "backend": request.backend.name(),
        "execute": request.execute,
        "status": overall_status.as_str(),
        "case_count": admission.cases.len(),
        "execution_returncodes": returncodes,
        "numerical_parity": "not_evaluated",
        "portable_branches": ["alter-case-splitting", "quoted-comment-and-continuation-audit", "recursive-dependency-staging", "ngspice-conversion", "measure/probe-contract", "native-result-validation", "xdm-two-stage-dispatch"],
        "external_runtime_boundary": ["native-engine", "ngspice", "Xyce", "xdm_bdl"],
    });
    let report_text = serde_json::to_string_pretty(&run_report)
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    fs::write(project_root.join("run_report.json"), report_text + "\n")
        .map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    Ok(RunHspiceResult {
        status: overall_status,
        output_root,
        case_count: admission.cases.len(),
        execution_returncodes: returncodes,
        numerical_parity: ParityStatus::NotEvaluated,
    })
}

/// Resolve and dispatch the upstream project-manifest branch through the
/// same deck/backend/result contract as the direct deck entry point.
pub fn run_hspice_project(
    manifest_path: impl AsRef<Path>,
    execute: bool,
    native_engine: Option<PathBuf>,
) -> Result<RunHspiceResult, DirectPortError> {
    let manifest_path = absolute_path(manifest_path.as_ref())
        .map_err(|error| DirectPortError::ProjectManifestIo(error.to_string()))?;
    let manifest = ProjectManifest::from_yaml(&manifest_path)?;
    let manifest_dir = manifest_path.parent().unwrap_or_else(|| Path::new("."));
    let deck = manifest.hspice_deck.ok_or_else(|| {
        DirectPortError::InvalidProjectManifest(
            "inputs.hspice_deck is required for run-hspice project dispatch".to_owned(),
        )
    })?;
    let deck = if deck.is_absolute() {
        deck
    } else {
        manifest_dir.join(deck)
    };
    let output_root = if manifest.output_root.is_absolute() {
        manifest.output_root
    } else {
        manifest_dir.join(manifest.output_root)
    };
    let mut request = RunHspiceRequest::new(manifest.backend.name(), output_root, execute)?;
    request.native_engine = native_engine;
    run_hspice(deck, request)
}

fn output_probes(text: &str) -> Vec<String> {
    let mut probes = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('*') {
            continue;
        }
        let parts = line.split_whitespace().collect::<Vec<_>>();
        let Some(directive) = parts.first() else {
            continue;
        };
        if matches!(directive.to_ascii_lowercase().as_str(), ".probe" | ".print")
            && parts.len() >= 3
        {
            probes.extend(parts[2..].iter().map(|value| (*value).to_owned()));
        }
    }
    probes
}

fn stable_source_path(deck_path: &Path, stem: &str) -> String {
    let fallback = deck_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or(stem)
        .to_owned();
    let Ok(current) = std::env::current_dir() else {
        return fallback;
    };
    let Ok(relative) = deck_path.strip_prefix(current) else {
        return fallback;
    };
    let value = relative.to_string_lossy().replace('\\', "/");
    if value.is_empty() { fallback } else { value }
}

fn output_measures(text: &str) -> Vec<serde_json::Value> {
    let mut measures = Vec::new();
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('*') {
            continue;
        }
        let parts = line.split_whitespace().collect::<Vec<_>>();
        let Some(directive) = parts.first() else {
            continue;
        };
        if !matches!(
            directive.to_ascii_lowercase().as_str(),
            ".measure" | ".meas"
        ) || parts.len() < 4
        {
            continue;
        }
        let operation_token = parts[3];
        let mut operation = operation_token.to_ascii_lowercase();
        let target = if operation.starts_with("param=") {
            operation = "param".to_owned();
            operation_token
                .split_once('=')
                .map(|(_, value)| value.to_owned())
        } else if operation == "param" {
            if parts.len() >= 6 && parts[4] == "=" {
                Some(parts[5].to_owned())
            } else {
                parts.get(4).map(|value| (*value).to_owned())
            }
        } else {
            parts.get(4).map(|value| (*value).to_owned())
        };
        let Some(target) = target else {
            continue;
        };
        measures.push(json!({
            "analysis": parts[1].to_ascii_lowercase(),
            "name": parts[2],
            "operation": operation,
            "target": target,
            "raw": line,
        }));
    }
    measures
}

fn canonical_ascii_key(value: &str) -> String {
    value
        .bytes()
        .map(|byte| byte.to_ascii_lowercase())
        .map(char::from)
        .collect()
}

fn measurement_name_char(value: char, first: bool) -> bool {
    if first {
        value.is_ascii_alphabetic() || value == '_'
    } else {
        value.is_alphanumeric() || matches!(value, '_' | '.' | '$' | '-')
    }
}

fn parse_measurement_number(value: &str) -> Option<(f64, usize)> {
    let bytes = value.as_bytes();
    let mut index = usize::from(
        bytes
            .first()
            .is_some_and(|byte| matches!(byte, b'+' | b'-')),
    );
    let integer_start = index;
    while bytes.get(index).is_some_and(u8::is_ascii_digit) {
        index += 1;
    }
    let integer_digits = index - integer_start;
    let fraction_digits = if bytes.get(index) == Some(&b'.') {
        index += 1;
        let start = index;
        while bytes.get(index).is_some_and(u8::is_ascii_digit) {
            index += 1;
        }
        index - start
    } else {
        0
    };
    if integer_digits == 0 && fraction_digits == 0 {
        return None;
    }
    if bytes
        .get(index)
        .is_some_and(|byte| matches!(byte, b'e' | b'E'))
    {
        index += 1;
        if bytes
            .get(index)
            .is_some_and(|byte| matches!(byte, b'+' | b'-'))
        {
            index += 1;
        }
        let start = index;
        while bytes.get(index).is_some_and(u8::is_ascii_digit) {
            index += 1;
        }
        if index == start {
            return None;
        }
    }
    let number = value.get(..index)?.parse::<f64>().ok()?;
    number.is_finite().then_some((number, index))
}

fn parse_ngspice_measurement_line(line: &str) -> Option<(String, f64, Option<f64>)> {
    let line = line.trim();
    let mut name_end = 0;
    for (index, character) in line.char_indices() {
        if !measurement_name_char(character, index == 0) {
            break;
        }
        name_end = index + character.len_utf8();
    }
    if name_end == 0 {
        return None;
    }
    let name = line.get(..name_end)?.to_owned();
    let mut rest = line.get(name_end..)?.trim_start();
    rest = rest.strip_prefix('=')?.trim_start();
    let (value, consumed) = parse_measurement_number(rest)?;
    let tail = rest.get(consumed..)?;
    if tail.is_empty() {
        return Some((name, value, None));
    }
    if !tail.chars().next()?.is_whitespace() {
        return None;
    }
    rest = tail.trim_start().strip_prefix("at=")?.trim_start();
    let (at, consumed) = parse_measurement_number(rest)?;
    rest = rest.get(consumed..)?.trim();
    rest.is_empty().then_some((name, value, Some(at)))
}

fn parse_ngspice_measurements(text: &str) -> Vec<serde_json::Value> {
    text.lines()
        .filter_map(parse_ngspice_measurement_line)
        .map(|(name, value, at)| {
            let mut entry = json!({"name": name, "value": value});
            if let Some(at) = at {
                entry["at"] = json!(at);
            }
            entry
        })
        .collect()
}

fn validate_ngspice_measurements(
    requested: &[serde_json::Value],
    returned: &[serde_json::Value],
) -> Result<(), DirectPortError> {
    if requested.len() != returned.len() {
        return Err(DirectPortError::UnsupportedExecution(format!(
            "ngspice returned {} measurements for {} requested measures",
            returned.len(),
            requested.len()
        )));
    }
    let expected = requested
        .iter()
        .filter_map(|value| value.get("name").and_then(serde_json::Value::as_str))
        .map(canonical_ascii_key)
        .collect::<BTreeSet<_>>();
    if expected.len() != requested.len() {
        return Err(DirectPortError::UnsupportedExecution(
            "duplicate requested measurement names are not supported".to_owned(),
        ));
    }
    let mut seen = BTreeSet::new();
    for value in returned {
        let name = value
            .get("name")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| {
                DirectPortError::UnsupportedExecution(
                    "ngspice returned a measurement without a name".to_owned(),
                )
            })?;
        let canonical_name = canonical_ascii_key(name);
        if !expected.contains(&canonical_name) || !seen.insert(canonical_name) {
            return Err(DirectPortError::UnsupportedExecution(format!(
                "ngspice returned an unknown or duplicate measurement '{name}'"
            )));
        }
        let number = value
            .get("value")
            .and_then(serde_json::Value::as_f64)
            .ok_or_else(|| {
                DirectPortError::UnsupportedExecution(format!(
                    "ngspice measurement '{name}' is not numeric"
                ))
            })?;
        if !number.is_finite()
            || value
                .get("at")
                .and_then(serde_json::Value::as_f64)
                .is_some_and(|at| !at.is_finite())
        {
            return Err(DirectPortError::UnsupportedExecution(format!(
                "ngspice measurement '{name}' is non-finite"
            )));
        }
    }
    Ok(())
}

#[derive(Debug)]
struct NgspiceWaveform {
    columns: Vec<String>,
    rows: Vec<Vec<f64>>,
}

#[derive(Debug)]
struct NgspiceWaveformBlock {
    columns: Vec<String>,
    indices: Vec<u64>,
    rows: Vec<Vec<f64>>,
}

fn canonical_waveform_key(value: &str) -> String {
    let canonical = canonical_ascii_key(value);
    if let Some(value) = canonical
        .strip_prefix("i(")
        .and_then(|value| value.strip_suffix(')'))
    {
        format!("{value}#branch")
    } else {
        canonical
    }
}

fn parse_ngspice_waveform(text: &str) -> Result<Option<NgspiceWaveform>, DirectPortError> {
    let mut blocks = Vec::<NgspiceWaveformBlock>::new();
    let mut current = None;
    for line in text.lines() {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        if fields
            .first()
            .is_some_and(|value| value.eq_ignore_ascii_case("index"))
            && fields.len() >= 3
        {
            let candidate = fields[1..]
                .iter()
                .map(|field| (*field).to_owned())
                .collect::<Vec<_>>();
            if current
                .as_ref()
                .is_some_and(|block: &NgspiceWaveformBlock| {
                    block.columns.len() != candidate.len()
                        || block.columns.iter().zip(&candidate).any(|(left, right)| {
                            canonical_ascii_key(left) != canonical_ascii_key(right)
                        })
                })
            {
                if let Some(block) = current.take()
                    && !block.rows.is_empty()
                {
                    blocks.push(block);
                }
                current = Some(NgspiceWaveformBlock {
                    columns: candidate,
                    indices: Vec::new(),
                    rows: Vec::new(),
                });
            } else if current.is_none() {
                current = Some(NgspiceWaveformBlock {
                    columns: candidate,
                    indices: Vec::new(),
                    rows: Vec::new(),
                });
            }
            continue;
        }
        let Some(block) = current.as_mut() else {
            continue;
        };
        if fields.len() != block.columns.len() + 1
            || fields
                .first()
                .is_none_or(|value| !value.chars().all(|character| character.is_ascii_digit()))
        {
            continue;
        }
        let index = fields[0].parse::<u64>().map_err(|error| {
            DirectPortError::UnsupportedExecution(format!(
                "ngspice waveform index is not an integer: {error}"
            ))
        })?;
        if block
            .indices
            .last()
            .is_some_and(|previous| index <= *previous)
        {
            return Err(DirectPortError::UnsupportedExecution(
                "ngspice print table contains conflicting waveform headers".to_owned(),
            ));
        }
        let values = fields[1..]
            .iter()
            .map(|value| value.parse::<f64>())
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| {
                DirectPortError::UnsupportedExecution(format!(
                    "ngspice waveform contains a non-numeric value: {error}"
                ))
            })?;
        if values.iter().any(|value| !value.is_finite()) {
            return Err(DirectPortError::UnsupportedExecution(
                "ngspice waveform contains a non-finite value".to_owned(),
            ));
        }
        block.indices.push(index);
        block.rows.push(values);
    }
    if let Some(block) = current
        && !block.rows.is_empty()
    {
        blocks.push(block);
    }
    let Some(first) = blocks.first() else {
        return Ok(None);
    };
    let axis = canonical_waveform_key(first.columns.first().map_or("", String::as_str));
    if axis.is_empty() {
        return Err(DirectPortError::UnsupportedExecution(
            "ngspice print table is missing its axis column".to_owned(),
        ));
    }
    let mut columns = first.columns.clone();
    let mut rows = first.rows.clone();
    let indices = &first.indices;
    let axis_values = first
        .rows
        .iter()
        .map(|row| row[0].to_bits())
        .collect::<Vec<_>>();
    for block in blocks.iter().skip(1) {
        if block.indices != *indices
            || canonical_waveform_key(block.columns.first().map_or("", String::as_str)) != axis
            || block
                .rows
                .iter()
                .map(|row| row[0].to_bits())
                .ne(axis_values.iter().copied())
        {
            return Err(DirectPortError::UnsupportedExecution(
                "ngspice print table contains conflicting waveform headers".to_owned(),
            ));
        }
        for value in block.columns.iter().skip(1) {
            columns.push(value.clone());
        }
        for (row, block_row) in rows.iter_mut().zip(&block.rows) {
            row.extend_from_slice(&block_row[1..]);
        }
    }
    Ok(Some(NgspiceWaveform { columns, rows }))
}

fn validate_ngspice_waveform_columns(
    waveform: Option<&NgspiceWaveform>,
    requested: &[String],
) -> Result<(), DirectPortError> {
    let Some(waveform) = waveform else {
        return if requested.is_empty() {
            Ok(())
        } else {
            Err(DirectPortError::UnsupportedExecution(
                "ngspice returned no waveform header for requested probes".to_owned(),
            ))
        };
    };
    let expected = requested
        .iter()
        .map(|value| canonical_waveform_key(value))
        .collect::<BTreeSet<_>>();
    if expected.len() != requested.len() {
        return Err(DirectPortError::UnsupportedExecution(
            "duplicate requested waveform probes are not supported".to_owned(),
        ));
    }
    let expected_columns = requested.len().checked_add(1).ok_or_else(|| {
        DirectPortError::UnsupportedExecution(
            "requested waveform probe count overflows the bounded column contract".to_owned(),
        )
    })?;
    if waveform.columns.len() != expected_columns {
        return Err(DirectPortError::UnsupportedExecution(
            "ngspice print table column count does not match requested probes".to_owned(),
        ));
    }
    let Some(axis) = waveform.columns.first() else {
        return Err(DirectPortError::UnsupportedExecution(
            "ngspice print table is missing its axis column".to_owned(),
        ));
    };
    if axis.is_empty() {
        return Err(DirectPortError::UnsupportedExecution(
            "ngspice print table axis column is empty".to_owned(),
        ));
    }
    let returned = waveform
        .columns
        .iter()
        .skip(1)
        .map(|value| canonical_waveform_key(value))
        .collect::<BTreeSet<_>>();
    if returned.len() != requested.len() || returned != expected {
        return Err(DirectPortError::UnsupportedExecution(
            "ngspice waveform columns do not match requested probes".to_owned(),
        ));
    }
    Ok(())
}

fn write_ngspice_waveform_csv(
    waveform: Option<&NgspiceWaveform>,
    path: &Path,
) -> Result<usize, DirectPortError> {
    let Some(waveform) = waveform else {
        return Ok(0);
    };
    let mut csv = waveform.columns.join(",");
    csv.push('\n');
    for row in &waveform.rows {
        csv.push_str(
            &row.iter()
                .map(|value| format!("{value:.17e}"))
                .collect::<Vec<_>>()
                .join(","),
        );
        csv.push('\n');
    }
    if csv.len() > MAX_EXTERNAL_ARTIFACT_BYTES {
        return Err(DirectPortError::UnsupportedExecution(
            "ngspice waveform CSV exceeds the bounded 8 MiB output budget".to_owned(),
        ));
    }
    fs::write(path, csv).map_err(|error| DirectPortError::OutputIo(error.to_string()))?;
    Ok(waveform.rows.len())
}

fn touchstone_port_count(path: &Path) -> Option<usize> {
    let name = path.file_name()?.to_str()?.to_ascii_lowercase();
    let marker = name.rfind(".s")?;
    let digits = name.get(marker + 2..)?.strip_suffix('p')?;
    let ports = digits.parse::<usize>().ok()?;
    (ports > 0 && ports <= 32).then_some(ports)
}

fn compile_touchstone_s_elements(
    text: &str,
    source_dir: &Path,
    _run_dir: &Path,
) -> Result<(String, Vec<ConversionAction>, Vec<UnsupportedIssue>), DirectPortError> {
    let mut output = Vec::new();
    let actions = Vec::new();
    let mut unsupported = Vec::new();
    let lines = text.lines().collect::<Vec<_>>();
    let mut line_index = 0usize;
    while line_index < lines.len() {
        let raw = lines[line_index];
        let first_token = tokens(raw).into_iter().next().unwrap_or_default();
        let mut end_index = line_index + 1;
        // The pinned CLI consumes an S-element as one logical record, so a
        // TSTONEFILE parameter on a `+` continuation must be fitted too.
        if first_token.len() > 1
            && first_token.starts_with(['S', 's'])
            && !first_token.starts_with(['.', '*'])
        {
            while end_index < lines.len() && lines[end_index].trim_start().starts_with('+') {
                end_index += 1;
            }
        }
        let block = lines[line_index..end_index].join("\n");
        let normalized = block.replace('+', " ");
        let upper = normalized.to_ascii_uppercase();
        if !first_token.starts_with(['S', 's']) || !upper.contains("TSTONEFILE") {
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        }
        let Some(tstone_index) = upper.find("TSTONEFILE") else {
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        };
        let Some(equal_offset) = normalized[tstone_index..].find('=') else {
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        };
        let equal = tstone_index + equal_offset;
        let file_token = normalized[equal + 1..]
            .split_whitespace()
            .next()
            .unwrap_or("")
            .trim_matches(['\'', '"', ',', ')']);
        let touchstone = source_dir.join(file_token);
        let fields = tokens(&normalized)
            .into_iter()
            .filter(|field| field != "+")
            .collect::<Vec<_>>();
        let nodes = fields
            .iter()
            .skip(1)
            .take_while(|field| !field.contains('='))
            .cloned()
            .collect::<Vec<_>>();
        let Some(ports) = touchstone_port_count(&touchstone) else {
            unsupported.push(UnsupportedIssue {
                line: raw.trim().to_owned(),
                reason: "touchstone_port_count_is_invalid".to_owned(),
            });
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        };
        if nodes.len() != ports + 1 || nodes.last().is_none_or(|value| value != "0") {
            unsupported.push(UnsupportedIssue {
                line: raw.trim().to_owned(),
                reason: "touchstone_s_element_requires_common_ground_reference".to_owned(),
            });
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        }
        if !touchstone.is_file() {
            unsupported.push(UnsupportedIssue {
                line: raw.trim().to_owned(),
                reason: "touchstone_file_not_found".to_owned(),
            });
            output.extend(
                lines[line_index..end_index]
                    .iter()
                    .map(|line| (*line).to_owned()),
            );
            line_index = end_index;
            continue;
        }
        // The pinned Python workflow has no portable S-domain exporter for
        // an HSPICE `S` element.  Do not silently substitute AS-03's Y fit:
        // that changes the element's semantics and can produce a plausible
        // but incorrect transient deck.  Preserve the source line and make
        // the unsupported boundary explicit.
        unsupported.push(UnsupportedIssue {
            line: raw.trim().to_owned(),
            reason: "touchstone_s_element_auto_fit_disabled".to_owned(),
        });
        output.extend(
            lines[line_index..end_index]
                .iter()
                .map(|line| (*line).to_owned()),
        );
        line_index = end_index;
    }
    Ok((
        format!("{}\n", output.join("\n").trim()),
        actions,
        unsupported,
    ))
}

fn prepare_case(case: DeckCase, backend: Backend) -> PreparedCase {
    let audit = audit_deck(&case.text);
    let dependencies = audit
        .includes
        .iter()
        .cloned()
        .chain(audit.libraries.iter().map(|library| library.path.clone()))
        .map(|reference| DependencyReference {
            admission: classify_dependency(&reference),
            reference,
        })
        .collect::<Vec<_>>();
    let (deck_text, actions, unsupported) = convert_deck(&case.text, backend);
    let mut output_paths = vec![
        format!("{}/case.cir", case.name),
        format!("{}/case.source.sp", case.name),
        format!("{}/compat_report.json", case.name),
    ];
    if backend == Backend::XyceXdm {
        output_paths.push(format!("{}/case.sp", case.name));
    }
    let status = if !audit.unsupported_directives.is_empty()
        || !unsupported.is_empty()
        || dependencies.iter().any(|dependency| {
            dependency.admission != DependencyAdmission::RelativeRequiresSourceRoot
        }) {
        PreparationStatus::Blocked
    } else if actions.is_empty() {
        PreparationStatus::Compatible
    } else {
        PreparationStatus::AutoConverted
    };
    PreparedCase {
        case,
        deck_text,
        audit,
        dependencies,
        actions,
        unsupported,
        preparation_status: status,
        output_paths,
    }
}

/// Mirrors `split_alter_cases` from the pinned Python object, including its
/// permissive `.alter*` prefix and missing-`.end` behavior.
pub fn split_alter_cases(text: &str, stem: &str) -> Vec<DeckCase> {
    let mut base = Vec::<String>::new();
    let mut alters = Vec::<(String, Vec<String>)>::new();
    let mut current_header: Option<String> = None;
    let mut current_lines = Vec::<String>::new();
    let mut end_line: Option<String> = None;
    for line in text.lines() {
        let stripped = line.trim();
        if stripped.eq_ignore_ascii_case(".end") {
            end_line = Some(stripped.to_owned());
            continue;
        }
        if stripped.to_ascii_lowercase().starts_with(".alter") {
            if let Some(header) = current_header.take() {
                alters.push((header, std::mem::take(&mut current_lines)));
            }
            current_header = Some(stripped.to_owned());
            continue;
        }
        if current_header.is_none() {
            base.push(line.to_owned());
        } else {
            current_lines.push(line.to_owned());
        }
    }
    if let Some(header) = current_header {
        alters.push((header, current_lines));
    }
    let base_text = case_text(&base, end_line.as_deref());
    let mut cases = vec![DeckCase {
        name: format!("{stem}__base"),
        text: base_text.clone(),
        kind: CaseKind::Base,
    }];
    for (index, (header, body)) in alters.into_iter().enumerate() {
        let suffix = case_suffix(&header, index + 1);
        let name = format!("{stem}__{suffix}");
        cases.push(DeckCase {
            name,
            text: case_text(&[base.clone(), body].concat(), end_line.as_deref()),
            kind: CaseKind::Alter,
        });
    }
    cases
}

fn case_text(lines: &[String], end_line: Option<&str>) -> String {
    let body = lines.join("\n").trim().to_owned();
    let body = match end_line {
        Some(end) if body.is_empty() => end.to_owned(),
        Some(end) => format!("{body}\n{end}"),
        None => body,
    };
    format!("{body}\n")
}

fn case_suffix(header: &str, index: usize) -> String {
    let mut words = header.split_whitespace();
    let _directive = words.next();
    let label = words.collect::<Vec<_>>().join(" ");
    if label.is_empty() {
        return format!("alter_{index:03}");
    }
    let mut sanitized = label
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' {
                character.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect::<String>();
    while sanitized.starts_with('_') {
        sanitized.remove(0);
    }
    while sanitized.ends_with('_') {
        sanitized.pop();
    }
    if sanitized.is_empty() {
        format!("alter_{index:03}")
    } else {
        format!("alter_{index:03}_{sanitized}")
    }
}

fn strip_hspice_comment(line: &str) -> String {
    let mut quote = None;
    for (index, character) in line.char_indices() {
        if matches!(character, '\'' | '"') && quote.is_none() {
            quote = Some(character);
        } else if quote == Some(character) {
            quote = None;
        } else if character == '$' && quote.is_none() {
            return line[..index].to_owned();
        }
    }
    line.to_owned()
}

fn logical_lines(text: &str) -> Vec<String> {
    let mut lines = Vec::new();
    let mut current = String::new();
    for raw in text.lines() {
        let stripped = strip_hspice_comment(raw).trim().to_owned();
        if stripped.is_empty() || stripped.starts_with('*') {
            continue;
        }
        if let Some(rest) = stripped.strip_prefix('+') {
            current.push(' ');
            current.push_str(rest.trim());
        } else {
            if !current.is_empty() {
                lines.push(std::mem::take(&mut current));
            }
            current = stripped;
        }
    }
    if !current.is_empty() {
        lines.push(current);
    }
    lines
}

fn tokens(line: &str) -> Vec<String> {
    let characters = line.chars().collect::<Vec<_>>();
    let mut output = Vec::new();
    let mut cursor = 0;
    while cursor < characters.len() {
        while cursor < characters.len() && characters[cursor].is_whitespace() {
            cursor += 1;
        }
        if cursor == characters.len() {
            break;
        }
        let start = cursor;
        if matches!(characters[cursor], '\'' | '"') {
            let quote = characters[cursor];
            cursor += 1;
            while cursor < characters.len() {
                let character = characters[cursor];
                cursor += 1;
                if character == quote {
                    break;
                }
            }
        } else {
            while cursor < characters.len() && !characters[cursor].is_whitespace() {
                cursor += 1;
            }
        }
        output.push(characters[start..cursor].iter().collect());
    }
    output
}

fn clean_path(token: &str) -> String {
    token.trim_matches(['\'', '"']).to_owned()
}

/// Mirrors the upstream directive, include, library, and unsupported audit.
pub fn audit_deck(text: &str) -> DeckAudit {
    let supported = SUPPORTED_DIRECTIVES
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let mut directive_counts = BTreeMap::new();
    let mut includes = Vec::new();
    let mut libraries = Vec::new();
    let mut unsupported_directives = Vec::new();
    for line in logical_lines(text) {
        if !line.starts_with('.') {
            continue;
        }
        let fields = tokens(&line);
        let Some(directive) = fields.first().map(|field| field.to_ascii_lowercase()) else {
            continue;
        };
        *directive_counts.entry(directive.clone()).or_insert(0) += 1;
        if matches!(directive.as_str(), ".include" | ".inc") && fields.len() >= 2 {
            includes.push(clean_path(&fields[1]));
        }
        if directive == ".lib" && fields.len() >= 2 {
            libraries.push(LibraryReference {
                path: clean_path(&fields[1]),
                section: fields.get(2).map(|field| clean_path(field)),
            });
        }
        if !supported.contains(directive.as_str()) {
            unsupported_directives.push(directive);
        }
    }
    DeckAudit {
        directive_counts,
        includes,
        libraries,
        unsupported_directives,
    }
}

fn classify_dependency(reference: &str) -> DependencyAdmission {
    let path = Path::new(reference);
    if path.is_absolute() {
        return DependencyAdmission::AbsoluteNotStaged;
    }
    if path
        .components()
        .next()
        .is_some_and(|component| matches!(component, std::path::Component::ParentDir))
    {
        return DependencyAdmission::LexicallyEscapesSourceRoot;
    }
    DependencyAdmission::RelativeRequiresSourceRoot
}

fn has_post_option(line: &str) -> bool {
    let fields = tokens(line);
    fields
        .first()
        .is_some_and(|field| field.eq_ignore_ascii_case(".option"))
        && fields[1..].iter().any(|field| {
            field.eq_ignore_ascii_case("post") || field.to_ascii_lowercase().starts_with("post=")
        })
}

const PWL_TIME_UNITS: [(&str, f64); 6] = [
    ("fs", 1e-15),
    ("ps", 1e-12),
    ("ns", 1e-9),
    ("us", 1e-6),
    ("ms", 1e-3),
    ("s", 1.0),
];

fn parse_pwl_time(token: &str) -> Option<(f64, String)> {
    let lower = token.to_ascii_lowercase();
    for (unit, scale) in PWL_TIME_UNITS {
        if let Some(number) = lower.strip_suffix(unit) {
            if number.is_empty()
                || !number
                    .chars()
                    .all(|character| character.is_ascii_digit() || ".eE+-".contains(character))
            {
                continue;
            }
            let seconds = number.parse::<f64>().ok()? * scale;
            return Some((seconds, unit.to_owned()));
        }
    }
    None
}

fn is_pwl_value(token: &str) -> bool {
    !token.is_empty()
        && token
            .chars()
            .all(|character| character.is_ascii_digit() || ".eE+-".contains(character))
}

fn parse_pwl_points(text: &str) -> Vec<(f64, String)> {
    let fields = text.split_whitespace().collect::<Vec<_>>();
    let mut points = Vec::new();
    for pair in fields.windows(2) {
        let Some((seconds, _unit)) = parse_pwl_time(pair[0]) else {
            continue;
        };
        if is_pwl_value(pair[1]) {
            points.push((seconds, pair[1].to_owned()));
        }
    }
    points
}

fn parse_repeat_line(line: &str) -> Option<(f64, String, Option<String>)> {
    let trimmed = line.trim_start();
    let remainder = trimmed.strip_prefix('+')?.trim_start();
    let remainder_lower = remainder.to_ascii_lowercase();
    let mut cursor = 0;
    if !remainder_lower[cursor..].starts_with('r') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    if remainder.as_bytes().get(cursor) != Some(&b'=') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    let number_start = cursor;
    while remainder.as_bytes().get(cursor).is_some_and(|character| {
        character.is_ascii_digit() || matches!(character, b'.' | b'e' | b'E' | b'+' | b'-')
    }) {
        cursor += 1;
    }
    if cursor == number_start {
        return None;
    }
    let number_text = remainder.get(number_start..cursor)?.to_owned();
    let number = number_text.parse::<f64>().ok()?;
    let unit_start = cursor;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_alphabetic)
    {
        cursor += 1;
    }
    let unit = remainder.get(unit_start..cursor)?;
    let scale = PWL_TIME_UNITS
        .iter()
        .find(|(candidate, _)| candidate.eq_ignore_ascii_case(unit))
        .map(|(_, scale)| *scale)?;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    if remainder.as_bytes().get(cursor) != Some(&b')') {
        return None;
    }
    cursor += 1;
    while remainder
        .as_bytes()
        .get(cursor)
        .is_some_and(u8::is_ascii_whitespace)
    {
        cursor += 1;
    }
    let multiplicity = if remainder_lower[cursor..].starts_with('m') {
        cursor += 1;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(u8::is_ascii_whitespace)
        {
            cursor += 1;
        }
        if remainder.as_bytes().get(cursor) != Some(&b'=') {
            return None;
        }
        cursor += 1;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(u8::is_ascii_whitespace)
        {
            cursor += 1;
        }
        let value_start = cursor;
        while remainder
            .as_bytes()
            .get(cursor)
            .is_some_and(|character| !character.is_ascii_whitespace())
        {
            cursor += 1;
        }
        Some(remainder.get(value_start..cursor)?.to_owned())
    } else {
        None
    };
    if !remainder[cursor..].trim().is_empty() {
        return None;
    }
    Some((number * scale, format!("{number_text}{unit}"), multiplicity))
}

fn current_pwl_open(line: &str) -> Option<usize> {
    if !line.starts_with(['I', 'i']) {
        return None;
    }
    let first_space = line.find(char::is_whitespace)?;
    if first_space <= 1 {
        return None;
    }
    let lower = line.to_ascii_lowercase();
    let pwl = lower.rfind("pwl")?;
    if pwl > 0 && line.as_bytes()[pwl - 1].is_ascii_alphanumeric() {
        return None;
    }
    let mut open = pwl + 3;
    while line
        .as_bytes()
        .get(open)
        .is_some_and(u8::is_ascii_whitespace)
    {
        open += 1;
    }
    if line.as_bytes().get(open) != Some(&b'(') {
        return None;
    }
    Some(open)
}

fn format_pwl_number(value: f64) -> String {
    if value == 0.0 {
        return "0".to_owned();
    }
    let absolute = value.abs();
    if (1e-4..1e6).contains(&absolute) {
        let exponent = absolute.log10().floor() as i32;
        let decimals = (5 - exponent).max(0) as usize;
        let mut result = format!("{:.*}", decimals, value);
        while result.ends_with('0') {
            result.pop();
        }
        if result.ends_with('.') {
            result.pop();
        }
        return result;
    }
    let scientific = format!("{value:.5e}");
    let (mantissa, exponent) = scientific
        .split_once('e')
        .expect("Rust scientific formatting includes an exponent");
    let mut mantissa = mantissa
        .trim_end_matches('0')
        .trim_end_matches('.')
        .to_owned();
    if mantissa == "-0" {
        mantissa = "0".to_owned();
    }
    let exponent = exponent.parse::<i32>().expect("Rust exponent is numeric");
    format!("{mantissa}e{exponent:+03}")
}

fn rewrite_current_pwl_source(
    group: &str,
    repeat_start: f64,
    repeat_end: f64,
    points: &[(f64, String)],
    multiplicity: Option<&str>,
) -> String {
    let mut source = group.to_owned();
    source.replace_range(0..1, "B");
    let lower = source.to_ascii_lowercase();
    let open = source
        .rfind('(')
        .expect("current PWL group has an opening parenthesis");
    let pwl = lower[..open]
        .rfind("pwl")
        .expect("current PWL group has a PWL function");
    let multiplier = multiplicity.map_or_else(String::new, |value| format!("({value}) * "));
    source.replace_range(pwl..open + 1, &format!("I = {multiplier}pwl("));
    let start = format_pwl_number(repeat_start / 1e-12);
    let period = format_pwl_number((repeat_end - repeat_start) / 1e-12);
    let mut lines = vec![format!(
        "{source}(time <= {start}ps ? time : {start}ps + (time - {start}ps) - {period}ps * floor((time - {start}ps) / {period}ps)),"
    )];
    for (chunk_index, chunk) in points.chunks(4).enumerate() {
        let values = chunk
            .iter()
            .map(|(seconds, value)| format!("{}ps, {value}", format_pwl_number(seconds / 1e-12)))
            .collect::<Vec<_>>()
            .join(", ");
        let suffix = if (chunk_index + 1) * 4 >= points.len() {
            ""
        } else {
            ","
        };
        lines.push(format!("+ {values}{suffix}"));
    }
    lines.push("+ )".to_owned());
    lines.join("\n")
}

fn rewrite_current_pwl_repeats_for_ngspice(
    text: &str,
    actions: &mut Vec<ConversionAction>,
    unsupported: &mut Vec<UnsupportedIssue>,
) -> String {
    let lines = text.split_inclusive('\n').collect::<Vec<_>>();
    let mut output = String::new();
    let mut index = 0;
    while index < lines.len() {
        let raw_line = lines[index];
        let line = raw_line.trim_end_matches(['\r', '\n']);
        let Some(open) = current_pwl_open(line) else {
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        let mut point_text = line[open + 1..].to_owned();
        let mut repeat = None;
        let mut end_index = index + 1;
        while end_index < lines.len() {
            let candidate = lines[end_index].trim_end_matches(['\r', '\n']);
            if let Some(parsed) = parse_repeat_line(candidate) {
                repeat = Some(parsed);
                break;
            }
            point_text.push(' ');
            point_text.push_str(candidate);
            end_index += 1;
        }
        let Some((repeat_start, repeat_text, multiplicity)) = repeat else {
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        let points = parse_pwl_points(&point_text);
        let first_line = line.to_owned();
        let repeat_end = points.last().map(|(seconds, _)| *seconds);
        if !points
            .iter()
            .any(|(seconds, _)| (*seconds - repeat_start).abs() <= 1e-18)
        {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "current_pwl_repeat_point_not_found".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        }
        let Some(repeat_end) = repeat_end else {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "current_pwl_repeat_point_not_found".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        };
        if repeat_end <= repeat_start {
            unsupported.push(UnsupportedIssue {
                line: first_line,
                reason: "invalid_current_pwl_repeat_window".to_owned(),
            });
            output.push_str(raw_line);
            index += 1;
            continue;
        }
        let group = &line[..open + 1];
        let converted = rewrite_current_pwl_source(
            group,
            repeat_start,
            repeat_end,
            &points,
            multiplicity.as_deref(),
        );
        actions.push(ConversionAction {
            kind: "rewrite_current_pwl_repeat".to_owned(),
            source: format!("{}... R={repeat_text}", group.trim()),
            target: format!(
                "behavioral current PWL: repeat {}ps to {}ps{}",
                format_pwl_number(repeat_start / 1e-12),
                format_pwl_number(repeat_end / 1e-12),
                multiplicity
                    .as_deref()
                    .map_or(String::new(), |value| format!("; preserves M={value}"))
            ),
        });
        output.push_str(&converted);
        if lines[end_index].ends_with('\n') {
            output.push('\n');
        }
        index = end_index + 1;
    }
    output
}

/// Mirrors the deterministic text conversions in `convert_hspice_deck`.
pub(crate) fn convert_deck(
    text: &str,
    backend: Backend,
) -> (String, Vec<ConversionAction>, Vec<UnsupportedIssue>) {
    if backend != Backend::Ngspice {
        return (text.to_owned(), Vec::new(), Vec::new());
    }
    let mut actions = Vec::new();
    let mut unsupported = Vec::new();
    let source_text = rewrite_current_pwl_repeats_for_ngspice(text, &mut actions, &mut unsupported);
    let mut output = Vec::new();
    for raw in source_text.lines() {
        let stripped = raw.trim();
        let lower = stripped.to_ascii_lowercase();
        if lower.starts_with(".inc ") {
            let target = format!(
                ".include {}",
                stripped
                    .split_once(char::is_whitespace)
                    .map_or("", |(_, rest)| rest)
            );
            actions.push(ConversionAction {
                kind: "rewrite".to_owned(),
                source: stripped.to_owned(),
                target: target.clone(),
            });
            output.push(target);
        } else if lower.starts_with(".probe ") {
            let target = format!(
                ".print {}",
                stripped
                    .split_once(char::is_whitespace)
                    .map_or("", |(_, rest)| rest)
            );
            actions.push(ConversionAction {
                kind: "rewrite".to_owned(),
                source: stripped.to_owned(),
                target: target.clone(),
            });
            output.push(target);
        } else if has_post_option(stripped) {
            actions.push(ConversionAction {
                kind: "drop_option".to_owned(),
                source: stripped.to_owned(),
                target: String::new(),
            });
        } else {
            output.push(raw.to_owned());
        }
    }
    let deck_text = format!("{}\n", output.join("\n").trim());
    (deck_text, actions, unsupported)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_backend_and_execute_branches_are_explicit() {
        for backend in Backend::ALL {
            for execute in [false, true] {
                let request = RunHspiceRequest::new(backend.name(), "runs", execute).unwrap();
                let admission = admit_run_hspice("demo", ".tran 1p 1n\n.end\n", request).unwrap();
                assert_eq!(admission.backend, backend);
                assert_eq!(admission.execute, execute);
                assert_eq!(
                    admission.execution_stage,
                    match (backend, execute) {
                        (_, false) => ExecutionStage::NotExecuted,
                        (Backend::Native, true) => ExecutionStage::NativeEngine,
                        (Backend::Ngspice, true) => ExecutionStage::Ngspice,
                        (Backend::Xyce, true) => ExecutionStage::Xyce,
                        (Backend::XyceXdm, true) => ExecutionStage::XdmThenXyce,
                    }
                );
            }
        }
    }

    #[test]
    fn alter_split_matches_pinned_case_names_and_end_ownership() {
        let cases = split_alter_cases(
            ".param c=1u\n.tran 1p 1n\n.alter high decap\n.param c=2u\n.alter slow\n.param c=3u\n.end\n",
            "deck",
        );
        assert_eq!(
            cases
                .iter()
                .map(|case| case.name.as_str())
                .collect::<Vec<_>>(),
            [
                "deck__base",
                "deck__alter_001_high_decap",
                "deck__alter_002_slow"
            ]
        );
        assert!(cases.iter().all(|case| case.text.ends_with(".end\n")));
        assert!(cases[1].text.contains(".param c=2u"));
        assert!(!cases[1].text.contains(".param c=3u"));
    }

    #[test]
    fn audit_and_ngspice_conversion_cover_includes_libs_measure_and_actions() {
        let source = ".inc 'models.inc'\n.lib './corners.lib' tt\n.probe tran v(out)\n.measure tran m max v(out)\n.option post=2\n.end\n";
        let audit = audit_deck(source);
        assert_eq!(audit.includes, ["models.inc"]);
        assert_eq!(audit.libraries[0].path, "./corners.lib");
        assert_eq!(audit.directive_counts[".measure"], 1);
        let admission = admit_run_hspice(
            "deck",
            source,
            RunHspiceRequest::new("ngspice", "runs", false).unwrap(),
        )
        .unwrap();
        assert_eq!(
            admission.cases[0].preparation_status,
            PreparationStatus::AutoConverted
        );
        assert!(
            admission.cases[0]
                .deck_text
                .contains(".include 'models.inc'")
        );
        assert!(admission.cases[0].deck_text.contains(".print tran v(out)"));
        assert!(!admission.cases[0].deck_text.contains("post=2"));
    }

    #[test]
    fn normalized_outputs_match_pinned_hspice_measure_contract() {
        let source = concat!(
            ".probe tran v(out) i(v1)\n",
            ".print ac vm(out)\n",
            ".measure tran m max v(out) from=1n to=2n\n",
            ".meas op p PARAM='v(out)'\n",
            ".measure op q PARAM = sqrt(v(out))\n",
        );
        assert_eq!(
            output_probes(source),
            vec![
                "v(out)".to_owned(),
                "i(v1)".to_owned(),
                "vm(out)".to_owned()
            ]
        );
        let measures = output_measures(source);
        assert_eq!(measures.len(), 3);
        assert_eq!(measures[0]["analysis"], "tran");
        assert_eq!(measures[0]["name"], "m");
        assert_eq!(measures[0]["operation"], "max");
        assert_eq!(measures[0]["target"], "v(out)");
        assert_eq!(measures[1]["operation"], "param");
        assert_eq!(measures[1]["target"], "'v(out)'");
        assert_eq!(measures[2]["target"], "sqrt(v(out))");
    }

    #[test]
    fn ngspice_s_element_parser_rejects_auto_fit_without_mutating_source() {
        let root = std::env::temp_dir().join(format!("sipi-as05-s-cont-{}", std::process::id()));
        let run = root.join("run");
        fs::create_dir_all(&run).unwrap();
        fs::write(root.join("missing.s2p"), b"not fitted").unwrap();
        let (prepared, actions, unsupported) = compile_touchstone_s_elements(
            "Sfoo p1 p2 0\n+ TSTONEFILE='missing.s2p'\n.end\n",
            &root,
            &run,
        )
        .unwrap();
        assert!(actions.is_empty());
        assert_eq!(
            unsupported[0].reason,
            "touchstone_s_element_auto_fit_disabled"
        );
        assert!(prepared.contains("+ TSTONEFILE='missing.s2p'"));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_result_helpers_parse_measurements_and_waveforms() {
        let root = std::env::temp_dir().join(format!("sipi-as05-results-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let transcript = "m_rms = 1.25e-3 at=2e-9\nIndex time v(out)\n0 0 1\n1 1e-9 2\n";
        let measurements = parse_ngspice_measurements(transcript);
        assert_eq!(measurements[0]["name"], "m_rms");
        assert_eq!(measurements[0]["at"], 2e-9);
        let path = root.join("waveform.csv");
        let waveform = parse_ngspice_waveform(transcript).unwrap();
        validate_ngspice_waveform_columns(waveform.as_ref(), &["V(OUT)".to_owned()]).unwrap();
        assert_eq!(
            write_ngspice_waveform_csv(waveform.as_ref(), &path).unwrap(),
            2
        );
        assert!(
            fs::read_to_string(path)
                .unwrap()
                .starts_with("time,v(out)\n")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_result_contract_rejects_missing_extra_and_nonfinite_values() {
        let requested = vec![json!({"name": "m_rms"})];
        assert!(validate_ngspice_measurements(&requested, &[]).is_err());
        assert!(
            validate_ngspice_measurements(&requested, &[json!({"name": "other", "value": 1.0})])
                .is_err()
        );
        assert!(
            validate_ngspice_measurements(&requested, &parse_ngspice_measurements("m_rms = NaN\n"))
                .is_err()
        );
        let waveform = parse_ngspice_waveform("Index time v(out)\n0 0 1\n").unwrap();
        assert!(
            validate_ngspice_waveform_columns(waveform.as_ref(), &["v(in)".to_owned()]).is_err()
        );
        assert!(
            validate_ngspice_waveform_columns(
                parse_ngspice_waveform("Index time v(in)\n0 0 1\n")
                    .unwrap()
                    .as_ref(),
                &["v(in)".to_owned(), "v(in)".to_owned()]
            )
            .is_err()
        );
    }

    #[test]
    fn ngspice_result_contract_matches_ascii_case_insensitively_and_is_anchored() {
        let requested = vec![json!({"name": "M_RMS"})];
        let returned = parse_ngspice_measurements("m_rms = 1.25e-3 at=2e-9\n");
        validate_ngspice_measurements(&requested, &returned).unwrap();
        assert_eq!(returned[0]["name"], "m_rms");
        assert!(parse_ngspice_measurements("m_rms = 1.0 trailing\n").is_empty());
        assert!(parse_ngspice_measurements("m_rms = 1.0 at=2 at=3\n").is_empty());
        assert!(parse_ngspice_measurements("m rms = 1.0\n").is_empty());
        let waveform = parse_ngspice_waveform("Index TIME V(OUT)\n0 0 1\n").unwrap();
        validate_ngspice_waveform_columns(waveform.as_ref(), &["v(out)".to_owned()]).unwrap();
    }

    #[test]
    fn ngspice_waveform_header_drift_is_not_written_from_a_partial_payload() {
        let text = "Index time v(out)\n0 0 1\nIndex time v(in)\n1 1 2\nIndex time v(out)\n2 2 3\n";
        let error = parse_ngspice_waveform(text).unwrap_err();
        assert!(
            matches!(error, DirectPortError::UnsupportedExecution(message) if message.contains("conflicting waveform headers"))
        );
        let root =
            std::env::temp_dir().join(format!("sipi-as05-wave-drift-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("waveform.csv");
        assert_eq!(write_ngspice_waveform_csv(None, &path).unwrap(), 0);
        assert!(!path.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_waveform_merges_print_tables_on_exact_shared_axis() {
        let text = concat!(
            "Index time v(load)\n",
            "0 0 1\n",
            "1 1e-9 2\n",
            "Index time v(vdd) vsrc#branch\n",
            "0 0 3 4\n",
            "1 1e-9 5 6\n",
        );
        let waveform = parse_ngspice_waveform(text).unwrap().unwrap();
        assert_eq!(
            waveform.columns,
            ["time", "v(load)", "v(vdd)", "vsrc#branch"]
        );
        assert_eq!(waveform.rows, [[0.0, 1.0, 3.0, 4.0], [1e-9, 2.0, 5.0, 6.0]]);
        validate_ngspice_waveform_columns(
            Some(&waveform),
            &[
                "v(load)".to_owned(),
                "v(vdd)".to_owned(),
                "i(Vsrc)".to_owned(),
            ],
        )
        .unwrap();
    }

    #[test]
    fn ngspice_waveform_contract_rejects_missing_axis_and_duplicate_probe_columns() {
        let missing_axis = parse_ngspice_waveform("Index\n0\n").unwrap();
        assert!(
            validate_ngspice_waveform_columns(missing_axis.as_ref(), &["v(out)".to_owned()])
                .is_err()
        );
        let duplicate = parse_ngspice_waveform("Index time V(out) v(OUT)\n0 0 1 1\n").unwrap();
        assert!(
            validate_ngspice_waveform_columns(
                duplicate.as_ref(),
                &["v(out)".to_owned(), "v(OUT)".to_owned()]
            )
            .is_err()
        );
    }

    #[test]
    fn ngspice_measurement_only_contract_has_no_waveform_artifact() {
        let root =
            std::env::temp_dir().join(format!("sipi-as05-measure-only-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let waveform = root.join("waveform.csv");
        let text = "m_rms = 1.25e-3\n";
        let parsed = parse_ngspice_waveform(text).unwrap();
        assert_eq!(
            write_ngspice_waveform_csv(parsed.as_ref(), &waveform).unwrap(),
            0
        );
        assert!(!waveform.is_file());
        let requested = vec![json!({"name": "m_rms"})];
        let returned = parse_ngspice_measurements(text);
        validate_ngspice_measurements(&requested, &returned).unwrap();
        validate_ngspice_waveform_columns(parsed.as_ref(), &[]).unwrap();
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_touchstone_s_element_fails_closed_without_auto_fit() {
        let root = std::env::temp_dir().join(format!("sipi-as05-sparam-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let mut s2p = String::from("# Hz S RI R 50\n");
        for index in 0..20 {
            let frequency = 1.0e6 * (index + 1) as f64;
            s2p.push_str(&format!("{frequency:.0} 0.01 0 0.8 0 0.8 0 0.01 0\n"));
        }
        fs::write(root.join("line.s2p"), s2p).unwrap();
        let deck = root.join("two.sp");
        fs::write(&deck, "Sfoo p1 p2 0\n+ TSTONEFILE='line.s2p'\n.end\n").unwrap();
        let request = RunHspiceRequest::new("ngspice", root.join("two-out"), false).unwrap();
        let result = run_hspice(&deck, request).unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let report =
            fs::read_to_string(root.join("two-out/two/two__base/compat_report.json")).unwrap();
        assert!(report.contains("touchstone_s_element_auto_fit_disabled"));
        assert!(
            !root
                .join("two-out/two/two__base/sparam/Sfoo.y.sp")
                .is_file()
        );

        let values = "0 ".repeat(18);
        let mut s3p = String::from("# GHz S RI R 50\n");
        for index in 0..12 {
            s3p.push_str(&format!("{} {values}\n", 0.1 + index as f64 * 0.05));
        }
        fs::write(root.join("network.s3p"), s3p).unwrap();
        let deck = root.join("three.sp");
        fs::write(&deck, "Sfoo p1 p2 p3 0\n+ TSTONEFILE='network.s3p'\n.end\n").unwrap();
        let request = RunHspiceRequest::new("ngspice", root.join("three-out"), false).unwrap();
        let result = run_hspice(&deck, request).unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let report =
            fs::read_to_string(root.join("three-out/three/three__base/compat_report.json"))
                .unwrap();
        assert!(report.contains("touchstone_s_element_auto_fit_disabled"));
        assert!(
            !root
                .join("three-out/three/three__base/sparam/Sfoo.y.sp")
                .is_file()
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn unsupported_directive_is_reported_without_silent_deletion() {
        let admission = admit_run_hspice(
            "deck",
            ".fft v(out)\n.end\n",
            RunHspiceRequest::new("native", "runs", false).unwrap(),
        )
        .unwrap();
        assert_eq!(
            admission.cases[0].preparation_status,
            PreparationStatus::Blocked
        );
        assert_eq!(admission.cases[0].audit.unsupported_directives, [".fft"]);
        assert!(admission.cases[0].deck_text.contains(".fft v(out)"));
    }

    #[test]
    fn model_and_endcomment_are_audited_without_hard_blocking() {
        let audit = audit_deck(
            ".model sw sw(Ron=1 Roff=2)\n.endcomment preserved by source audit\n.end*comment preserved by source audit\n.end\n",
        );
        assert!(audit.unsupported_directives.is_empty());
        assert_eq!(audit.directive_counts[".model"], 1);
        assert_eq!(audit.directive_counts[".endcomment"], 1);
        assert_eq!(audit.directive_counts[".end*comment"], 1);
    }

    #[test]
    fn xyce_and_xdm_backends_are_rejected_before_admission() {
        for backend in ["xyce", "xyce-xdm"] {
            assert_eq!(
                RunHspiceRequest::new(backend, "runs", true).unwrap_err(),
                DirectPortError::UnsupportedBackend(backend.to_owned())
            );
        }
    }

    #[test]
    fn invalid_backend_and_empty_stem_fail_closed() {
        assert_eq!(
            RunHspiceRequest::new("hspice", "runs", false).unwrap_err(),
            DirectPortError::UnsupportedBackend("hspice".to_owned())
        );
        assert_eq!(
            admit_run_hspice(
                "",
                ".end\n",
                RunHspiceRequest::new("native", "runs", false).unwrap()
            )
            .unwrap_err(),
            DirectPortError::EmptyDeckStem
        );
    }

    #[test]
    fn file_runner_requires_explicit_native_engine_before_execution() {
        let root = std::env::temp_dir().join(format!("sipi-as05-run-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        let request = RunHspiceRequest::new("native", root.join("out"), true).unwrap();
        let result = run_hspice(&deck, request);
        assert!(matches!(
            result,
            Err(DirectPortError::UnsupportedExecution(_))
        ));
        assert!(!root.join("out").exists());
        assert!(!root.join("out/deck/deck__base/native_result.json").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn file_runner_rejects_stale_project_before_writing_case_artifacts() {
        let root = std::env::temp_dir().join(format!("sipi-as05-stale-{}", std::process::id()));
        let stale_case = root.join("out/deck/deck__base");
        fs::create_dir_all(&stale_case).unwrap();
        fs::write(stale_case.join("run_summary.json"), "stale").unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        let request = RunHspiceRequest::new("ngspice", root.join("out"), false).unwrap();
        assert!(matches!(
            run_hspice(&deck, request),
            Err(DirectPortError::UnsupportedExecution(message))
                if message.contains("project directory must be fresh")
        ));
        assert!(!stale_case.join("case.cir").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn execute_never_resolves_fake_path_or_alias_executables() {
        let root = std::env::temp_dir().join(format!("sipi-as05-custody-{}", std::process::id()));
        let request = RunHspiceRequest::new("native", root.join("out"), true)
            .unwrap()
            .with_native_engine(root.join("alias.exe"));
        let result = run_hspice(root.join("deck.sp"), request);
        assert!(
            matches!(result, Err(DirectPortError::UnsupportedExecution(message)) if message.contains("custody"))
        );
        assert!(!root.join("out").exists());
    }

    #[test]
    fn ngspice_execution_requires_absolute_sha256_attestation() {
        let root =
            std::env::temp_dir().join(format!("sipi-as05-ng-custody-{}", std::process::id()));
        let deck = root.join("deck.sp");
        fs::create_dir_all(&root).unwrap();
        fs::write(&deck, ".tran 1p 1n\n.end\n").unwrap();
        let missing = RunHspiceRequest::new("ngspice", root.join("out"), true).unwrap();
        assert!(matches!(
            run_hspice(&deck, missing),
            Err(DirectPortError::UnsupportedExecution(message))
                if message.contains("caller custody")
        ));
        let wrong = RunHspiceRequest::new("ngspice", root.join("wrong-out"), true).unwrap();
        assert!(matches!(
            run_hspice_with_ngspice_custody(
                &deck,
                wrong,
                NgspiceCustody::new(std::env::current_exe().unwrap(), "0".repeat(64)),
            ),
            Err(DirectPortError::UnsupportedExecution(message))
                if message.contains("SHA-256")
        ));
        let relative_request =
            RunHspiceRequest::new("ngspice", root.join("relative-out"), true).unwrap();
        assert!(matches!(
            run_hspice_with_ngspice_custody(
                &deck,
                relative_request,
                NgspiceCustody::new(PathBuf::from("ngspice.exe"), "0".repeat(64)),
            ),
            Err(DirectPortError::UnsupportedExecution(message))
                if message.contains("absolute executable path")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn file_runner_stages_recursive_dependencies_and_hashes_compatibility() {
        let root = std::env::temp_dir().join(format!("sipi-as05-deps-{}", std::process::id()));
        fs::create_dir_all(root.join("models")).unwrap();
        fs::write(
            root.join("models/top.inc"),
            ".include 'nested.inc'\n.param x=1\n",
        )
        .unwrap();
        fs::write(root.join("models/nested.inc"), ".param y=2\n").unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".include 'models/top.inc'\n.tran 1p 1n\n.end\n").unwrap();
        let request = RunHspiceRequest::new("native", root.join("out"), false).unwrap();
        run_hspice(&deck, request).unwrap();
        let case_root = root.join("out/deck/deck__base");
        assert!(case_root.join("models/top.inc").is_file());
        assert!(case_root.join("models/nested.inc").is_file());
        let report: serde_json::Value =
            serde_json::from_slice(&fs::read(case_root.join("compat_report.json")).unwrap())
                .unwrap();
        assert_eq!(report["schema_version"], 2);
        assert!(report["deck"]["sha256"].as_str().is_some());
        let dependencies = report["dependencies"].as_array().unwrap();
        assert_eq!(dependencies.len(), 2);
        for dependency in dependencies {
            assert!(dependency["source"].as_str().is_some());
            assert_eq!(dependency["source"], dependency["staged"]);
            assert_eq!(dependency["source_bytes"], dependency["staged_bytes"]);
            assert_eq!(dependency["source_sha256"], dependency["staged_sha256"]);
        }
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn ngspice_dependency_staging_converts_nested_decks() {
        let root = std::env::temp_dir().join(format!("sipi-as05-ng-deps-{}", std::process::id()));
        fs::create_dir_all(root.join("models")).unwrap();
        fs::write(
            root.join("models/top.inc"),
            ".include 'nested.inc'\n.probe tran v(out)\n.option post=2\n",
        )
        .unwrap();
        fs::write(root.join("models/nested.inc"), ".param y=2\n").unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".inc 'models/top.inc'\n.tran 1p 1n\n.end\n").unwrap();
        let request = RunHspiceRequest::new("ngspice", root.join("out"), false).unwrap();
        let result = run_hspice(&deck, request).unwrap();
        assert_eq!(result.status, PreparationStatus::AutoConverted);
        let case_root = root.join("out/deck/deck__base");
        let nested = fs::read_to_string(case_root.join("models/top.inc")).unwrap();
        assert!(nested.contains(".include 'nested.inc'"));
        assert!(nested.contains(".print tran v(out)"));
        assert!(!nested.contains("post=2"));
        let report: serde_json::Value =
            serde_json::from_slice(&fs::read(case_root.join("compat_report.json")).unwrap())
                .unwrap();
        assert!(
            report["actions"]
                .as_array()
                .unwrap()
                .iter()
                .any(|action| { action["source"] == ".probe tran v(out)" })
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn missing_and_outside_dependencies_are_reported_without_aborting_preparation() {
        let root = std::env::temp_dir().join(format!(
            "sipi-as05-dependency-blockers-{}",
            std::process::id()
        ));
        let outside_root = std::env::temp_dir().join(format!(
            "sipi-as05-dependency-blockers-outside-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&outside_root).unwrap();
        fs::write(outside_root.join("outside.inc"), ".param outside=1\n").unwrap();
        let deck = root.join("deck.sp");
        let outside_reference = format!(
            "../{}/outside.inc",
            outside_root.file_name().unwrap().to_string_lossy()
        );
        fs::write(
            &deck,
            format!(".include 'missing.inc'\n.include '{outside_reference}'\n.tran 1p 1n\n.end\n"),
        )
        .unwrap();
        let request = RunHspiceRequest::new("native", root.join("out"), false).unwrap();
        let result = run_hspice(&deck, request).unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let report: serde_json::Value = serde_json::from_slice(
            &fs::read(root.join("out/deck/deck__base/compat_report.json")).unwrap(),
        )
        .unwrap();
        let unsupported = report["unsupported"].as_array().unwrap();
        assert!(unsupported.iter().any(|item| {
            item["line"] == "missing.inc" && item["reason"] == "include_not_found"
        }));
        assert!(unsupported.iter().any(|item| {
            item["line"] == outside_reference
                && item["reason"] == "include_outside_source_directory"
        }));
        assert!(report["dependencies"].as_array().unwrap().is_empty());
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(outside_root);
    }

    #[test]
    fn absolute_dependency_references_are_redacted_in_all_case_artifacts() {
        let root = std::env::temp_dir().join(format!(
            "sipi-as05-absolute-redaction-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        let absolute_reference = root.join("private").join("secret.inc");
        let deck = root.join("deck.sp");
        let raw_reference = absolute_reference.to_string_lossy().into_owned();
        fs::write(
            &deck,
            format!(".include '{raw_reference}'\n.lib '{raw_reference}' tt\n.tran 1p 1n\n.end\n"),
        )
        .unwrap();
        let result = run_hspice(
            &deck,
            RunHspiceRequest::new("native", root.join("out"), false).unwrap(),
        )
        .unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let case_root = root.join("out/deck/deck__base");
        for name in [
            "case.source.sp",
            "case.cir",
            "dependencies.json",
            "compat_report.json",
            "preflight.log",
        ] {
            let path = case_root.join(name);
            if path.is_file() {
                let contents = fs::read_to_string(path).unwrap();
                assert!(
                    !contents.contains(&raw_reference),
                    "absolute path leaked in {name}"
                );
                if name != "dependencies.json" {
                    assert!(
                        contents.contains("<absolute:secret.inc:"),
                        "redaction missing in {name}"
                    );
                }
            }
        }
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn nested_dependency_paths_are_redacted_before_conversion_and_write() {
        let root =
            std::env::temp_dir().join(format!("sipi-as05-nested-redaction-{}", std::process::id()));
        fs::create_dir_all(root.join("models")).unwrap();
        let raw_reference = r"C:\private\nested-secret.inc";
        fs::write(
            root.join("models/top.inc"),
            format!(".include '{raw_reference}'\n.probe tran v(out)\n"),
        )
        .unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".include 'models/top.inc'\n.end\n").unwrap();
        run_hspice(
            &deck,
            RunHspiceRequest::new("ngspice", root.join("out"), false).unwrap(),
        )
        .unwrap();
        let case_root = root.join("out/deck/deck__base");
        let staged = fs::read_to_string(case_root.join("models/top.inc")).unwrap();
        assert!(!staged.contains(raw_reference));
        assert!(staged.contains("<absolute:nested-secret.inc:"));
        let report = fs::read_to_string(case_root.join("compat_report.json")).unwrap();
        assert!(!report.contains(raw_reference));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn normalized_dependency_paths_reject_portable_windows_names_and_ads() {
        assert!(dependency_reference_is_absolute("C:relative.inc"));
        assert!(redacted_dependency_reference("C:relative.inc").starts_with("<absolute:"));
        for value in [
            "models:bad.inc",
            "models/C:bad.inc",
            "models/file.",
            "models/file ",
            "models/CON",
            "models/com1.txt",
            "",
            ".",
            "..",
        ] {
            assert!(
                normalized_relative_path(Path::new(value)).is_err(),
                "path should be rejected: {value:?}"
            );
        }
        assert_eq!(
            normalized_relative_path(Path::new("models/good.inc")).unwrap(),
            PathBuf::from("models/good.inc")
        );
    }

    #[test]
    fn physical_dependency_receipt_reads_back_the_create_new_handle() {
        let root =
            std::env::temp_dir().join(format!("sipi-as05-physical-receipt-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let target = root.join("nested/model.inc");
        let bytes = b".param physical=1\n";
        let (length, sha256, identity) = write_dependency_create_new(&target, bytes).unwrap();
        assert_eq!(length, bytes.len() as u64);
        assert_eq!(sha256, format!("{:x}", Sha256::digest(bytes)));
        assert_eq!(identity.bytes, length);
        assert_eq!(fs::read(&target).unwrap(), bytes);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn oversized_staged_output_is_rejected_before_create() {
        let root =
            std::env::temp_dir().join(format!("sipi-as05-oversized-staged-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let target = root.join("nested/model.inc");
        let bytes = vec![b'x'; (MAX_STAGED_DEPENDENCY_FILE_BYTES + 1) as usize];
        assert!(matches!(
            write_dependency_create_new(&target, &bytes),
            Err(DirectPortError::UnsupportedExecution(message))
                if message.contains("staged dependency")
        ));
        assert!(!target.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn cumulative_dependency_budget_cleans_prior_targets_and_preserves_owned_files() {
        const FILE_BYTES: usize = 8 * 1024 * 1024;
        let root = std::env::temp_dir().join(format!(
            "sipi-as05-cumulative-dependency-budget-{}",
            std::process::id()
        ));
        let source_root = root.join("source");
        let run_root = root.join("run");
        fs::create_dir_all(&source_root).unwrap();
        fs::create_dir_all(&run_root).unwrap();
        fs::write(run_root.join("case.cir"), "runner-owned\n").unwrap();
        let mut deck = String::new();
        for index in 0..5 {
            let name = format!("dep{index}.inc");
            let payload = format!(".param x={}\n", "x".repeat(FILE_BYTES - 12));
            fs::write(source_root.join(&name), payload).unwrap();
            deck.push_str(&format!(".include '{name}'\n"));
        }
        let error =
            stage_case_dependencies(&source_root, &run_root, &deck, Backend::Native).unwrap_err();
        assert!(error.to_string().contains("dependency byte budget"));
        assert_eq!(
            fs::read_to_string(run_root.join("case.cir")).unwrap(),
            "runner-owned\n"
        );
        for index in 0..5 {
            assert!(!run_root.join(format!("dep{index}.inc")).exists());
        }
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn oversized_dependency_is_rejected_before_staging() {
        let root = std::env::temp_dir().join(format!(
            "sipi-as05-oversized-dependency-{}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        let source = root.join("oversized.inc");
        let file = fs::File::create(&source).unwrap();
        file.set_len(MAX_DEPENDENCY_FILE_BYTES + 1).unwrap();
        assert!(matches!(
            read_dependency_once(&source),
            Err(DirectPortError::UnsupportedExecution(message))
                if message.contains("16 MiB")
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn dependency_cannot_overwrite_runner_owned_case_artifacts() {
        let root =
            std::env::temp_dir().join(format!("sipi-as05-owned-collision-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let deck = root.join("deck.sp");
        fs::write(root.join("case.cir"), ".param protected=1\n").unwrap();
        fs::write(&deck, ".include 'case.cir'\n.end\n").unwrap();
        let result = run_hspice(
            &deck,
            RunHspiceRequest::new("native", root.join("out"), false).unwrap(),
        )
        .unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let case_root = root.join("out/deck/deck__base");
        assert_eq!(
            fs::read_to_string(case_root.join("case.cir")).unwrap(),
            ".include 'case.cir'\n.end\n"
        );
        let report: serde_json::Value =
            serde_json::from_slice(&fs::read(case_root.join("compat_report.json")).unwrap())
                .unwrap();
        assert!(
            report["unsupported"]
                .as_array()
                .unwrap()
                .iter()
                .any(|item| { item["reason"] == "dependency_output_path_collision" })
        );
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn unix_symlink_dependency_alias_is_rejected_before_staging() {
        let root =
            std::env::temp_dir().join(format!("sipi-as05-symlink-alias-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("real.inc"), ".param real=1\n").unwrap();
        let alias = root.join("alias.inc");
        std::os::unix::fs::symlink(root.join("real.inc"), &alias).unwrap();
        let deck = root.join("deck.sp");
        fs::write(&deck, ".include 'alias.inc'\n.end\n").unwrap();
        let result = run_hspice(
            &deck,
            RunHspiceRequest::new("native", root.join("out"), false).unwrap(),
        )
        .unwrap();
        assert_eq!(result.status, PreparationStatus::Blocked);
        let report: serde_json::Value = serde_json::from_slice(
            &fs::read(root.join("out/deck/deck__base/compat_report.json")).unwrap(),
        )
        .unwrap();
        assert!(
            report["unsupported"]
                .as_array()
                .unwrap()
                .iter()
                .any(|item| {
                    item["reason"] == "dependency path contains a symlink or reparse component"
                })
        );
        let _ = fs::remove_dir_all(root);
    }
}
