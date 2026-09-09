use std::process::{Command, Output};

use serde_json::Value;

fn cli(arguments: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_sipi"))
        .args(arguments)
        .output()
        .unwrap()
}

fn result(output: &Output) -> Value {
    let value: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(value["schema"], "sipi.cli.response.v1");
    value["result"].clone()
}

#[cfg(not(feature = "pybert-direct-integration"))]
#[test]
fn default_build_does_not_advertise_or_execute_the_quarantined_candidate() {
    let commands = cli(&["commands", "--json"]);
    assert!(commands.status.success());
    assert!(!String::from_utf8_lossy(&commands.stdout).contains("channel.simulate"));
    let output = cli(&[
        "channel",
        "simulate",
        "missing.json",
        "--output-dir",
        "unused",
    ]);
    assert_eq!(output.status.code(), Some(4));
    assert!(result(&output).is_null());
}

#[cfg(feature = "pybert-direct-integration")]
mod native {
    use super::*;
    use sha2::{Digest, Sha256};
    use sipi_pybert_direct::run_sim_native_json;
    use std::{
        fs,
        path::PathBuf,
        sync::atomic::{AtomicU64, Ordering},
    };

    const TEMPLATE: &[u8] = include_bytes!("../../../examples/channel-native/metallic-line.json");
    static NEXT: AtomicU64 = AtomicU64::new(0);

