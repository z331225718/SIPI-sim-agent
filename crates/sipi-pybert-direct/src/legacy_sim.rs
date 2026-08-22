//! PB-01 (`pybert sim`) predecessor workflow-boundary contract.
//!
//! The pinned command accepts a legacy `PyBertCfg` file and writes one legacy
//! `PyBertData` pickle. This module preserves the argument/default/error/
//! artifact decisions used by `legacy_runtime`. Its `BlockedLegacyProjection`
//! result describes only the older boundary-only candidate and is superseded
//! by the executable scoped leaf; it does not describe the remaining unported
//! PB-01 branches.

use std::{
    fs, io,
    path::{Path, PathBuf},
};

use thiserror::Error;

/// The pinned upstream command name.
pub const PB01_COMMAND: &str = "sim";
/// The suffix used by the upstream default result path.
pub const DEFAULT_RESULT_EXTENSION: &str = "pybert_data";
/// Legacy configuration suffixes accepted by `PyBertCfg.load_from_file`.
pub const LEGACY_CONFIG_EXTENSIONS: &[&str] = &[".yaml", ".yml", ".pybert_cfg"];
/// Existing native-core entry point used by the executable scoped leaf.
pub const NATIVE_CORE_ENTRYPOINT: &str = "run_sim_native_file";

/// Exact PB-01 command-line request, without shell interpolation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LegacySimRequestV1 {
    pub config_file: PathBuf,
    pub results: Option<PathBuf>,
}

impl LegacySimRequestV1 {
    /// Return the argv shape emitted by the pinned `sim` command.
    pub fn command_manifest(&self) -> Result<Vec<OsStringLike>, LegacySimError> {
        let mut argv = vec![
            OsStringLike::from(PB01_COMMAND),
            OsStringLike::from_path(&self.config_file)?,
        ];
        if let Some(results) = &self.results {
            argv.push(OsStringLike::from("--results"));
            argv.push(OsStringLike::from_path(results)?);
        }
        Ok(argv)
    }

    /// Resolve the upstream default when `--results` is omitted.
    pub fn resolved_results_path(&self) -> Result<PathBuf, LegacySimError> {
        if let Some(results) = &self.results {
            if results.as_os_str().is_empty() {
                return Err(LegacySimError::EmptyResultsPath);
            }
            return Ok(results.clone());
        }
        let mut path = self.config_file.clone();
        if path.file_name().is_none() {
            return Err(LegacySimError::InvalidConfigPath);
        }
        path.set_extension(DEFAULT_RESULT_EXTENSION.trim_start_matches('.'));
        Ok(path)
    }
}

/// A small path-free argv item used by evidence and focused tests.
///
/// The real process adapter owns platform-specific `OsString` handling.  The
/// candidate contract intentionally exposes only a UTF-8 manifest so it never
/// silently lossy-converts a path during execution.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct OsStringLike(String);

impl OsStringLike {
    fn from(value: &str) -> Self {
        Self(value.to_owned())
    }

    fn from_path(value: &Path) -> Result<Self, LegacySimError> {
        value
            .to_str()
            .map(|value| Self(value.to_owned()))
            .ok_or(LegacySimError::NonUtf8Path)
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// Validate the branch that the pinned `sim` command reaches before its
/// Python simulation backend is called.
pub fn validate_legacy_sim_request(request: &LegacySimRequestV1) -> Result<(), LegacySimError> {
    let metadata = fs::metadata(&request.config_file).map_err(LegacySimError::ConfigIo)?;
    if !metadata.is_file() {
        return Err(LegacySimError::ConfigNotRegular);
    }
    let extension = request
        .config_file
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{value}"))
        .ok_or(LegacySimError::UnsupportedConfigExtension)?;
    if !LEGACY_CONFIG_EXTENSIONS.contains(&extension.as_str()) {
        return Err(LegacySimError::UnsupportedConfigExtension);
    }
    let results = request.resolved_results_path()?;
    if paths_alias(&request.config_file, &results).map_err(LegacySimError::ResultsIo)? {
        return Err(LegacySimError::ResultsAliasConfig);
    }
    Ok(())
}

fn paths_alias(left: &Path, right: &Path) -> io::Result<bool> {
    match fs::metadata(right) {
        Ok(_) => same_file::is_same_file(left, right),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error),
    }
}

/// Historical boundary-only candidate status retained for predecessor tools.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LegacySimCandidateStatus {
    ReadyForExternalOracle,
    BlockedLegacyProjection,
}

