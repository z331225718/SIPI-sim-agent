#![forbid(unsafe_code)]

use std::{
    collections::BTreeSet,
    env, fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

use pelite::pe64::{Pe, PeFile};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const POLICY_SCHEMA: &str = "sipi.release-layout-policy.v1";
pub const REPORT_SCHEMA: &str = "sipi.release-layout-report.v1";

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LayoutPolicyV1 {
    pub schema: String,
    pub platform: String,
    pub expected_executable: String,
    pub required_files: Vec<String>,
    pub optional_files: Vec<String>,
    pub normal_import_dll_allowlist: Vec<String>,
    pub forbidden_import_dll_tokens: Vec<String>,
    pub smoke: Vec<SmokeCommandV1>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SmokeCommandV1 {
    pub args: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LayoutReportV1 {
    pub schema: &'static str,
    pub status: &'static str,
    pub policy_sha256: String,
    pub inventory_sha256: String,
    pub executable_sha256: String,
    pub executable_bytes: u64,
    pub machine: String,
    pub normal_imports: Vec<String>,
    pub delay_import_directory_present: bool,
    pub smoke: Vec<SmokeReportV1>,
    pub limitations: Vec<&'static str>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SmokeReportV1 {
    pub args: Vec<String>,
    pub exit_code: i32,
    pub stdout_sha256: String,
    pub stderr_sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LayoutErrorCode {
    InvalidPolicy,
    UnsafeStage,
    LayoutMismatch,
    PeRejected,
    SmokeRejected,
    IoFailure,
}

impl LayoutErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidPolicy => "invalid_policy",
            Self::UnsafeStage => "unsafe_stage",
            Self::LayoutMismatch => "layout_mismatch",
            Self::PeRejected => "pe_rejected",
            Self::SmokeRejected => "smoke_rejected",
            Self::IoFailure => "io_failure",
        }
    }
}

#[derive(Debug)]
pub struct LayoutError {
    code: LayoutErrorCode,
    detail: String,
}

impl LayoutError {
    fn new(code: LayoutErrorCode, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }

    pub const fn code(&self) -> LayoutErrorCode {
        self.code
    }
}

impl std::fmt::Display for LayoutError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code.as_str(), self.detail)
    }
}

impl std::error::Error for LayoutError {}

pub fn parse_policy(input: &[u8]) -> Result<LayoutPolicyV1, LayoutError> {
    let policy = serde_json::from_slice(input).map_err(|_| {
        LayoutError::new(LayoutErrorCode::InvalidPolicy, "policy JSON was rejected")
    })?;
    validate_policy(&policy)?;
    Ok(policy)
}

pub fn verify_stage(stage: &Path, policy_bytes: &[u8]) -> Result<LayoutReportV1, LayoutError> {
    let policy = parse_policy(policy_bytes)?;
    verify_stage_with_policy(stage, &policy, sha256_hex(policy_bytes))
}

pub fn write_report(path: &Path, report: &LayoutReportV1) -> Result<(), LayoutError> {
    let bytes = serde_json::to_vec(report)
        .map_err(|_| LayoutError::new(LayoutErrorCode::IoFailure, "report serialization failed"))?;
    fs::write(path, bytes)
        .map_err(|_| LayoutError::new(LayoutErrorCode::IoFailure, "report could not be written"))
}

pub fn write_report_outside_stage(
    stage: &Path,
    path: &Path,
    report: &LayoutReportV1,
) -> Result<(), LayoutError> {
    let stage = fs::canonicalize(stage)
        .map_err(|_| LayoutError::new(LayoutErrorCode::UnsafeStage, "stage is unavailable"))?;
    let parent = path.parent().ok_or_else(|| {
        LayoutError::new(LayoutErrorCode::IoFailure, "report parent is unavailable")
    })?;
    let parent = fs::canonicalize(parent).map_err(|_| {
        LayoutError::new(LayoutErrorCode::IoFailure, "report parent is unavailable")
    })?;
    let name = path.file_name().ok_or_else(|| {
        LayoutError::new(LayoutErrorCode::IoFailure, "report name is unavailable")
    })?;
    let destination = parent.join(name);
    if destination.starts_with(&stage) {
        return Err(LayoutError::new(
            LayoutErrorCode::UnsafeStage,
            "report destination is inside the stage",
        ));
    }
    if let Ok(metadata) = fs::symlink_metadata(&destination)
        && (metadata.file_type().is_symlink() || is_reparse_point(&metadata))
    {
        return Err(LayoutError::new(
            LayoutErrorCode::IoFailure,
            "report destination is a link or reparse point",
        ));
    }
    write_report(&destination, report)
}