    struct Temp(PathBuf);
    impl Temp {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "sipi-native-channel-{}-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            fs::create_dir(&root).unwrap();
            Self(root)
        }
        fn run(&self, bytes: &[u8], name: &str) -> Output {
            let request = self.0.join(format!("{name}.json"));
            fs::write(&request, bytes).unwrap();
            cli(&[
                "channel",
                "simulate",
                request.to_str().unwrap(),
                "--output-dir",
                self.0.join(name).to_str().unwrap(),
            ])
        }
    }
    impl Drop for Temp {
        fn drop(&mut self) {
            assert!(self.0.starts_with(std::env::temp_dir()));
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn input() -> Value {
        serde_json::from_slice(TEMPLATE).unwrap()
    }

    fn csv(path: PathBuf) -> (Vec<String>, Vec<Vec<f64>>) {
        let text = fs::read_to_string(path).unwrap();
        let mut lines = text.lines();
        let header = lines
            .next()
            .unwrap()
            .split(',')
            .map(str::to_string)
            .collect();
        let rows = lines
            .map(|line| {
                line.split(',')
                    .map(|number| number.parse::<f64>().unwrap())
                    .collect()
            })
            .collect();
        (header, rows)
    }

    #[test]
    fn init_help_and_discovery_are_self_contained_and_do_not_overwrite() {
        let root = Temp::new();
        let request = root.0.join("request with spaces.json");
        let initialized = cli(&["channel", "init", request.to_str().unwrap()]);
        assert!(initialized.status.success(), "{initialized:?}");
        assert!(initialized.stderr.is_empty());
        assert_eq!(fs::read(&request).unwrap(), TEMPLATE);
        assert!(
            !cli(&["channel", "init", request.to_str().unwrap()])
                .status
                .success()
        );
        assert_eq!(fs::read(&request).unwrap(), TEMPLATE);
        let help = cli(&["channel", "help"]);
        assert!(help.status.success());
        assert_eq!(result(&help)["backend"], "in_process_sipi_pybert_direct");
        for command in ["commands", "protocols"] {
            let output = cli(&[command, "--json"]);
            assert!(output.status.success(), "{output:?}");
            assert!(String::from_utf8_lossy(&output.stdout).contains("channel.simulate"));
        }
    }

    #[test]
    fn real_metallic_simulation_matches_owning_workflow_and_exports_every_csv_sample() {
        let root = Temp::new();
        let actual = root.run(TEMPLATE, "metallic");
        assert!(actual.status.success(), "{actual:?}");
        assert!(actual.stderr.is_empty());
        let receipt = result(&actual);
        assert_eq!(receipt["acceptance"], false);
        assert_eq!(receipt["waveform_samples"], 8192);
        let out = root.0.join("metallic");
        assert_eq!(
            serde_json::from_slice::<Value>(&fs::read(out.join("receipt.json")).unwrap()).unwrap(),
            receipt
        );
        let expected = run_sim_native_json(
            TEMPLATE,
            &root.0.join("metallic.json"),
            &root.0.join("owner"),
        )
        .unwrap();
        for artifact in ["meta.json", "arrays.npz"] {
            assert_eq!(
                fs::read(out.join(artifact)).unwrap(),
                fs::read(root.0.join("owner").join(artifact)).unwrap(),
                "{artifact}"
            );
        }
        let (header, rows) = csv(out.join("waveforms.csv"));
        assert_eq!(rows.len(), 8192);
        for (column, name) in header.iter().enumerate() {
            let native = &expected.output.arrays[name];
            for (index, row) in rows.iter().enumerate() {
                assert_eq!(
                    row[column].to_bits(),
                    native[index].to_bits(),
                    "{name}[{index}]"
                );
            }
        }
        let (_, rows) = csv(out.join("channel-impulse.csv"));
        let kernel = &expected.output.arrays["channel_impulse_v_per_v"];
        assert_eq!(rows.len(), kernel.len());
        for (index, row) in rows.iter().enumerate() {
            assert_eq!(
                row[0],
                index as f64 * expected.input.timebase.sample_interval.0
            );
            assert_eq!(row[1].to_bits(), kernel[index].to_bits());
        }
        for (name, identity) in receipt["artifacts"].as_object().unwrap() {
            let bytes = fs::read(out.join(name)).unwrap();
            assert_eq!(identity["byte_length"], bytes.len());
            assert_eq!(identity["sha256"], format!("{:x}", Sha256::digest(bytes)));
        }
        let executable = fs::read(env!("CARGO_BIN_EXE_sipi")).unwrap();
        assert_eq!(
            receipt["executable"]["sha256"],
            format!("{:x}", Sha256::digest(executable))
        );
        let html = fs::read_to_string(out.join("report.html")).unwrap();
        assert_eq!(html.matches("<polyline ").count(), 5);
        assert!(!html.contains("<script"));
        assert!(html.contains("Samples 0..511 of 8192"));
        assert!(
            expected.output.arrays["channel_output_v"]
                .iter()
                .any(|value| value.abs() > 0.01)
        );
    }

    #[test]
    fn explicit_bits_use_the_owning_serialized_field_and_reject_ambiguous_aliases() {
        let root = Temp::new();
        let mut request = input();
        request["timebase"]["nbits"] = 8.into();
        request["pattern"] = serde_json::json!({
            "kind": "explicit_bits", "bit_count": 8, "bits": [0, 1, 1, 0, 1, 0, 0, 1]
        });
        let bytes = serde_json::to_vec(&request).unwrap();
        let parsed: sipi_pybert_direct::SimulationInputV1 = serde_json::from_slice(&bytes).unwrap();
        let serialized = serde_json::to_vec(&parsed).unwrap();
        assert!(sipi_pybert_direct::strict_simulation_input_json(&serialized).is_ok());
        let actual = root.run(&bytes, "explicit");
        assert!(actual.status.success(), "{actual:?}");
        let (_, rows) = csv(root.0.join("explicit/waveforms.csv"));
        assert_eq!(rows.len(), 128);
        for (index, row) in rows.iter().enumerate() {
            let bit = [0, 1, 1, 0, 1, 0, 0, 1][index / 16];
            assert_eq!(row[1], f64::from(2 * bit - 1) * 0.5);
        }
        request["pattern"]["bitCount"] = 8.into();
        let duplicate_alias = root.run(&serde_json::to_vec(&request).unwrap(), "alias");
        assert_eq!(duplicate_alias.status.code(), Some(2));
        request["pattern"]
            .as_object_mut()
            .unwrap()
            .remove("bit_count");
        let camel_only = root.run(&serde_json::to_vec(&request).unwrap(), "camel");
        assert_eq!(camel_only.status.code(), Some(2));
    }

    #[test]
    fn equalization_and_impulse_inputs_are_not_replaced_with_a_channel_only_toy() {
        let root = Temp::new();
        let mut request = input();
        request["timebase"]["nbits"] = 32.into();
        request["channel"] = serde_json::json!({"kind": "impulse_response", "value": {
            "sampleInterval": 1.953125e-12, "impulseResponseVoltsPerSecond": [512e9, 128e9], "sourceImpedance": 50, "loadImpedance": 50
        }});
        request["tx"]["ffe"] =
            serde_json::json!({"enabled": true, "weights": [0.8, -0.2], "cursorPosition": 0});
        request["rx"]["ffe"] =
            serde_json::json!({"enabled": true, "weights": [1.0, -0.15], "cursorPosition": 0});
        let bytes = serde_json::to_vec(&request).unwrap();
        let output = root.run(&bytes, "eq");
        assert!(output.status.success(), "{output:?}");
        let expected =
            run_sim_native_json(&bytes, &root.0.join("eq.json"), &root.0.join("owner")).unwrap();
        assert_eq!(
            fs::read(root.0.join("eq/arrays.npz")).unwrap(),
            fs::read(expected.arrays_path).unwrap()
        );
        assert_ne!(
            expected.output.arrays["rx_input_v"],
            expected.output.arrays["rx_output_v"]
        );
    }

    #[test]
    fn bad_requests_fail_without_a_success_receipt_or_old_run_damage() {
        let root = Temp::new();
        let mut unknown = input();
        unknown["silentFallback"] = true.into();
        let mut invalid_time = input();
        invalid_time["timebase"]["sampleInterval"] = 0.into();
        let mut unsupported = input();
        unsupported["externalModels"] = serde_json::json!([{"kind":"ami", "capability":"getwave"}]);
        let mut limited = input();
        limited["limits"]["maxTotalSamples"] = 1.into();
        for (name, bytes, code) in [
            ("malformed", b"{".to_vec(), 2),
            ("unknown", serde_json::to_vec(&unknown).unwrap(), 2),
            ("time", serde_json::to_vec(&invalid_time).unwrap(), 2),
            ("external", serde_json::to_vec(&unsupported).unwrap(), 4),
            ("limit", serde_json::to_vec(&limited).unwrap(), 5),
            (
                "duplicate",
                String::from_utf8(TEMPLATE.to_vec())
                    .unwrap()
                    .replacen("\"runId\":", "\"runId\":\"first\",\"runId\":", 1)
                    .into_bytes(),
                2,
            ),
        ] {
            let output = root.run(&bytes, name);
            assert_eq!(output.status.code(), Some(code), "{name}: {output:?}");
            assert!(!root.0.join(name).join("receipt.json").exists());
            assert!(
                !String::from_utf8_lossy(&output.stderr)
                    .contains(&root.0.to_string_lossy().to_string())
            );
        }
        let out = root.0.join("existing");
        fs::create_dir(&out).unwrap();
        fs::write(out.join("meta.json"), "retain prior run").unwrap();
        assert!(!root.run(TEMPLATE, "existing").status.success());
        assert_eq!(
            fs::read_to_string(out.join("meta.json")).unwrap(),
            "retain prior run"
        );
        assert!(!out.join("receipt.json").exists());
    }

    #[test]
    fn usage_is_strict_and_report_escapes_caller_text() {
        for args in [
            vec!["channel", "help", "extra"],
            vec!["channel", "init"],
            vec![
                "channel",
                "simulate",
                "x",
                "--output-dir",
                "y",
                "--output-dir",
                "z",
            ],
        ] {
            assert_eq!(cli(&args).status.code(), Some(64));
        }
        let root = Temp::new();
        let mut request = input();
        request["runId"] = "<script>alert('x')</script> & evidence".into();
        let output = root.run(&serde_json::to_vec(&request).unwrap(), "escaped");
        assert!(output.status.success(), "{output:?}");
        let html = fs::read_to_string(root.0.join("escaped/report.html")).unwrap();
        assert!(!html.contains("<script>"));
        assert!(html.contains("&lt;script&gt;"));
    }

    #[test]
    fn request_size_is_bounded_before_simulation() {
        let root = Temp::new();
        let output = root.run(&vec![b' '; 16 * 1024 * 1024 + 1], "oversize");
        assert_eq!(output.status.code(), Some(2));
        assert!(!root.0.join("oversize").exists());
    }

    #[test]
    fn copied_executable_simulates_outside_checkout_without_build_or_python_tools() {
        let root = Temp::new();
        let executable = root.0.join(if cfg!(windows) { "sipi.exe" } else { "sipi" });
        fs::copy(env!("CARGO_BIN_EXE_sipi"), &executable).unwrap();
        let path = if cfg!(windows) {
            format!("{}\\System32", std::env::var("SystemRoot").unwrap())
        } else {
            String::new()
        };
        for arguments in [
            vec!["channel", "init", "request.json"],
            vec!["channel", "simulate", "request.json", "--output-dir", "run"],
        ] {
            let output = Command::new(&executable)
                .args(arguments)
                .current_dir(&root.0)
                .env("PATH", &path)
                .env_remove("PYTHONPATH")
                .env_remove("PYTHONHOME")
                .output()
                .unwrap();
            assert!(output.status.success(), "{output:?}");
            assert!(output.stderr.is_empty());
        }
        let receipt: Value =
            serde_json::from_slice(&fs::read(root.0.join("run/receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["waveform_samples"], 8192);
        assert_eq!(receipt["backend"], "in_process_sipi_pybert_direct");
    }
}