/// Validate the request and return the predecessor candidate status.
///
/// The executable YAML projection now lives in `legacy_runtime`; this helper
/// remains fail-closed so old boundary-only consumers cannot claim execution.
pub fn prepare_legacy_sim_v1(
    request: &LegacySimRequestV1,
) -> Result<LegacySimCandidateStatus, LegacySimError> {
    validate_legacy_sim_request(request)?;
    Ok(LegacySimCandidateStatus::BlockedLegacyProjection)
}

/// Errors observed or intentionally surfaced at the PB-01 contract boundary.
#[derive(Debug, Error)]
pub enum LegacySimError {
    #[error("PB-01 config file could not be read: {0}")]
    ConfigIo(#[source] io::Error),
    #[error("PB-01 config path must name a regular file")]
    ConfigNotRegular,
    #[error("PB-01 config extension must be .yaml, .yml, or .pybert_cfg")]
    UnsupportedConfigExtension,
    #[error("PB-01 config path is invalid")]
    InvalidConfigPath,
    #[error("PB-01 --results path must not be empty")]
    EmptyResultsPath,
    #[error("PB-01 --results path must not alias the configuration file")]
    ResultsAliasConfig,
    #[error("PB-01 --results path could not be inspected: {0}")]
    ResultsIo(#[source] io::Error),
    #[error("PB-01 command manifest requires UTF-8 paths")]
    NonUtf8Path,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_result_path_matches_pinned_cli() {
        let request = LegacySimRequestV1 {
            config_file: PathBuf::from("case.yaml"),
            results: None,
        };
        assert_eq!(
            request.resolved_results_path().unwrap(),
            PathBuf::from("case.pybert_data")
        );
    }

    #[test]
    fn explicit_result_path_is_forwarded_without_rewriting() {
        let request = LegacySimRequestV1 {
            config_file: PathBuf::from("case.yml"),
            results: Some(PathBuf::from("artifacts/custom.result")),
        };
        assert_eq!(
            request.resolved_results_path().unwrap(),
            PathBuf::from("artifacts/custom.result")
        );
        assert_eq!(
            request
                .command_manifest()
                .unwrap()
                .iter()
                .map(OsStringLike::as_str)
                .collect::<Vec<_>>(),
            vec!["sim", "case.yml", "--results", "artifacts/custom.result"]
        );
    }

    #[test]
    fn unsupported_config_extension_fails_before_projection() {
        let root = std::env::temp_dir().join(format!("sipi-pb01-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let path = root.join("case.json");
        fs::write(&path, b"{}").unwrap();
        let request = LegacySimRequestV1 {
            config_file: path,
            results: None,
        };
        assert!(matches!(
            validate_legacy_sim_request(&request),
            Err(LegacySimError::UnsupportedConfigExtension)
        ));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn valid_legacy_request_remains_explicitly_blocked_for_projection() {
        let root = std::env::temp_dir().join(format!("sipi-pb01-valid-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let path = root.join("case.yaml");
        fs::write(&path, b"not parsed by this candidate\n").unwrap();
        let request = LegacySimRequestV1 {
            config_file: path,
            results: None,
        };
        assert_eq!(
            prepare_legacy_sim_v1(&request).unwrap(),
            LegacySimCandidateStatus::BlockedLegacyProjection
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn result_hard_link_to_config_is_rejected() {
        let root = std::env::temp_dir().join(format!("sipi-pb01-alias-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let config = root.join("case.yaml");
        let result = root.join("alias.pybert_data");
        fs::write(&config, b"config\n").unwrap();
        fs::hard_link(&config, &result).unwrap();
        let request = LegacySimRequestV1 {
            config_file: config,
            results: Some(result),
        };
        assert!(matches!(
            validate_legacy_sim_request(&request),
            Err(LegacySimError::ResultsAliasConfig)
        ));
        let _ = fs::remove_dir_all(root);
    }
}