fn verify_stage_with_policy(
    stage: &Path,
    policy: &LayoutPolicyV1,
    policy_sha256: String,
) -> Result<LayoutReportV1, LayoutError> {
    let before = inspect_stage(stage, policy)?;
    let executable = stage_path(stage, &policy.expected_executable);
    let executable_bytes = fs::read(&executable).map_err(|_| {
        LayoutError::new(LayoutErrorCode::IoFailure, "executable could not be read")
    })?;
    let executable_sha256 = sha256_hex(&executable_bytes);
    let (machine, imports, delay_import_directory_present) = inspect_pe(&executable_bytes, policy)?;
    let smoke = run_smoke(stage, &policy.expected_executable, &policy.smoke)?;
    let after = inspect_stage(stage, policy)?;
    if before != after {
        return Err(LayoutError::new(
            LayoutErrorCode::SmokeRejected,
            "smoke command changed the stage inventory",
        ));
    }
    Ok(LayoutReportV1 {
        schema: REPORT_SCHEMA,
        status: "layout_conformant",
        policy_sha256,
        inventory_sha256: before,
        executable_sha256,
        executable_bytes: executable_bytes.len() as u64,
        machine,
        normal_imports: imports,
        delay_import_directory_present,
        smoke,
        limitations: vec![
            "provisional product boundary; this is not release readiness",
            "no hostile-filesystem containment claim",
            "no arbitrary-command child-process or dynamic-load claim",
        ],
    })
}

fn validate_policy(policy: &LayoutPolicyV1) -> Result<(), LayoutError> {
    if policy.schema != POLICY_SCHEMA || policy.platform != "windows-x86_64" {
        return Err(LayoutError::new(
            LayoutErrorCode::InvalidPolicy,
            "schema or platform is not supported",
        ));
    }
    let mut paths = BTreeSet::new();
    for path in policy
        .required_files
        .iter()
        .chain(policy.optional_files.iter())
    {
        validate_relative_path(path)?;
        if !paths.insert(path.to_ascii_lowercase()) {
            return Err(LayoutError::new(
                LayoutErrorCode::InvalidPolicy,
                "layout policy has duplicate or case-colliding paths",
            ));
        }
    }
    if !policy.required_files.contains(&policy.expected_executable) || policy.smoke.is_empty() {
        return Err(LayoutError::new(
            LayoutErrorCode::InvalidPolicy,
            "executable must be required and smoke commands must be present",
        ));
    }
    let mut imports = BTreeSet::new();
    for name in &policy.normal_import_dll_allowlist {
        validate_dll_name(name)?;
        if !imports.insert(name.to_ascii_lowercase()) {
            return Err(LayoutError::new(
                LayoutErrorCode::InvalidPolicy,
                "normal import allowlist has duplicates",
            ));
        }
    }
    if imports.is_empty() {
        return Err(LayoutError::new(
            LayoutErrorCode::InvalidPolicy,
            "normal import allowlist must be explicit",
        ));
    }
    for token in &policy.forbidden_import_dll_tokens {
        if token.is_empty() || token.bytes().any(|byte| byte.is_ascii_control()) {
            return Err(LayoutError::new(
                LayoutErrorCode::InvalidPolicy,
                "forbidden import token is invalid",
            ));
        }
    }
    for smoke in &policy.smoke {
        if smoke.args.is_empty()
            || smoke
                .args
                .iter()
                .any(|arg| arg.is_empty() || arg.contains('\0'))
        {
            return Err(LayoutError::new(
                LayoutErrorCode::InvalidPolicy,
                "smoke command is invalid",
            ));
        }
    }
    Ok(())
}

