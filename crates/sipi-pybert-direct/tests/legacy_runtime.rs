use std::{collections::BTreeMap, fs, path::PathBuf};

use serde::Deserialize;
use sipi_pybert_direct::{LegacySimRequestV1, run_legacy_sim_v1};

const EXPECTED_ITEM_NAMES: [&str; 23] = [
    "chnl_h",
    "tx_out_h",
    "ctle_out_h",
    "dfe_out_h",
    "chnl_s",
    "tx_s",
    "ctle_s",
    "dfe_s",
    "tx_out_s",
    "ctle_out_s",
    "dfe_out_s",
    "chnl_p",
    "tx_out_p",
    "ctle_out_p",
    "dfe_out_p",
    "chnl_H",
    "tx_H",
    "ctle_H",
    "dfe_H",
    "tx_out_H",
    "ctle_out_H",
    "dfe_out_H",
    "tx_out",
];

#[derive(Deserialize)]
struct LegacyPickleProbe {
    schema: String,
    item_names: Vec<String>,
    arrays: BTreeMap<String, Vec<f64>>,
}

#[test]
fn pinned_legacy_fixture_runs_in_rust_and_writes_python_pickle_dict() {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml");
    let root = std::env::temp_dir().join(format!("sipi-pb01-runtime-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let result = root.join("fixture.pybert_data");
    let report = run_legacy_sim_v1(&LegacySimRequestV1 {
        config_file: fixture,
        results: Some(result.clone()),
    })
    .unwrap();
    assert_eq!(report.input.timebase.nbits, 1_000);
    assert!(report.output.arrays.contains_key("channel_impulse_v_per_v"));
    let bytes = fs::read(&result).unwrap();
    assert_eq!(&bytes[..2], b"\x80\x03");
    let payload: LegacyPickleProbe =
        serde_pickle::from_slice(&bytes, serde_pickle::DeOptions::default()).unwrap();
    assert_eq!(payload.schema, "sipi.pybert_data.v1");
    assert_eq!(payload.item_names, EXPECTED_ITEM_NAMES);
    assert_eq!(
        payload
            .arrays
            .keys()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        EXPECTED_ITEM_NAMES
            .iter()
            .copied()
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>()
    );
    let _ = fs::remove_dir_all(root);
}
