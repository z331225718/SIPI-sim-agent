use std::{collections::BTreeMap, fs, path::PathBuf, process::Command};

use serde::Deserialize;
use sha2::{Digest, Sha256};
use sipi_pybert_direct::{
    ChannelInputV1, LegacyResultCodecV1, LegacyRuntimeError, LegacySimRequestV1, ModulationV1,
    project_legacy_config_v1, run_legacy_sim_v1, run_legacy_sim_with_codec_v1, simulate_native_v1,
};

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

fn projection_yaml(extra: &str) -> String {
    format!(
        r#"!!python/object:pybert.configuration.PyBertCfg
bit_rate: 10.0
nbits: 1000
pattern: PRBS-7
seed: 17
nspui: 2
{}
"#,
        extra
    )
}

fn write_s2p(root: &std::path::Path, name: &str) -> std::path::PathBuf {
    let path = root.join(name);
    fs::write(
        &path,
        "# GHz S RI R 50\n0 0 0 1 0 0 0 0 0\n1 0 0 0.8 0.1 0 0 0 0\n2 0 0 0.5 0.2 0 0 0 0\n",
    )
    .unwrap();
    path
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
    for name in EXPECTED_ITEM_NAMES.iter() {
        assert!(
            !payload.arrays[*name].is_empty(),
            "{name} must be populated"
        );
    }
    for name in EXPECTED_ITEM_NAMES
        .iter()
        .filter(|name| name.ends_with("_H"))
    {
        assert!(
            !payload.arrays[*name].is_empty(),
            "{name} must be populated"
        );
    }
    assert_ne!(
        payload.arrays["ctle_out_h"], payload.arrays["dfe_out_h"],
        "DFE output response must not alias CTLE output"
    );
    assert_ne!(
        payload.arrays["ctle_out_H"], payload.arrays["dfe_out_H"],
        "DFE frequency response must not alias CTLE frequency response"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn legacy_class_result_uses_pinned_pybert_object_graph() {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml");
    let root = std::env::temp_dir().join(format!("sipi-pb01-class-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let result = root.join("fixture.pybert_data");
    let report = run_legacy_sim_with_codec_v1(
        &LegacySimRequestV1 {
            config_file: fixture,
            results: Some(result.clone()),
        },
        LegacyResultCodecV1::ClassPickle,
    )
    .unwrap();
    assert!(report.output.arrays.contains_key("tx_waveform_v"));
    let bytes = fs::read(&result).unwrap();
    assert_eq!(&bytes[..2], b"\x80\x03");
    for marker in [
        b"pybert.results\nPyBertData\n".as_slice(),
        b"chaco.array_plot_data\nArrayPlotData\n".as_slice(),
        b"traits.trait_dict_object\nTraitDictObject\n".as_slice(),
        b"numpy._core.multiarray\n_reconstruct\n".as_slice(),
        b"numpy\ndtype\n".as_slice(),
    ] {
        assert!(bytes.windows(marker.len()).any(|window| window == marker));
    }
    for name in EXPECTED_ITEM_NAMES {
        let mut encoded_name = vec![b'X'];
        encoded_name.extend_from_slice(&(name.len() as u32).to_le_bytes());
        encoded_name.extend_from_slice(name.as_bytes());
        assert_eq!(
            bytes
                .windows(encoded_name.len())
                .filter(|window| *window == encoded_name.as_slice())
                .count(),
            1,
            "class pickle must contain each canonical item exactly once: {name}"
        );
    }
    assert!(
        !bytes
            .windows(b"sipi.pybert_data.v1".len())
            .any(|window| { window == b"sipi.pybert_data.v1" })
    );
    // The class codec carries real PyBERT object-array semantics for
    // `tx_out`, so the serialized byte stream is intentionally not frozen as
    // a SIPI-specific fingerprint.  Class/load behavior is checked below and
    // in the optional pinned-Python integration test.
    let original_digest = Sha256::digest(&bytes);
    assert!(bytes.len() < 512 * 1024 * 1024);
    let error = run_legacy_sim_with_codec_v1(
        &LegacySimRequestV1 {
            config_file: PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("fixtures")
                .join("pb-01-legacy-nrz.yaml"),
            results: Some(result.clone()),
        },
        LegacyResultCodecV1::ClassPickle,
    )
    .unwrap_err();
    assert!(
        matches!(error, LegacyRuntimeError::InvalidConfig(message) if message.contains("already exists"))
    );
    assert_eq!(Sha256::digest(fs::read(&result).unwrap()), original_digest);
    assert!(
        fs::read_dir(&root)
            .unwrap()
            .filter_map(Result::ok)
            .all(|entry| !entry
                .file_name()
                .to_string_lossy()
                .starts_with(".sipi-pb01-result-"))
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn legacy_cli_reaches_class_codec_and_rejects_format_drift() {
    let binary = env!("CARGO_BIN_EXE_sipi-pybert-direct");
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml");
    let root = std::env::temp_dir().join(format!("sipi-pb01-cli-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let default_result = root.join("default.pybert_data");
    let status = Command::new(binary)
        .arg("sim")
        .arg(&fixture)
        .arg("--results")
        .arg(&default_result)
        .status()
        .unwrap();
    assert!(status.success());
    assert!(
        fs::read(&default_result)
            .unwrap()
            .windows(b"pybert.results\nPyBertData\n".len())
            .any(|window| window == b"pybert.results\nPyBertData\n")
    );

    let result = root.join("class.pybert_data");
    let status = Command::new(binary)
        .arg("sim")
        .arg(&fixture)
        .arg("--result-format")
        .arg("class-pickle")
        .arg("--results")
        .arg(&result)
        .status()
        .unwrap();
    assert!(status.success());
    assert!(
        fs::read(&result)
            .unwrap()
            .windows(b"pybert.results\nPyBertData\n".len())
            .any(|window| window == b"pybert.results\nPyBertData\n")
    );

    let dictionary = root.join("dictionary.pybert_data");
    let status = Command::new(binary)
        .arg("sim")
        .arg(&fixture)
        .arg("--result-format")
        .arg("sipi-dictionary")
        .arg("--results")
        .arg(&dictionary)
        .status()
        .unwrap();
    assert!(status.success());
    assert!(
        fs::read(&dictionary)
            .unwrap()
            .windows(b"sipi.pybert_data.v1".len())
            .any(|window| window == b"sipi.pybert_data.v1")
    );

    for arguments in [
        vec!["--result-format", "future"],
        vec![
            "--result-format",
            "class-pickle",
            "--result-format",
            "class-pickle",
        ],
    ] {
        let rejected = root.join(format!("rejected-{}.pybert_data", arguments.len()));
        let status = Command::new(binary)
            .arg("sim")
            .arg(&fixture)
            .args(arguments)
            .arg("--results")
            .arg(&rejected)
            .status()
            .unwrap();
        assert_eq!(status.code(), Some(2));
        assert!(!rejected.exists());
    }
    let _ = fs::remove_dir_all(root);
}

#[cfg(feature = "pinned-python-tests")]
#[test]
fn pinned_python_loads_exact_class_graph_and_all_logical_arrays() {
    let python = std::env::var_os("SIPI_PYBERT_PINNED_PYTHON")
        .expect("pinned-python-tests requires SIPI_PYBERT_PINNED_PYTHON");
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml");
    let root = std::env::temp_dir().join(format!("sipi-pb01-pinned-load-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let class_pickle = root.join("class.pybert_data");
    run_legacy_sim_with_codec_v1(
        &LegacySimRequestV1 {
            config_file: fixture,
            results: Some(class_pickle.clone()),
        },
        LegacyResultCodecV1::ClassPickle,
    )
    .unwrap();

    const PROBE: &str = r#"
import hashlib, io, pickle, pickletools, sys
from collections import Counter
import numpy as np

class_path = sys.argv[1]
data = open(class_path, "rb").read()
allowed = {
    "pybert.results PyBertData",
    "chaco.array_plot_data ArrayPlotData",
    "traits.trait_dict_object TraitDictObject",
    "numpy._core.multiarray _reconstruct",
    "numpy ndarray",
    "numpy dtype",
    "builtins getattr",
}
globals_seen = [arg for op, arg, _ in pickletools.genops(data) if op.name == "GLOBAL"]
expected_globals = Counter({
    "pybert.results PyBertData": 1,
    "chaco.array_plot_data ArrayPlotData": 1,
    "traits.trait_dict_object TraitDictObject": 1,
    "numpy._core.multiarray _reconstruct": 23,
    "numpy ndarray": 23,
    "numpy dtype": 23,
    "builtins getattr": 2,
})
assert Counter(globals_seen) == expected_globals, (Counter(globals_seen), expected_globals)
assert set(globals_seen) == allowed

class BoundedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        identity = f"{module} {name}"
        assert identity in allowed, identity
        return super().find_class(module, name)

root = BoundedUnpickler(io.BytesIO(data)).load()
assert (type(root).__module__, type(root).__name__) == ("pybert.results", "PyBertData")
assert (type(root.the_data).__module__, type(root.the_data).__name__) == (
    "chaco.array_plot_data", "ArrayPlotData"
)
arrays = root.the_data.arrays
assert (type(arrays).__module__, type(arrays).__name__) == (
    "traits.trait_dict_object", "TraitDictObject"
)
expected_names = [
    "chnl_h", "tx_out_h", "ctle_out_h", "dfe_out_h", "chnl_s", "tx_s",
    "ctle_s", "dfe_s", "tx_out_s", "ctle_out_s", "dfe_out_s", "chnl_p",
    "tx_out_p", "ctle_out_p", "dfe_out_p", "chnl_H", "tx_H", "ctle_H",
    "dfe_H", "tx_out_H", "ctle_out_H", "dfe_out_H", "tx_out",
]
assert list(arrays.keys()) == expected_names
expected = {
    "chnl_h": (640, "d9786d1c2014dd5baea1f4879a9dcfc0e4b404fe9786c538b9ec1e86356db930"),
    "tx_out_h": (640, "02f709a6632dbe1df72023cc41a2a4b0f1fb4164b5ee921e7cb62029f00159c9"),
    "ctle_out_h": (640, "02f709a6632dbe1df72023cc41a2a4b0f1fb4164b5ee921e7cb62029f00159c9"),
    "dfe_out_h": (640, "4a337ca621d43ac7a06c0d58ce9f2e8d22658da1f0d617026bc62d50c26d1591"),
    "chnl_s": (640, "8184546a0842f8be5a696ee4f93649aa679c5543a95e00a8788990db003ce095"),
    "tx_s": (640, "9f53ade3b540318594b3f3416bdedeaabfd180237c6b28437c425a2231d3524d"),
    "ctle_s": (960, "19991170f3d158846e457c8fcd1d17bfbf7d9cd992ae16482d2dc00cf4c8668f"),
    "dfe_s": (640, "ed07ce8b9a09d9104d336ceafdbbfef7f85a7c7198cf416e0070a54b4bc366ca"),
    "tx_out_s": (640, "a98e7ab29b49071da6433c33df05263f4fa428049bab7a067d45393a47a5e50f"),
    "ctle_out_s": (640, "a98e7ab29b49071da6433c33df05263f4fa428049bab7a067d45393a47a5e50f"),
    "dfe_out_s": (640, "6d90a04bd26cd4fba9aec1fa4f575d34e26b3d41e92a067cd48a1a2fbfb86d04"),
    "chnl_p": (640, "27a36801b4797ff508c32659866dd351e1042955262f039d8f64444f93f39a4e"),
    "tx_out_p": (640, "5df2ad4bff0250ce1ce1ecd011b8b1a17dc3e40aeaf32067fc4d16c852254ba8"),
    "ctle_out_p": (640, "5df2ad4bff0250ce1ce1ecd011b8b1a17dc3e40aeaf32067fc4d16c852254ba8"),
    "dfe_out_p": (640, "d9b785f9648f83122f06f35795eef9cfb836d8e829e135bbbca8d9e9a12f9174"),
    "chnl_H": (400, "b1f21c045d988e994b4a134d872eaaa7cf253db75e1ea3fc6e27d9562f3df6c1"),
    "tx_H": (400, "1d12882e1eb204a20aaa51cd92c87194bf89da6eef2c4b633ce6aaf328cef3ca"),
    "ctle_H": (400, "5a312281df4bd8dfbb4d4a94ad0bf44d01bb8cfced1206b90e21b4ca0568cdb1"),
    "dfe_H": (400, "5a312281df4bd8dfbb4d4a94ad0bf44d01bb8cfced1206b90e21b4ca0568cdb1"),
    "tx_out_H": (400, "2525885485b5d165fd23ceed6c94d68ead2bde341139809b2a1e97cd2316adad"),
    "ctle_out_H": (400, "2525885485b5d165fd23ceed6c94d68ead2bde341139809b2a1e97cd2316adad"),
    "dfe_out_H": (400, "0570b7b150fdb201bd2e3166f88c8ca63e153182c474ba6bd3b11e1862603db2"),
}
assert list(expected) == expected_names[:-1]
for name in expected_names:
    actual = arrays[name]
    if name == "tx_out":
        assert type(actual) is np.ndarray, (name, type(actual))
        assert actual.dtype == np.dtype("O"), (name, actual.dtype)
        assert actual.ndim == 0 and actual.shape == (), (name, actual.shape)
        assert actual.item() is None, actual.item()
        continue
    expected_length, expected_digest = expected[name]
    assert type(actual) is np.ndarray, (name, type(actual))
    assert actual.dtype == np.dtype("<f8"), (name, actual.dtype)
    assert actual.ndim == 1 and actual.shape == (expected_length,), (name, actual.shape)
    assert actual.flags.c_contiguous, name
    actual_digest = hashlib.sha256(actual.tobytes(order="C")).hexdigest()
    assert actual_digest == expected_digest, name
assert root.date_created == "not-recorded"
assert root.version == "sipi-pybert-direct/0.1.0 class-pickle-v1 noncanonical"
print("bounded-class-load-ok")
"#;
    let output = Command::new(python)
        .args(["-c", PROBE])
        .arg(&class_pickle)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "stdout={} stderr={}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        String::from_utf8_lossy(&output.stdout).trim(),
        "bounded-class-load-ok"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_covers_portable_modulation_noise_and_viterbi_fields() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-projection-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config_path = root.join("pam4.yaml");
    fs::write(
        &config_path,
        projection_yaml(
            "f_max: 2.0\nmod_type: PAM-4\npn_mag: 0.001\npn_freq: 1000.0\nrn: 0.001\nrx_use_viterbi: true\nrx_viterbi_symbols: 2\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]",
        ),
    )
    .unwrap();
    let (_, input) = project_legacy_config_v1(&config_path, "portable-fields").unwrap();
    assert!(matches!(input.modulation, ModulationV1::Pam4));
    assert_eq!(input.timebase.data_rate.0, 5.0e9);
    assert_eq!(input.timebase.sample_interval.0, 100.0e-12);
    assert_eq!(input.analysis.jitter_eye_uis, Some(5_080));
    assert_eq!(
        input.tx.additive_noise.as_ref().unwrap().samples_v.len(),
        1000
    );
    assert!(input.tx.additive_noise.is_some());
    assert!(input.tx.periodic_noise.is_some());
    assert!(input.rx.viterbi_enabled);
    assert!(
        input
            .rx
            .viterbi
            .as_ref()
            .is_some_and(|viterbi| !viterbi.fec)
    );
    assert!(input.rx.dfe.is_some());
    assert_eq!(
        input
            .rx
            .dfe
            .as_ref()
            .and_then(|dfe| dfe.tap_limits.as_ref())
            .map(Vec::len),
        Some(1)
    );
    let pam4_run_path = root.join("pam4-run.yaml");
    fs::write(
        &pam4_run_path,
        projection_yaml(
            "f_max: 2.0\nmod_type: PAM-4\npn_mag: 0.001\npn_freq: 1000.0\nrn: 0.001\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]",
        ),
    )
    .unwrap();
    let pam4_report = run_legacy_sim_v1(&LegacySimRequestV1 {
        config_file: pam4_run_path,
        results: Some(root.join("pam4-run.pybert_data")),
    })
    .unwrap();
    assert!(matches!(pam4_report.input.modulation, ModulationV1::Pam4));
    assert!(pam4_report.output.arrays.contains_key("dfe_output_v"));
    let fec_path = root.join("pam4-fec.yaml");
    fs::write(
        &fec_path,
        projection_yaml(
            "f_max: 2.0\nmod_type: PAM-4\nrx_use_viterbi: true\nrx_viterbi_fec: true\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]",
        ),
    )
    .unwrap();
    let (_, fec_input) = project_legacy_config_v1(&fec_path, "portable-fec").unwrap();
    assert!(matches!(fec_input.modulation, ModulationV1::Pam4));
    assert_eq!(fec_input.timebase.data_rate.0, 10.0e9);
    assert_eq!(fec_input.timebase.sample_interval.0, 50.0e-12);
    assert_eq!(
        fec_input
            .tx
            .additive_noise
            .as_ref()
            .unwrap()
            .samples_v
            .len(),
        2000
    );
    assert!(
        fec_input
            .rx
            .viterbi
            .as_ref()
            .is_some_and(|viterbi| viterbi.fec && viterbi.noise_sigma_v.is_none())
    );
    let fec_report = run_legacy_sim_v1(&LegacySimRequestV1 {
        config_file: fec_path.clone(),
        results: Some(root.join("pam4-fec.pybert_data")),
    })
    .unwrap();
    assert!(matches!(fec_report.input.modulation, ModulationV1::Pam4));
    assert!(
        fec_report
            .output
            .metrics
            .contains_key("fec_encoded_bit_count")
    );
    for (name, value) in [("nrz", "NRZ"), ("duo", "Duo-binary")] {
        let path = root.join(format!("{name}.yaml"));
        fs::write(
            &path,
            projection_yaml(&format!("f_max: 2.0\nmod_type: {value}")),
        )
        .unwrap();
        let (_, projected) = project_legacy_config_v1(&path, name).unwrap();
        assert!(matches!(
            (name, projected.modulation),
            ("nrz", ModulationV1::Nrz) | ("duo", ModulationV1::DuoBinary)
        ));
    }
    let duo_path = root.join("duo-run.yaml");
    fs::write(
        &duo_path,
        projection_yaml(
            "f_max: 4.0\nl_ch: 0.0\nmod_type: Duo-binary\npn_mag: 0.001\npn_freq: 1000.0\nrn: 0.001\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]",
        ),
    )
    .unwrap();
    let duo_result_path = root.join("duo-run.pybert_data");
    let duo_report = run_legacy_sim_v1(&LegacySimRequestV1 {
        config_file: duo_path,
        results: Some(duo_result_path.clone()),
    })
    .expect("Duo-binary legacy jitter must use the configured decision scaler");
    assert!(matches!(
        duo_report.input.modulation,
        ModulationV1::DuoBinary
    ));
    assert!(
        duo_result_path.is_file(),
        "successful Duo-binary run publishes a result artifact"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn legacy_duobinary_jitter_uses_decision_scaler_for_crossings() {
    let root = std::env::temp_dir().join(format!("sipi-pb01-duo-scaler-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let low_path = root.join("low.yaml");
    let high_path = root.join("high.yaml");
    let common = "f_max: 4.0\nl_ch: 0.0\nmod_type: Duo-binary\nvod: 0.5\nctle_enable: false\nrn: 0.0\npn_mag: 0.0\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]\n";
    fs::write(
        &low_path,
        projection_yaml(&format!("{common}decision_scaler: 0.2\n")),
    )
    .unwrap();
    fs::write(
        &high_path,
        projection_yaml(&format!("{common}decision_scaler: 0.6\n")),
    )
    .unwrap();

    let (_, low_input) = project_legacy_config_v1(&low_path, "native-low-scaler").unwrap();
    let (_, high_input) = project_legacy_config_v1(&high_path, "native-high-scaler").unwrap();
    assert_ne!(
        low_input.tx.amplitude.0,
        low_input
            .rx
            .dfe
            .as_ref()
            .expect("legacy projection supplies a DFE")
            .decision_scaler
            .0
    );
    let low_native = simulate_native_v1(&low_input).unwrap();
    let high_native = simulate_native_v1(&high_input).unwrap();
    assert_eq!(
        low_native.arrays["jitter_chnl_tie_s"], high_native.arrays["jitter_chnl_tie_s"],
        "public native jitter must use TX amplitude, not legacy DFE scaler"
    );
    assert_eq!(
        low_native.arrays["jitter_tx_tie_s"], high_native.arrays["jitter_tx_tie_s"],
        "public native TX jitter must use TX amplitude, not legacy DFE scaler"
    );

    let low = run_legacy_sim_v1(&LegacySimRequestV1 {
        config_file: low_path,
        results: Some(root.join("low.pybert_data")),
    })
    .expect("low decision scaler Duo-binary run must complete");
    let high = run_legacy_sim_v1(&LegacySimRequestV1 {
        config_file: high_path,
        results: Some(root.join("high.pybert_data")),
    })
    .expect("high decision scaler Duo-binary run must complete");
    let low_ties = &low.output.arrays["jitter_chnl_tie_s"];
    let high_ties = &high.output.arrays["jitter_chnl_tie_s"];
    assert!(!low_ties.is_empty());
    assert!(!high_ties.is_empty());
    assert_ne!(
        low_ties, high_ties,
        "legacy Duo-binary crossing thresholds must consume decision_scaler"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn legacy_codecs_share_execution_policy_for_nrz_and_pam4() {
    let root = std::env::temp_dir().join(format!("sipi-pb01-codec-policy-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    for (name, modulation) in [("nrz", "NRZ"), ("pam4", "PAM-4")] {
        let config_path = root.join(format!("{name}.yaml"));
        fs::write(
            &config_path,
            projection_yaml(&format!(
                "f_max: 2.0\nmod_type: {modulation}\nrn: 0.0\npn_mag: 0.0\ndfe_tap_tuners:\n- !!python/tuple [true, -0.2, 0.2]\n"
            )),
        )
        .unwrap();
        for (codec_name, codec) in [
            ("dictionary", LegacyResultCodecV1::SipiDictionary),
            ("class", LegacyResultCodecV1::ClassPickle),
        ] {
            let result_path = root.join(format!("{name}-{codec_name}.pybert_data"));
            let report = run_legacy_sim_with_codec_v1(
                &LegacySimRequestV1 {
                    config_file: config_path.clone(),
                    results: Some(result_path.clone()),
                },
                codec,
            )
            .expect("both legacy codecs must use the same migrated execution policy");
            assert!(
                !report.output.arrays.is_empty(),
                "{name}/{codec_name} must publish the migrated output"
            );
            assert!(
                result_path.is_file(),
                "{name}/{codec_name} artifact missing"
            );
            assert_eq!(
                report.input.modulation,
                if modulation == "PAM-4" {
                    ModulationV1::Pam4
                } else {
                    ModulationV1::Nrz
                }
            );
        }
    }
    let _ = fs::remove_dir_all(root);
}

#[test]
fn legacy_thresh_is_projected_and_changes_native_jitter_threshold() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-thresh-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let default_path = root.join("default.yaml");
    let explicit_path = root.join("explicit.yaml");
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("fixtures")
        .join("pb-01-legacy-nrz.yaml");
    let fixture_text = fs::read_to_string(&fixture).unwrap();
    fs::write(&default_path, &fixture_text).unwrap();
    fs::write(&explicit_path, format!("{fixture_text}thresh: 7.5\n")).unwrap();
    let (default_projection, default_input) =
        project_legacy_config_v1(&default_path, "threshold-default").unwrap();
    let (explicit_projection, explicit_input) =
        project_legacy_config_v1(&explicit_path, "threshold-explicit").unwrap();
    assert_eq!(default_projection.jitter_rel_thresh, 3.0);
    assert_eq!(default_input.analysis.jitter_rel_thresh, Some(3.0));
    assert_eq!(explicit_projection.jitter_rel_thresh, 7.5);
    assert_eq!(explicit_input.analysis.jitter_rel_thresh, Some(7.5));
    let default_output = simulate_native_v1(&default_input).unwrap();
    let explicit_output = simulate_native_v1(&explicit_input).unwrap();
    assert_ne!(
        default_output.arrays["jitter_threshold"], explicit_output.arrays["jitter_threshold"],
        "legacy thresh must reach spectral jitter classification"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_parses_portable_s2p_channel_and_ctle_files() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-s2p-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let _ = write_s2p(&root, "channel.s2p");
    let _ = write_s2p(&root, "ctle.s2p");
    let config_path = root.join("s2p.yaml");
    fs::write(
        &config_path,
        projection_yaml(
            "eye_bits: 1000\nf_max: 1.0\nf_step: 100.0\nimpulse_length: 0.125\nuse_ch_file: true\nch_file: channel.s2p\nuse_ctle_file: true\nctle_file: ctle.s2p",
        ),
    )
    .unwrap();
    let (_, input) = project_legacy_config_v1(&config_path, "portable-s2p").unwrap();
    assert!(matches!(
        &input.channel,
        ChannelInputV1::ImpulseResponse(response) if response.impulse_response_volts_per_second.len() == 2
    ));
    assert!(
        input
            .rx
            .ctle
            .as_ref()
            .and_then(|ctle| ctle.impulse_response_v_per_v.as_ref())
            .is_some_and(|impulse| !impulse.is_empty())
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_keeps_ami_external_boundary_fail_closed() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-external-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config_path = root.join("ami.yaml");
    fs::write(
        &config_path,
        projection_yaml("tx_use_ami: true\ntx_ami_file: tx.ami"),
    )
    .unwrap();
    assert!(matches!(
        project_legacy_config_v1(&config_path, "external"),
        Err(LegacyRuntimeError::Unsupported(message)) if message.contains("tx_use_ami")
    ));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn projection_decodes_bounded_pybert_cfg_pickle_state_without_python() {
    let root = std::env::temp_dir().join(format!("sipi-pb03-pickle-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let config_path = root.join("portable.pybert_cfg");
    let pickle = [
        0x80, 0x03, 0x63, 0x70, 0x79, 0x62, 0x65, 0x72, 0x74, 0x2e, 0x63, 0x6f, 0x6e, 0x66, 0x69,
        0x67, 0x75, 0x72, 0x61, 0x74, 0x69, 0x6f, 0x6e, 0x0a, 0x50, 0x79, 0x42, 0x65, 0x72, 0x74,
        0x43, 0x66, 0x67, 0x0a, 0x71, 0x00, 0x29, 0x81, 0x71, 0x01, 0x7d, 0x71, 0x02, 0x28, 0x58,
        0x08, 0x00, 0x00, 0x00, 0x62, 0x69, 0x74, 0x5f, 0x72, 0x61, 0x74, 0x65, 0x71, 0x03, 0x47,
        0x40, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x58, 0x05, 0x00, 0x00, 0x00, 0x6e, 0x62,
        0x69, 0x74, 0x73, 0x71, 0x04, 0x4d, 0xe8, 0x03, 0x58, 0x07, 0x00, 0x00, 0x00, 0x70, 0x61,
        0x74, 0x74, 0x65, 0x72, 0x6e, 0x71, 0x05, 0x58, 0x06, 0x00, 0x00, 0x00, 0x50, 0x52, 0x42,
        0x53, 0x2d, 0x37, 0x71, 0x06, 0x58, 0x04, 0x00, 0x00, 0x00, 0x73, 0x65, 0x65, 0x64, 0x71,
        0x07, 0x4b, 0x11, 0x58, 0x05, 0x00, 0x00, 0x00, 0x6e, 0x73, 0x70, 0x75, 0x69, 0x71, 0x08,
        0x4b, 0x02, 0x75, 0x62, 0x2e,
    ];
    fs::write(&config_path, pickle).unwrap();
    let (_, input) = project_legacy_config_v1(&config_path, "pickle-config").unwrap();
    assert_eq!(input.timebase.nbits, 1_000);
    assert!(matches!(input.modulation, ModulationV1::Nrz));
    assert_eq!(input.tx.ffe.weights.len(), 7);
    let _ = fs::remove_dir_all(root);
}