fn validate_relative_path(path: &str) -> Result<(), LayoutError> {
    if path.is_empty()
        || path.contains('\\')
        || path.contains(':')
        || path.starts_with('/')
        || path.ends_with('/')
    {
        return Err(LayoutError::new(
            LayoutErrorCode::InvalidPolicy,
            "path is unsafe",
        ));
    }
    for component in path.split('/') {
        let reserved = matches!(
            component
                .trim_end_matches([' ', '.'])
                .to_ascii_uppercase()
                .as_str(),
            "CON"
                | "PRN"
                | "AUX"
                | "NUL"
                | "COM1"
                | "COM2"
                | "COM3"
                | "COM4"
                | "COM5"
                | "COM6"
                | "COM7"
                | "COM8"
                | "COM9"
                | "LPT1"
                | "LPT2"
                | "LPT3"
                | "LPT4"
                | "LPT5"
                | "LPT6"
                | "LPT7"
                | "LPT8"
                | "LPT9"
        );
        if component.is_empty()
            || matches!(component, "." | "..")
            || component.ends_with([' ', '.'])
            || component.bytes().any(|byte| byte.is_ascii_control())
            || reserved
        {
            return Err(LayoutError::new(
                LayoutErrorCode::InvalidPolicy,
                "path is unsafe",
            ));
        }
    }
    Ok(())
}

fn validate_dll_name(name: &str) -> Result<(), LayoutError> {
    if name.is_empty()
        || name.contains(['/', '\\', ':'])
        || !name.to_ascii_lowercase().ends_with(".dll")
        || name.bytes().any(|byte| byte.is_ascii_control())
    {
        return Err(LayoutError::new(
            LayoutErrorCode::InvalidPolicy,
            "DLL allowlist entry is invalid",
        ));
    }
    Ok(())
}

fn inspect_stage(stage: &Path, policy: &LayoutPolicyV1) -> Result<String, LayoutError> {
    let metadata = fs::symlink_metadata(stage)
        .map_err(|_| LayoutError::new(LayoutErrorCode::UnsafeStage, "stage is unavailable"))?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() || is_reparse_point(&metadata) {
        return Err(LayoutError::new(
            LayoutErrorCode::UnsafeStage,
            "stage root is unsafe",
        ));
    }
    let expected = policy
        .required_files
        .iter()
        .chain(policy.optional_files.iter())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut actual = Vec::new();
    collect_stage_files(stage, Path::new(""), &expected, &mut actual)?;
    let actual_paths = actual
        .iter()
        .map(|entry| entry.path.clone())
        .collect::<BTreeSet<_>>();
    if !policy
        .required_files
        .iter()
        .all(|path| actual_paths.contains(path))
    {
        return Err(LayoutError::new(
            LayoutErrorCode::LayoutMismatch,
            "stage is missing a required file",
        ));
    }
    if actual_paths.iter().any(|path| !expected.contains(path)) {
        return Err(LayoutError::new(
            LayoutErrorCode::LayoutMismatch,
            "stage contains an unlisted file",
        ));
    }
    let mut case_folded = BTreeSet::new();
    for entry in &actual {
        if !case_folded.insert(entry.path.to_ascii_lowercase()) {
            return Err(LayoutError::new(
                LayoutErrorCode::LayoutMismatch,
                "stage has a case-colliding path",
            ));
        }
    }
    let serialized = actual
        .iter()
        .map(|entry| format!("{}:{}:{}", entry.path, entry.bytes, entry.sha256))
        .collect::<Vec<_>>()
        .join("\n");
    Ok(sha256_hex(serialized.as_bytes()))
}

#[derive(Debug, PartialEq, Eq)]
struct StageFile {
    path: String,
    bytes: u64,
    sha256: String,
}

