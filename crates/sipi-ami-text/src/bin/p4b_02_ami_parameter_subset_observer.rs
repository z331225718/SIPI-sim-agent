//! Hash-only external observation for the selected ADS AMI text profiles.
//!
//! This tool reads each exact `.ami` file twice, parses both bytes through the
//! bounded clean-room parser, and emits only identity/digest/count evidence.
//! It never opens a DLL and never invokes an AMI ABI entry point.

use std::{
    env,
    error::Error,
    fmt,
    fs::{self, File},
    io::{self, Read},
    path::{Path, PathBuf},
};

use sha2::{Digest, Sha256};
use sipi_ami_text::{
    AMI_PARAMETER_SUBSET_POLICY_V1, AMI_PARAMETER_TREE_POLICY_V1, AmiForwardedParameterSubsetV1,
    AmiParameterProfileLimitsV1, AmiParameterProfileRoleV1, ParseLimitsV1,
    build_ami_parameter_tree_v1, build_forwarded_parameter_subset_v1, parse_and_bind_v1,
    selected_rx_forwarded_parameters_v1, selected_tx_forwarded_parameters_v1,
};

const SCHEMA: &str = "sipi.p4b-02.ami-parameter-subset-observation.v1";
const STATUS: &str =
    "external_only_host_forwarded_parameter_subset_observed_dll_consumption_unproven";
const DECISION: &str = "external_asset_oracle";
const MAX_ASSET_BYTES: u64 = 1024 * 1024;
const FRESH_READS: u64 = 2;

