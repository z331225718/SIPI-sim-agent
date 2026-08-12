#![forbid(unsafe_code)]

//! External-only custody runner for the selected P3C S4P profile.
//!
//! This ignored test is invoked only by the external observer from a clean Git
//! archive. It writes hashes and aggregate facts to an external report; it
//! never writes the selected asset into the worktree.

use std::{
    env,
    fs::{self, File},
    io::{self, Read},
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use sha2::{Digest, Sha256};
use sipi_artifacts::ArtifactRoot;
use sipi_p3c::{
    SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_FILE_NAME_V1,
    SELECTED_P3C_S4P_SHA256_V1, SelectedP3cSealedS4pIdentityV1,
    admit_selected_p3c_sealed_s4p_v1,
};

const SOURCE_ENV: &str = "SIPI_P3C_SEALED_S4P_EXTERNAL_SOURCE";
const REPORT_ENV: &str = "SIPI_P3C_SEALED_S4P_RUNNER_REPORT";
const RUNNER_SCHEMA: &str = "sipi.p3c.sealed-selected-s4p-custody-runner.v1";

#[derive(Debug)]
struct RunFact {
    manifest_sha256: String,
    record_count: usize,
}

fn sha256_reader(mut reader: impl Read) -> io::Result<(u64, String)> {
    let mut digest = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        length = length.checked_add(read as u64).ok_or_else(|| io::Error::other("source_length_overflow"))?;
        digest.update(&buffer[..read]);
    }
    Ok((length, format!("{:x}", digest.finalize())))
}

fn source_identity(source: &Path) -> Result<(u64, String), String> {
    let file = File::open(source).map_err(|error| format!("source_open:{error}"))?;
    let identity = sha256_reader(file).map_err(|error| format!("source_hash:{error}"))?;
    if identity != (SELECTED_P3C_S4P_BYTE_LENGTH_V1, SELECTED_P3C_S4P_SHA256_V1.to_owned()) {
        return Err("source_identity_mismatch".to_owned());
    }
    Ok(identity)
}

fn fresh_root(index: usize) -> Result<PathBuf, String> {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| "clock_before_epoch".to_owned())?
        .as_nanos();
    let root = env::temp_dir().join(format!("sipi-p3c-sealed-s4p-{index}-{nonce}"));
    fs::create_dir(&root).map_err(|error| format!("root_create:{error}"))?;
    Ok(root)
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn observe_once(source: &Path, index: usize) -> Result<RunFact, String> {
    let before = source_identity(source)?;
    let root = fresh_root(index)?;
    let result = (|| {
        let store = ArtifactRoot::open_or_create(&root).map_err(|error| format!("artifact_root:{error:?}"))?;
        let artifact_id = format!("selected-s4p-{index}");
        let mut stage = store.begin(&artifact_id).map_err(|error| format!("artifact_begin:{error:?}"))?;
        let source_file = File::open(source).map_err(|error| format!("source_reopen:{error}"))?;
        stage
            .stage_reader(SELECTED_P3C_S4P_FILE_NAME_V1, source_file, SELECTED_P3C_S4P_BYTE_LENGTH_V1)
            .map_err(|error| format!("artifact_stage:{error:?}"))?;
        stage
            .seal()
            .map_err(|error| format!("artifact_seal:{error:?}"))?
            .publish_new()
            .map_err(|error| format!("artifact_publish:{error:?}"))?;

        let after = source_identity(source)?;
        if after != before {
            return Err("source_changed_during_materialization".to_owned());
        }
        let manifest = fs::read(root.join(&artifact_id).join("success.json"))
            .map_err(|error| format!("manifest_read:{error}"))?;
        let manifest_sha256 = sha256_bytes(&manifest);
        let reader = ArtifactRoot::open_existing(&root).map_err(|error| format!("artifact_reopen:{error:?}"))?;
        let identity = SelectedP3cSealedS4pIdentityV1::try_new(&artifact_id, &manifest_sha256)
            .map_err(|error| format!("identity:{error}"))?;
        let admitted = admit_selected_p3c_sealed_s4p_v1(&reader, &identity)
            .map_err(|error| format!("admission:{error}"))?;
        if admitted.source_byte_length() != before.0
            || admitted.source_sha256() != before.1
            || admitted.artifact_id() != artifact_id
            || admitted.manifest_sha256() != manifest_sha256
            || admitted.record_count() == 0
        {
            return Err("admission_provenance_mismatch".to_owned());
        }
        Ok(RunFact { manifest_sha256, record_count: admitted.record_count() })
    })();
    let cleanup = fs::remove_dir_all(&root).map_err(|error| format!("root_cleanup:{error}"));
    match (result, cleanup) {
        (Ok(fact), Ok(())) => Ok(fact),
        (Err(error), Ok(())) => Err(error),
        (_, Err(error)) => Err(error),
    }
}

fn required_path(name: &str) -> Result<PathBuf, String> {
    let raw = env::var_os(name).ok_or_else(|| format!("{name}_missing"))?;
    let path = PathBuf::from(raw);
    if !path.is_absolute() {
        return Err(format!("{name}_not_absolute"));
    }
    Ok(path)
}

fn write_report(report: &Path, first: &RunFact, second: &RunFact) -> Result<(), String> {
    let parent = report.parent().ok_or_else(|| "report_parent_missing".to_owned())?;
    fs::create_dir_all(parent).map_err(|error| format!("report_parent_create:{error}"))?;
    let payload = format!(
        concat!(
            "{{\"schema\":\"{}\",\"status\":\"observed\",",
            "\"source_byte_length\":{},",
            "\"source_sha256\":\"{}\",",
            "\"source_identity_checks\":\"before_stage_after_equal\",",
            "\"fresh_runs\":[",
            "{{\"manifest_sha256\":\"{}\",\"record_count\":{}}},",
            "{{\"manifest_sha256\":\"{}\",\"record_count\":{}}}",
            "],\"cleanup_status\":\"complete\"}}\n"
        ),
        RUNNER_SCHEMA,
        SELECTED_P3C_S4P_BYTE_LENGTH_V1,
        SELECTED_P3C_S4P_SHA256_V1,
        first.manifest_sha256,
        first.record_count,
        second.manifest_sha256,
        second.record_count,
    );
    fs::write(report, payload).map_err(|error| format!("report_write:{error}"))
}

fn run() -> Result<(), String> {
    let source = required_path(SOURCE_ENV)?;
    let report = required_path(REPORT_ENV)?;
    let first = observe_once(&source, 1)?;
    let second = observe_once(&source, 2)?;
    if first.record_count != second.record_count || first.manifest_sha256 == second.manifest_sha256 {
        return Err("fresh_runs_not_independent_or_consistent".to_owned());
    }
    write_report(&report, &first, &second)
}

#[test]
#[ignore = "external-only custody observation; requires explicit external source and report paths"]
fn p3c_sealed_s4p_external_runner() {
    run().unwrap_or_else(|error| panic!("p3c_sealed_s4p_external_runner_failed:{error}"));
}