fn collect_stage_files(
    root: &Path,
    relative: &Path,
    expected: &BTreeSet<String>,
    files: &mut Vec<StageFile>,
) -> Result<(), LayoutError> {
    for entry in fs::read_dir(root.join(relative)).map_err(|_| {
        LayoutError::new(
            LayoutErrorCode::UnsafeStage,
            "stage directory could not be read",
        )
    })? {
        let entry = entry.map_err(|_| {
            LayoutError::new(
                LayoutErrorCode::UnsafeStage,
                "stage entry could not be read",
            )
        })?;
        let file_name = entry.file_name().into_string().map_err(|_| {
            LayoutError::new(LayoutErrorCode::UnsafeStage, "stage entry is not UTF-8")
        })?;
        validate_relative_path(&file_name)?;
        let child_relative = relative.join(&file_name);
        let child = root.join(&child_relative);
        let metadata = fs::symlink_metadata(&child).map_err(|_| {
            LayoutError::new(
                LayoutErrorCode::UnsafeStage,
                "stage entry metadata is unavailable",
            )
        })?;
        if metadata.file_type().is_symlink() || is_reparse_point(&metadata) {
            return Err(LayoutError::new(
                LayoutErrorCode::UnsafeStage,
                "stage contains a link or reparse point",
            ));
        }
        let relative_string = child_relative.to_string_lossy().replace('\\', "/");
        if metadata.is_dir() {
            let prefix = format!("{relative_string}/");
            if !expected.iter().any(|path| path.starts_with(&prefix)) {
                return Err(LayoutError::new(
                    LayoutErrorCode::LayoutMismatch,
                    "stage contains an unlisted directory",
                ));
            }
            collect_stage_files(root, &child_relative, expected, files)?;
        } else if metadata.is_file() {
            files.push(StageFile {
                path: relative_string,
                bytes: metadata.len(),
                sha256: sha256_file(&child)?,
            });
        } else {
            return Err(LayoutError::new(
                LayoutErrorCode::UnsafeStage,
                "stage contains a non-regular entry",
            ));
        }
    }
    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(())
}

fn inspect_pe(
    bytes: &[u8],
    policy: &LayoutPolicyV1,
) -> Result<(String, Vec<String>, bool), LayoutError> {
    let pe = PeFile::from_bytes(bytes).map_err(|_| {
        LayoutError::new(
            LayoutErrorCode::PeRejected,
            "executable is not a valid PE file",
        )
    })?;
    if pe.file_header().Machine != 0x8664 {
        return Err(LayoutError::new(
            LayoutErrorCode::PeRejected,
            "PE machine is not AMD64",
        ));
    }
    let delay = pe.data_directory().get(13).ok_or_else(|| {
        LayoutError::new(
            LayoutErrorCode::PeRejected,
            "delay import directory is unavailable",
        )
    })?;
    let delay_present = delay.VirtualAddress != 0 || delay.Size != 0;
    if delay_present {
        return Err(LayoutError::new(
            LayoutErrorCode::PeRejected,
            "delay imports are not supported by layout policy v1",
        ));
    }
    let allowed = policy
        .normal_import_dll_allowlist
        .iter()
        .map(|name| name.to_ascii_lowercase())
        .collect::<BTreeSet<_>>();
    let mut imports = BTreeSet::new();
    for descriptor in pe.imports().map_err(|_| {
        LayoutError::new(
            LayoutErrorCode::PeRejected,
            "normal import table is invalid",
        )
    })? {
        let name = descriptor
            .dll_name()
            .map_err(|_| {
                LayoutError::new(LayoutErrorCode::PeRejected, "normal import name is invalid")
            })?
            .to_str()
            .map_err(|_| {
                LayoutError::new(
                    LayoutErrorCode::PeRejected,
                    "normal import name is not UTF-8",
                )
            })?
            .to_ascii_lowercase();
        if !allowed.contains(&name)
            || policy
                .forbidden_import_dll_tokens
                .iter()
                .any(|token| name.contains(&token.to_ascii_lowercase()))
        {
            return Err(LayoutError::new(
                LayoutErrorCode::PeRejected,
                "normal import is not allowed",
            ));
        }
        imports.insert(name);
    }
    Ok(("amd64".to_owned(), imports.into_iter().collect(), false))
}