#[derive(Debug)]
enum ObserverError {
    Usage,
    MissingArgument(&'static str),
    Read(PathBuf, io::Error),
    AssetTooLarge(PathBuf),
    FreshReadMismatch(PathBuf),
    Parse(&'static str, String),
    Tree(&'static str, String),
    Subset(&'static str, String),
    Report(io::Error),
    Encode(serde_json::Error),
}

impl fmt::Display for ObserverError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Usage => write!(f, "usage: --tx-ami PATH --rx-ami PATH --report PATH"),
            Self::MissingArgument(name) => write!(f, "missing argument {name}"),
            Self::Read(path, error) => write!(f, "read {}: {error}", path.display()),
            Self::AssetTooLarge(path) => {
                write!(f, "asset exceeds bounded read: {}", path.display())
            }
            Self::FreshReadMismatch(path) => write!(f, "fresh reads differ: {}", path.display()),
            Self::Parse(role, error) => write!(f, "{role} parse failed: {error}"),
            Self::Tree(role, error) => write!(f, "{role} parameter tree failed: {error}"),
            Self::Subset(role, error) => write!(f, "{role} forwarded subset failed: {error}"),
            Self::Report(error) => write!(f, "write report: {error}"),
            Self::Encode(error) => write!(f, "encode report: {error}"),
        }
    }
}

impl Error for ObserverError {}

struct Args {
    tx: PathBuf,
    rx: PathBuf,
    report: PathBuf,
}

fn parse_args() -> Result<Args, ObserverError> {
    let mut tx = None;
    let mut rx = None;
    let mut report = None;
    let mut args = env::args().skip(1);
    while let Some(flag) = args.next() {
        let value = args.next().ok_or(ObserverError::Usage)?;
        match flag.as_str() {
            "--tx-ami" => tx = Some(PathBuf::from(value)),
            "--rx-ami" => rx = Some(PathBuf::from(value)),
            "--report" => report = Some(PathBuf::from(value)),
            _ => return Err(ObserverError::Usage),
        }
    }
    Ok(Args {
        tx: tx.ok_or(ObserverError::MissingArgument("--tx-ami"))?,
        rx: rx.ok_or(ObserverError::MissingArgument("--rx-ami"))?,
        report: report.ok_or(ObserverError::MissingArgument("--report"))?,
    })
}

fn read_bounded(path: &Path) -> Result<Vec<u8>, ObserverError> {
    let metadata =
        fs::metadata(path).map_err(|error| ObserverError::Read(path.to_owned(), error))?;
    if metadata.len() > MAX_ASSET_BYTES {
        return Err(ObserverError::AssetTooLarge(path.to_owned()));
    }
    let file = File::open(path).map_err(|error| ObserverError::Read(path.to_owned(), error))?;
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    file.take(MAX_ASSET_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| ObserverError::Read(path.to_owned(), error))?;
    if bytes.len() as u64 > MAX_ASSET_BYTES {
        return Err(ObserverError::AssetTooLarge(path.to_owned()));
    }
    Ok(bytes)
}

fn read_fresh(path: &Path) -> Result<Vec<u8>, ObserverError> {
    let first = read_bounded(path)?;
    let second = read_bounded(path)?;
    if first != second {
        return Err(ObserverError::FreshReadMismatch(path.to_owned()));
    }
    Ok(first)
}

fn hash_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn selected_paths_sha256(subset: &AmiForwardedParameterSubsetV1) -> String {
    let mut bytes = Vec::new();
    for parameter in subset.parameters() {
        bytes.extend_from_slice(parameter.path().len().to_string().as_bytes());
        bytes.push(b':');
        bytes.extend_from_slice(parameter.path().as_bytes());
        bytes.push(b'|');
    }
    hash_hex(&bytes)
}

fn observe_profile(
    role_name: &'static str,
    role: AmiParameterProfileRoleV1,
    bytes: &[u8],
) -> Result<serde_json::Value, ObserverError> {
    let parse_limits = ParseLimitsV1::try_new(1_048_576, 64, 8_192, 8_192)
        .map_err(|error| ObserverError::Parse(role_name, error.to_string()))?;
    let binding = parse_and_bind_v1(bytes, parse_limits)
        .map_err(|error| ObserverError::Parse(role_name, error.to_string()))?;
    let profile_limits = AmiParameterProfileLimitsV1::selected_profile();
    let tree = build_ami_parameter_tree_v1(&binding, role, profile_limits)
        .map_err(|error| ObserverError::Tree(role_name, error.to_string()))?;
    let selections = match role {
        AmiParameterProfileRoleV1::Tx => selected_tx_forwarded_parameters_v1(),
        AmiParameterProfileRoleV1::Rx => selected_rx_forwarded_parameters_v1(),
    };
    let subset = build_forwarded_parameter_subset_v1(&tree, &selections)
        .map_err(|error| ObserverError::Subset(role_name, error.to_string()))?;
    Ok(serde_json::json!({
        "role": role.token(),
        "root_name": tree.root_name(),
        "byte_len": bytes.len(),
        "source_sha256": tree.source_sha256(),
        "tree_digest": tree.canonical_digest(),
        "subset_digest": subset.canonical_digest(),
        "selected_count": subset.parameters().len(),
        "selected_paths_sha256": selected_paths_sha256(&subset),
        "limits": {
            "parse_max_input_bytes": parse_limits.max_input_bytes().get(),
            "parse_max_nesting_depth": parse_limits.max_nesting_depth().get(),
            "parse_max_nodes": parse_limits.max_nodes().get(),
            "parse_max_token_bytes": parse_limits.max_token_bytes().get(),
            "profile_max_entries": profile_limits.max_entries(),
            "profile_max_depth": profile_limits.max_depth(),
            "profile_max_metadata_forms": profile_limits.max_metadata_forms(),
            "profile_max_value_bytes": profile_limits.max_value_bytes(),
            "profile_max_selected": profile_limits.max_selected(),
        },
    }))
}

fn run() -> Result<(), ObserverError> {
    let args = parse_args()?;
    let tx = read_fresh(&args.tx)?;
    let rx = read_fresh(&args.rx)?;
    let report = serde_json::json!({
        "schema": SCHEMA,
        "decision": DECISION,
        "policy": AMI_PARAMETER_SUBSET_POLICY_V1,
        "tree_policy": AMI_PARAMETER_TREE_POLICY_V1,
        "status": STATUS,
        "fresh_reads": FRESH_READS,
        "profiles": {
            "tx": observe_profile("tx", AmiParameterProfileRoleV1::Tx, &tx)?,
            "rx": observe_profile("rx", AmiParameterProfileRoleV1::Rx, &rx)?,
        },
        "runtime_observation": {
            "dll_loaded": false,
            "ami_init_invoked": false,
            "ami_get_wave_invoked": false,
            "selected_values_emitted": false,
        },
        "non_claims": [
            "host_forwarded_subset_identity_only",
            "vendor_dll_consumption_unproven",
            "ami_runtime_acceptance_unproven",
            "rights_and_dynamic_closure_not_established",
        ],
    });
    let bytes = serde_json::to_vec_pretty(&report).map_err(ObserverError::Encode)?;
    fs::write(args.report, bytes).map_err(ObserverError::Report)
}

fn main() {
    if let Err(error) = run() {
        eprintln!("p4b_02 observer: {error}");
        std::process::exit(2);
    }
}