fn run_smoke(
    stage: &Path,
    executable_relative: &str,
    smoke: &[SmokeCommandV1],
) -> Result<Vec<SmokeReportV1>, LayoutError> {
    let cwd = fresh_external_directory()?;
    let executable = stage_path(stage, executable_relative);
    let system_root = env::var("SystemRoot").map_err(|_| {
        LayoutError::new(LayoutErrorCode::SmokeRejected, "SystemRoot is unavailable")
    })?;
    let system_path = Path::new(&system_root).join("System32");
    let mut reports = Vec::new();
    for command in smoke {
        let output = Command::new(&executable)
            .args(&command.args)
            .current_dir(&cwd)
            .env_clear()
            .env("SystemRoot", &system_root)
            .env("WINDIR", &system_root)
            .env("PATH", &system_path)
            .output()
            .map_err(|_| {
                LayoutError::new(
                    LayoutErrorCode::SmokeRejected,
                    "smoke process could not start",
                )
            })?;
        validate_smoke_output(&output.stdout, &output.stderr, output.status.code())?;
        reports.push(SmokeReportV1 {
            args: command.args.clone(),
            exit_code: output.status.code().unwrap_or(-1),
            stdout_sha256: sha256_hex(&output.stdout),
            stderr_sha256: sha256_hex(&output.stderr),
        });
    }
    fs::remove_dir_all(&cwd).map_err(|_| {
        LayoutError::new(LayoutErrorCode::IoFailure, "smoke directory cleanup failed")
    })?;
    Ok(reports)
}

fn validate_smoke_output(
    stdout: &[u8],
    stderr: &[u8],
    exit_code: Option<i32>,
) -> Result<(), LayoutError> {
    if exit_code != Some(0)
        || !stdout.ends_with(b"\n")
        || stdout[..stdout.len() - 1].contains(&b'\n')
    {
        return Err(LayoutError::new(
            LayoutErrorCode::SmokeRejected,
            "smoke response shape is invalid",
        ));
    }
    let response: serde_json::Value =
        serde_json::from_slice(&stdout[..stdout.len() - 1]).map_err(|_| {
            LayoutError::new(LayoutErrorCode::SmokeRejected, "smoke stdout is not JSON")
        })?;
    if response.get("schema").and_then(serde_json::Value::as_str) != Some("sipi.cli.response.v1")
        || response.get("status").and_then(serde_json::Value::as_str) != Some("ok")
    {
        return Err(LayoutError::new(
            LayoutErrorCode::SmokeRejected,
            "smoke response was not successful",
        ));
    }
    for line in stderr
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
    {
        let diagnostic: serde_json::Value = serde_json::from_slice(line).map_err(|_| {
            LayoutError::new(LayoutErrorCode::SmokeRejected, "smoke stderr is not NDJSON")
        })?;
        if diagnostic.get("schema").and_then(serde_json::Value::as_str)
            != Some("sipi.cli.diagnostic.v1")
        {
            return Err(LayoutError::new(
                LayoutErrorCode::SmokeRejected,
                "smoke diagnostic schema is invalid",
            ));
        }
    }
    Ok(())
}

fn stage_path(stage: &Path, relative: &str) -> PathBuf {
    relative
        .split('/')
        .fold(stage.to_path_buf(), |path, component| path.join(component))
}

fn sha256_file(path: &Path) -> Result<String, LayoutError> {
    let bytes = fs::read(path).map_err(|_| {
        LayoutError::new(LayoutErrorCode::IoFailure, "stage file could not be read")
    })?;
    Ok(sha256_hex(&bytes))
}

fn sha256_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn fresh_external_directory() -> Result<PathBuf, LayoutError> {
    let tick = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| LayoutError::new(LayoutErrorCode::IoFailure, "clock is unavailable"))?
        .as_nanos();
    let path = env::temp_dir().join(format!("sipi-layout-smoke-{}-{tick}", std::process::id()));
    fs::create_dir(&path).map_err(|_| {
        LayoutError::new(
            LayoutErrorCode::IoFailure,
            "smoke directory could not be created",
        )
    })?;
    Ok(path)
}

#[cfg(windows)]
fn is_reparse_point(metadata: &fs::Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;

    metadata.file_attributes() & 0x400 != 0
}

#[cfg(not(windows))]
fn is_reparse_point(_metadata: &fs::Metadata) -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy() -> String {
        r#"{
          "schema":"sipi.release-layout-policy.v1",
          "platform":"windows-x86_64",
          "expectedExecutable":"sipi.exe",
          "requiredFiles":["sipi.exe","LICENSE","NOTICE"],
          "optionalFiles":[],
          "normalImportDllAllowlist":["kernel32.dll"],
          "forbiddenImportDllTokens":["python","pyami","agent-spice"],
          "smoke":[{"args":["version","--json"]}]
        }"#
        .to_owned()
    }

    #[test]
    fn policy_requires_an_explicit_import_allowlist() {
        let invalid = policy().replace("[\"kernel32.dll\"]", "[]");
        assert_eq!(
            parse_policy(invalid.as_bytes()).unwrap_err().code(),
            LayoutErrorCode::InvalidPolicy
        );
    }

    #[test]
    fn policy_rejects_case_colliding_paths() {
        let invalid = policy().replace("\"NOTICE\"]", "\"NOTICE\",\"notice\"]");
        assert_eq!(
            parse_policy(invalid.as_bytes()).unwrap_err().code(),
            LayoutErrorCode::InvalidPolicy
        );
    }

    #[test]
    fn stage_rejects_unlisted_content_before_pe_parsing() {
        let root = env::temp_dir().join(format!("sipi-layout-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir(&root).unwrap();
        fs::write(root.join("sipi.exe"), b"not-a-pe").unwrap();
        fs::write(root.join("LICENSE"), b"MIT").unwrap();
        fs::write(root.join("NOTICE"), b"scope").unwrap();
        fs::write(root.join("extra.py"), b"forbidden").unwrap();
        assert_eq!(
            verify_stage(&root, policy().as_bytes()).unwrap_err().code(),
            LayoutErrorCode::LayoutMismatch
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn smoke_requires_one_success_response_line() {
        assert!(
            validate_smoke_output(
                b"{\"schema\":\"sipi.cli.response.v1\",\"status\":\"ok\"}\n",
                b"",
                Some(0),
            )
            .is_ok()
        );
        assert_eq!(
            validate_smoke_output(b"human output\n", b"", Some(0))
                .unwrap_err()
                .code(),
            LayoutErrorCode::SmokeRejected
        );
    }

    #[test]
    fn mature_parser_accepts_the_current_test_pe_with_an_explicit_allowlist() {
        let executable = env::current_exe().unwrap();
        let bytes = fs::read(executable).unwrap();
        let pe = PeFile::from_bytes(&bytes).unwrap();
        let imports = pe
            .imports()
            .unwrap()
            .into_iter()
            .map(|descriptor| {
                descriptor
                    .dll_name()
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .to_ascii_lowercase()
            })
            .collect::<Vec<_>>();
        let mut policy = parse_policy(policy().as_bytes()).unwrap();
        policy.normal_import_dll_allowlist = imports;
        assert_eq!(inspect_pe(&bytes, &policy).unwrap().0, "amd64");
    }

    #[test]
    fn report_destination_cannot_be_inside_the_stage() {
        let root = env::temp_dir().join(format!("sipi-layout-report-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir(&root).unwrap();
        let report = LayoutReportV1 {
            schema: REPORT_SCHEMA,
            status: "layout_conformant",
            policy_sha256: "0".repeat(64),
            inventory_sha256: "0".repeat(64),
            executable_sha256: "0".repeat(64),
            executable_bytes: 0,
            machine: "amd64".to_owned(),
            normal_imports: vec![],
            delay_import_directory_present: false,
            smoke: vec![],
            limitations: vec![],
        };
        assert_eq!(
            write_report_outside_stage(&root, &root.join("report.json"), &report)
                .unwrap_err()
                .code(),
            LayoutErrorCode::UnsafeStage
        );
        fs::remove_dir_all(root).unwrap();
    }
}
