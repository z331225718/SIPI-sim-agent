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
    const TEMPLATE_TOUCHSTONE: &[u8] =
        include_bytes!("../../../examples/channel-native/touchstone-network.json");
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
        fn run_physical(&self, bytes: &[u8], name: &str) -> Output {
            let request = self.0.join(format!("{name}.json"));
            fs::write(&request, bytes).unwrap();
            cli(&[
                "channel",
                "simulate",
                request.to_str().unwrap(),
                "--output-dir",
                self.0.join(name).to_str().unwrap(),
                "--channel-policy",
                "physical-voltage-v1",
            ])
        }
        fn run_touchstone(&self, bytes: &[u8], name: &str) -> Output {
            let request = self.0.join(format!("{name}.json"));
            fs::write(&request, bytes).unwrap();
            cli(&[
                "channel",
                "simulate",
                request.to_str().unwrap(),
                "--output-dir",
                self.0.join(name).to_str().unwrap(),
                "--channel-policy",
                "touchstone-network-v1",
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
        assert!(html.contains("script-src 'self'"));
        assert!(!html.contains("script-src 'unsafe-inline'"));
        assert!(html.contains("<script src=\"channel-report.js\" defer></script>"));
        assert!(html.contains("Samples 0..511 of 8192"));
        let data = html
            .split_once("<script type=\"application/json\" id=\"channel-data\">")
            .unwrap()
            .1
            .split_once("</script>")
            .unwrap()
            .0;
        let data_json = data;
        let data: Value = serde_json::from_str(data_json).unwrap();
        for (key, names) in [
            (
                "waveform",
                vec![
                    "tx_waveform_v",
                    "channel_output_v",
                    "rx_input_v",
                    "rx_output_v",
                ],
            ),
            ("impulse", vec!["channel_impulse_v_per_v"]),
        ] {
            let expected_columns = names
                .iter()
                .map(|name| &expected.output.arrays[*name])
                .collect::<Vec<_>>();
            assert!(data_json.contains(&format!(
                "\"columns\":{}",
                serde_json::to_string(&expected_columns).unwrap()
            )));
            for (column, name) in names.into_iter().enumerate() {
                let actual = data[key]["columns"][column].as_array().unwrap();
                let expected_values = &expected.output.arrays[name];
                assert_eq!(actual.len(), expected_values.len());
            }
        }
        assert_eq!(data["waveform"]["time"].as_array().unwrap().len(), 8192);
        assert_eq!(
            receipt["report_data_policy"],
            "all_waveform_and_impulse_samples_embedded; original_f64; at_most_4096_contiguous_samples_per_view; no_decimation"
        );
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
            vec![
                "channel",
                "simulate",
                "request.json",
                "--output-dir",
                "physical-run",
                "--channel-policy",
                "physical-voltage-v1",
            ],
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
        let physical: Value =
            serde_json::from_slice(&fs::read(root.0.join("physical-run/receipt.json")).unwrap())
                .unwrap();
        assert_eq!(physical["channel_policy"], "physical-voltage-v1");
        assert_eq!(physical["waveform_samples"], 8192);
    }

    #[test]
    fn physical_voltage_keeps_absolute_delay_and_exports_the_owning_arrays() {
        let root = Temp::new();
        let mut request = input();
        let line = request["channel"]["value"].as_object_mut().unwrap();
        for key in [
            "skinEffectResistanceOhmPerM",
            "dcResistanceOhmPerM",
            "lossTangent",
            "sourceCapacitanceF",
            "loadCapacitanceF",
        ] {
            line.insert(key.into(), 0.0.into());
        }
        line.insert("propagationVelocityMPerS".into(), 200e6.into());
        line.insert("frequencyMaxHz".into(), 256e9.into());
        line.insert("applyRaisedCosineWindow".into(), false.into());
        let bytes = serde_json::to_vec(&request).unwrap();
        let actual = root.run_physical(&bytes, "delay");
        assert!(actual.status.success(), "{actual:?}");
        let receipt = result(&actual);
        assert_eq!(receipt["channel_policy"], "physical-voltage-v1");
        assert_eq!(receipt["channel_impulse_samples"], 512);
        let owner = sipi_pybert_direct::run_channel_physical_json(
            &bytes,
            &root.0.join("delay.json"),
            &root.0.join("owner-physical"),
        )
        .unwrap();
        for name in ["meta.json", "arrays.npz"] {
            assert_eq!(
                fs::read(root.0.join("delay").join(name)).unwrap(),
                fs::read(root.0.join("owner-physical").join(name)).unwrap()
            );
        }
        assert_eq!(owner.metadata["schema"], "sipi.channel.physical-result.v1");
        assert_eq!(
            owner.diagnostics["physical_channel"]["discarded_prefix_samples"],
            0
        );
        assert_eq!(
            owner.diagnostics["physical_channel"]["kernel_peak_time_s"],
            250e-12
        );
        let arrays = &owner.output.arrays;
        for (i, &y) in arrays["channel_output_v"].iter().enumerate() {
            let expected = if i < 128 {
                0.0
            } else {
                arrays["tx_waveform_v"][i - 128]
            };
            assert!(
                (y - expected).abs() < 1e-11,
                "sample {i}: {y} != {expected}"
            );
        }
        let (header, rows) = csv(root.0.join("delay/frequency-response.csv"));
        assert_eq!(rows.len(), 2049);
        let requested_step = request["channel"]["value"]["frequencyStepHz"]
            .as_f64()
            .unwrap();
        assert_eq!(
            owner.diagnostics["physical_channel"]["frequency_step_hz"]
                .as_f64()
                .unwrap()
                .to_bits(),
            requested_step.to_bits()
        );
        for (i, row) in rows.iter().enumerate() {
            assert_eq!(row[0].to_bits(), (i as f64 * requested_step).to_bits());
        }
        for (col, name) in header.iter().enumerate() {
            let key = if name == "frequency_hz" {
                "physical_channel_frequency_hz"
            } else {
                name
            };
            for (i, row) in rows.iter().enumerate() {
                assert_eq!(row[col].to_bits(), arrays[key][i].to_bits());
            }
        }
        for (name, identity) in receipt["artifacts"].as_object().unwrap() {
            let content = fs::read(root.0.join("delay").join(name)).unwrap();
            assert_eq!(identity["sha256"], format!("{:x}", Sha256::digest(content)));
        }
        request["tx"]["ffe"] =
            serde_json::json!({"enabled":true,"weights":[0.8,0.2],"cursorPosition":0});
        request["rx"]["ffe"] =
            serde_json::json!({"enabled":true,"weights":[1.0,-0.1],"cursorPosition":0});
        let eq = root.run_physical(&serde_json::to_vec(&request).unwrap(), "with-eq");
        assert!(eq.status.success(), "{eq:?}");
        let (_, waves) = csv(root.0.join("with-eq/waveforms.csv"));
        assert!(waves.iter().any(|row| (row[2] - row[3]).abs() > 0.01));
        assert!(waves.iter().any(|row| (row[3] - row[4]).abs() > 0.01));
    }

    #[test]
    fn physical_native_grid_uses_the_actual_nrz_duobinary_or_pam4_symbol_count() {
        let root = Temp::new();
        for (modulation, samples) in [("nrz", 2048), ("duo_binary", 2048), ("pam4", 1024)] {
            let mut request = input();
            request["timebase"]["nbits"] = 128.into();
            request["modulation"] = modulation.into();
            let line = request["channel"]["value"].as_object_mut().unwrap();
            for key in ["frequencyStepHz", "frequencyMaxHz", "impulseLength"] {
                line.insert(key.into(), Value::Null);
            }
            for key in [
                "lengthM",
                "skinEffectResistanceOhmPerM",
                "dcResistanceOhmPerM",
                "lossTangent",
                "sourceCapacitanceF",
                "loadCapacitanceF",
            ] {
                line.insert(key.into(), 0.0.into());
            }
            line.insert("applyRaisedCosineWindow".into(), false.into());
            let output = root.run_physical(&serde_json::to_vec(&request).unwrap(), modulation);
            assert!(output.status.success(), "{modulation}: {output:?}");
            let receipt = result(&output);
            assert_eq!(receipt["waveform_samples"], samples);
            assert_eq!(receipt["channel_impulse_samples"], samples);
            let (_, waveform) = csv(root.0.join(modulation).join("waveforms.csv"));
            for row in waveform {
                assert!((row[1] - row[2]).abs() < 1e-11);
            }
            let (_, impulse) = csv(root.0.join(modulation).join("channel-impulse.csv"));
            assert!((impulse[0][1] - 1.0).abs() < 1e-12);
            assert!(impulse[1..].iter().all(|row| row[1].abs() < 1e-12));
        }
    }

    #[test]
    fn physical_policy_rejects_ambiguous_grids_memory_and_nyquist_without_a_receipt() {
        let root = Temp::new();
        for (key, value) in [
            ("frequencyMaxHz", 64001e6),
            ("impulseLength", 16e-9),
            ("lossTangent", -0.01),
        ] {
            let mut request = input();
            request["channel"]["value"][key] = value.into();
            let output = root.run_physical(&serde_json::to_vec(&request).unwrap(), key);
            assert_eq!(output.status.code(), Some(2), "{output:?}");
            assert!(!root.0.join(key).join("receipt.json").exists());
        }
        let mut request = input();
        request["limits"]["maxMemoryBytes"] = 1000.into();
        let output = root.run_physical(&serde_json::to_vec(&request).unwrap(), "memory");
        assert_eq!(output.status.code(), Some(5), "{output:?}");
        request = input();
        request["channel"]["value"]["frequencyMaxHz"] = 256e9.into();
        request["channel"]["value"]["applyRaisedCosineWindow"] = false.into();
        let output = root.run_physical(&serde_json::to_vec(&request).unwrap(), "nyquist");
        assert_eq!(output.status.code(), Some(2), "{output:?}");
        assert!(!root.0.join("nyquist/receipt.json").exists());
        assert_eq!(
            cli(&[
                "channel",
                "simulate",
                "missing.json",
                "--output-dir",
                "unused",
                "--channel-policy",
                "unknown"
            ])
            .status
            .code(),
            Some(64)
        );
    }
    #[test]
    fn channel_init_supports_touchstone_network_template() {
        let root = Temp::new();
        let request = root.0.join("custom-touchstone.json");
        let output = cli(&[
            "channel",
            "init",
            request.to_str().unwrap(),
            "--template",
            "touchstone-network",
        ]);
        assert!(output.status.success(), "{output:?}");
        let res = result(&output);
        assert_eq!(res["template"], "touchstone-network-prbs9");
        assert_eq!(res["acceptance"], false);
        let bytes = fs::read(&request).unwrap();
        assert_eq!(bytes, TEMPLATE_TOUCHSTONE);
    }

    #[test]
    fn touchstone_network_policy_runs_analytic_cascade_and_generates_all_artifacts() {
        let root = Temp::new();
        let output = root.run_touchstone(TEMPLATE_TOUCHSTONE, "cascade_run");
        assert!(output.status.success(), "{output:?}");
        let res = result(&output);
        assert_eq!(res["status"], "complete");
        assert_eq!(res["channel_policy"], "touchstone-network-v1");
        assert_eq!(res["acceptance"], false);

        let dir = root.0.join("cascade_run");
        for name in [
            "request.json",
            "meta.json",
            "arrays.npz",
            "waveforms.csv",
            "channel-impulse.csv",
            "frequency-response.csv",
            "cascade-nodes.csv",
            "report.html",
            "channel-report.js",
            "receipt.json",
        ] {
            assert!(dir.join(name).is_file(), "missing artifact: {name}");
        }

        let (freq_headers, freq_rows) = csv(dir.join("frequency-response.csv"));
        assert_eq!(freq_headers[0], "frequency_hz");
        assert!(freq_headers.contains(&"touchstone_s21_re".to_string()));
        assert!(freq_headers.contains(&"touchstone_loaded_h_re".to_string()));
        assert_eq!(freq_rows.len(), 513); // 0 to 64 GHz at 125 MHz step
        assert_eq!(freq_rows[0].len(), freq_headers.len());

        let (node_headers, _) = csv(dir.join("cascade-nodes.csv"));
        assert_eq!(node_headers[0], "frequency_hz");
        assert!(node_headers.iter().any(|h| h.contains("tx_fixture")));
        assert!(node_headers.iter().any(|h| h.contains("rx_fixture")));

        let meta: Value = serde_json::from_slice(&fs::read(dir.join("meta.json")).unwrap()).unwrap();
        assert_eq!(meta["schema"], "sipi.channel.touchstone-result.v1");
        assert_eq!(meta["diagnostics"]["touchstone_network"]["acceptance"], false);
        assert_eq!(meta["diagnostics"]["touchstone_network"]["stage_count"], 3);
        assert_eq!(
            meta["diagnostics"]["touchstone_network"]["frequency_grid_coverage"]["has_dc"],
            true
        );
        assert_eq!(
            meta["diagnostics"]["touchstone_network"]["passivity"]["passes_bound"],
            true
        );
        assert_eq!(
            meta["diagnostics"]["touchstone_network"]["reciprocity"]["passes_bound"],
            true
        );
    }

    #[test]
    fn touchstone_network_policy_runs_direct_s2p_file_and_s4p_file() {
        let root = Temp::new();
        let s2p_path = root.0.join("line.s2p");
        let s2p_content = "# GHz S RI R 50\n\
                           0.0  0.0 0.0  1.0 0.0  1.0 0.0  0.0 0.0\n\
                           1.0  0.0 0.0  0.9 -0.1 0.9 -0.1 0.0 0.0\n\
                           2.0  0.0 0.0  0.8 -0.2 0.8 -0.2 0.0 0.0\n";
        fs::write(&s2p_path, s2p_content).unwrap();

        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();
        req["channel"]["value"] = serde_json::json!({
            "filePath": "line.s2p",
            "referenceImpedance": 50.0,
            "sourceImpedance": 50.0,
            "loadImpedance": 50.0,
            "applyRaisedCosineWindow": false
        });

        let output = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "s2p_run");
        assert!(output.status.success(), "{output:?}");
        let dir = root.0.join("s2p_run");
        assert!(dir.join("receipt.json").is_file());
        assert!(dir.join("frequency-response.csv").is_file());
        let meta: Value = serde_json::from_slice(&fs::read(dir.join("meta.json")).unwrap()).unwrap();
        assert_eq!(meta["diagnostics"]["touchstone_network"]["stage_count"], 1);

        // Now test 4-port S4P file with differential port mapping
        let s4p_path = root.0.join("diff_channel.s4p");
        let s4p_content = "# GHz S RI R 50\n\
0.0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n\
1.0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n\
2.0 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02 0.05 -0.02\n";
        fs::write(&s4p_path, s4p_content).unwrap();

        req["channel"]["value"] = serde_json::json!({
            "filePath": "diff_channel.s4p",
            "portMap": "tx_plus_rx_plus_tx_minus_rx_minus",
            "referenceImpedance": 50.0,
            "sourceImpedance": 50.0,
            "loadImpedance": 50.0,
            "applyRaisedCosineWindow": false
        });

        let output4 = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "s4p_run");
        assert!(output4.status.success(), "{output4:?}");
        let dir4 = root.0.join("s4p_run");
        assert!(dir4.join("receipt.json").is_file());
        assert!(dir4.join("frequency-response.csv").is_file());
    }

    #[test]
    fn touchstone_network_runs_with_b4_eq_and_b5_dfe_cdr() {
        let root = Temp::new();
        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();

        // Enable B4 TX FFE (3 taps: precursor, cursor, postcursor)
        req["tx"]["ffe"] = serde_json::json!({
            "enabled": true,
            "weights": [-0.1, 0.8, -0.1],
            "cursorPosition": 1
        });

        // Enable B4 RX CTLE (8 GHz zero, 16 GHz pole, 6 dB boost)
        req["rx"]["nativeCtleEnabled"] = true.into();
        req["rx"]["ctle"] = serde_json::json!({
            "bandwidth": 16e9,
            "peakFrequency": 8e9,
            "peakMagnitudeDb": 6.0,
            "frequencyStepHz": 125e6,
            "frequencyMaxHz": 64e9
        });

        // Enable B4 RX FFE
        req["rx"]["ffe"] = serde_json::json!({
            "enabled": true,
            "weights": [0.0, 1.0, 0.0],
            "cursorPosition": 1
        });

        // Enable B5 DFE and CDR (4 taps, adaptive gain)
        req["rx"]["dfeTaps"] = 4.into();
        req["rx"]["dfe"] = serde_json::json!({
            "gain": 0.1,
            "decisionScaler": 0.5,
            "deltaT": 1e-13,
            "alpha": 0.01,
            "bandwidth": 32e9,
            "ideal": false,
            "useAgc": false,
            "nLockAve": 10,
            "relLockTol": 0.1,
            "lockSustain": 5,
            "nAve": 10,
            "agcNAve": 10
        });

        let output = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "b4_b5_run");
        assert!(output.status.success(), "{output:?}");
        let dir = root.0.join("b4_b5_run");

        for name in [
            "request.json",
            "meta.json",
            "arrays.npz",
            "waveforms.csv",
            "channel-impulse.csv",
            "frequency-response.csv",
            "cascade-nodes.csv",
            "report.html",
            "channel-report.js",
            "receipt.json",
        ] {
            assert!(dir.join(name).is_file(), "missing artifact: {name}");
        }

        let (headers, rows) = csv(dir.join("waveforms.csv"));
        assert_eq!(headers[0], "time_s");
        assert!(headers.contains(&"tx_waveform_v".to_string()));
        assert!(headers.contains(&"channel_output_v".to_string()));
        assert!(headers.contains(&"rx_input_v".to_string()));
        assert!(headers.contains(&"rx_output_v".to_string()));
        assert_eq!(rows.len(), 8192); // 512 bits * 16 samples/UI

        let receipt: Value = serde_json::from_slice(&fs::read(dir.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["status"], "complete");
        assert_eq!(receipt["channel_policy"], "touchstone-network-v1");
        assert_eq!(receipt["acceptance"], false);
    }

    #[test]
    fn touchstone_network_runs_b6_statistical_eye_jitter_and_bathtub_with_full_csvs() {
        let root = Temp::new();
        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();

        // 1024 bits allows 2 full PRBS9 periods for jitter decomposition
        req["timebase"]["nbits"] = 1024.into();
        req["analysis"]["includeJitter"] = true.into();
        req["analysis"]["includeBathtub"] = true.into();
        req["analysis"]["statisticalEye"] = serde_json::json!({
            "targetBer": 1e-12,
            "timePoints": 64,
            "voltageResolution": 1e-3,
            "contourBerLevels": [1e-3, 1e-6, 1e-9, 1e-12],
            "postReceiverOutput": false,
            "maxDistributionStates": 200000
        });

        let output = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "b6_eye_run");
        assert!(output.status.success(), "{output:?}");
        let dir = root.0.join("b6_eye_run");

        for name in [
            "request.json",
            "meta.json",
            "arrays.npz",
            "waveforms.csv",
            "channel-impulse.csv",
            "frequency-response.csv",
            "cascade-nodes.csv",
            "eye-metrics.csv",
            "bathtub.csv",
            "eye-contours.csv",
            "report.html",
            "channel-report.js",
            "receipt.json",
        ] {
            assert!(dir.join(name).is_file(), "missing artifact: {name}");
        }

        // Verify eye-metrics.csv content
        let eye_text = fs::read_to_string(dir.join("eye-metrics.csv")).unwrap();
        assert!(eye_text.contains("eye_height_v"));
        assert!(eye_text.contains("eye_width_ps"));
        assert!(eye_text.contains("jitter_chnl_isi_s"));
        assert!(eye_text.contains("jitter_chnl_dual_dirac_random_s"));

        // Verify bathtub.csv content
        let (bathtub_headers, bathtub_rows) = csv(dir.join("bathtub.csv"));
        assert_eq!(bathtub_headers, vec!["time_s", "time_ui", "bathtub_ber"]);
        assert!(!bathtub_rows.is_empty());
        assert!(bathtub_rows.iter().all(|r| r.len() == 3));

        // Verify eye-contours.csv content
        let (contour_headers, contour_rows) = csv(dir.join("eye-contours.csv"));
        assert_eq!(contour_headers, vec!["contour_index", "x_ui", "y_v"]);
        assert!(!contour_rows.is_empty());

        // Verify report.html has eye navigation, summary values, and bathtub section
        let html = fs::read_to_string(dir.join("report.html")).unwrap();
        assert!(html.contains("Eye metrics CSV"));
        assert!(html.contains("Bathtub CSV"));
        assert!(html.contains("Eye contours CSV"));
        assert!(html.contains("Eye height"));
        assert!(html.contains("Eye width"));
        assert!(html.contains("data-view=\"bathtub\""));
        assert!(html.contains("BER Bathtub curve"));

        // Verify receipt
        let receipt: Value = serde_json::from_slice(&fs::read(dir.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["status"], "complete");
        assert_eq!(receipt["channel_policy"], "touchstone-network-v1");
        assert!(receipt["artifacts"]["eye-metrics.csv"].is_object());
        assert!(receipt["artifacts"]["bathtub.csv"].is_object());
        assert!(receipt["artifacts"]["eye-contours.csv"].is_object());
    }

    #[test]
    fn touchstone_network_runs_b5_training_window_and_exports_adaptation_and_events() {
        let root = Temp::new();
        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();

        // Enable B5 DFE with preloaded state and training window (10 to 200 UI)
        req["rx"]["dfeTaps"] = 4.into();
        req["rx"]["dfe"] = serde_json::json!({
            "gain": 0.05,
            "decisionScaler": 0.5,
            "deltaT": 1e-13,
            "alpha": 0.01,
            "bandwidth": 32e9,
            "ideal": false,
            "useAgc": false,
            "nLockAve": 10,
            "relLockTol": 0.1,
            "lockSustain": 5,
            "nAve": 5,
            "agcNAve": 10,
            "initialWeights": [0.05, -0.02, 0.01, -0.005],
            "initialValues": [1.0, -1.0, 1.0, -1.0],
            "initialCorrections": [0.0, 0.0, 0.0, 0.0],
            "trainingStartUi": 10,
            "trainingEndUi": 200
        });

        let output = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "b5_training_run");
        assert!(output.status.success(), "{output:?}");
        let dir = root.0.join("b5_training_run");

        assert!(dir.join("dfe-adaptation.csv").is_file());
        assert!(dir.join("dfe-events.csv").is_file());

        // Check dfe-adaptation.csv
        let (adapt_headers, adapt_rows) = csv(dir.join("dfe-adaptation.csv"));
        assert_eq!(
            adapt_headers,
            vec!["clock_index", "time_s", "tap_0_weight", "tap_1_weight", "tap_2_weight", "tap_3_weight"]
        );
        assert!(!adapt_rows.is_empty());

        // Verify strict frozen weight invariance: all clocks >= 200 must match clock 200 exactly!
        if adapt_rows.len() > 200 {
            let frozen_row = &adapt_rows[200];
            for row in &adapt_rows[200..] {
                assert_eq!(row[2], frozen_row[2], "tap 0 drifted after training end!");
                assert_eq!(row[3], frozen_row[3], "tap 1 drifted after training end!");
                assert_eq!(row[4], frozen_row[4], "tap 2 drifted after training end!");
                assert_eq!(row[5], frozen_row[5], "tap 3 drifted after training end!");
            }
        }

        // Check dfe-events.csv
        let (event_headers, event_rows) = csv(dir.join("dfe-events.csv"));
        assert_eq!(
            event_headers,
            vec!["clock_index", "time_s", "slicer_input_v", "decision", "error_v", "update_enabled", "bank_updated"]
        );
        assert_eq!(event_rows.len(), adapt_rows.len().saturating_sub(1));

        // Check meta.json diagnostics for invariance assertion
        let meta: Value = serde_json::from_slice(&fs::read(dir.join("meta.json")).unwrap()).unwrap();
        let inv = &meta["diagnostics"]["touchstone_network"]["dfe_training_invariance"];
        assert_eq!(inv["checked"], true);
        assert_eq!(inv["training_end_ui"], 200);
        assert_eq!(inv["passes_invariance"], true);
        assert_eq!(inv["maximum_drift"], 0.0);

        // Verify receipt
        let receipt: Value = serde_json::from_slice(&fs::read(dir.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["status"], "complete");
        assert!(receipt["artifacts"]["dfe-adaptation.csv"].is_object());
        assert!(receipt["artifacts"]["dfe-events.csv"].is_object());
    }

    #[test]
    fn touchstone_network_runs_pam4_modulation_with_three_eye_metrics() {
        let root = Temp::new();
        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();

        // Configure PAM4 modulation with 512 bits (= 256 symbols)
        req["modulation"] = "pam4".into();
        req["timebase"]["nbits"] = 512.into();

        let output = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "pam4_run");
        assert!(output.status.success(), "{output:?}");
        let dir = root.0.join("pam4_run");

        for name in [
            "request.json",
            "meta.json",
            "arrays.npz",
            "waveforms.csv",
            "channel-impulse.csv",
            "frequency-response.csv",
            "cascade-nodes.csv",
            "eye-metrics.csv",
            "report.html",
            "channel-report.js",
            "receipt.json",
        ] {
            assert!(dir.join(name).is_file(), "missing artifact: {name}");
        }

        // Verify eye-metrics.csv contains PAM4 four levels, three thresholds, three eyes, and RLM
        let eye_text = fs::read_to_string(dir.join("eye-metrics.csv")).unwrap();
        assert!(eye_text.contains("pam4_level_0_v"));
        assert!(eye_text.contains("pam4_level_1_v"));
        assert!(eye_text.contains("pam4_level_2_v"));
        assert!(eye_text.contains("pam4_level_3_v"));
        assert!(eye_text.contains("pam4_threshold_lower_v"));
        assert!(eye_text.contains("pam4_threshold_mid_v"));
        assert!(eye_text.contains("pam4_threshold_upper_v"));
        assert!(eye_text.contains("pam4_eye_height_lower_v"));
        assert!(eye_text.contains("pam4_eye_height_mid_v"));
        assert!(eye_text.contains("pam4_eye_height_upper_v"));
        assert!(eye_text.contains("pam4_eye_height_worst_v"));
        assert!(eye_text.contains("pam4_eye_width_worst_ps"));
        assert!(eye_text.contains("pam4_rlm"));
        assert!(eye_text.contains("pam4_symbol_count"));

        // Verify meta.json metrics
        let meta: Value = serde_json::from_slice(&fs::read(dir.join("meta.json")).unwrap()).unwrap();
        let metrics = &meta["backend_metadata"]["metrics"];
        assert_eq!(metrics["pam4_symbol_count"], 256.0);
        let rlm = metrics["pam4_rlm"].as_f64().unwrap();
        assert!(rlm > 0.0 && rlm <= 1.0, "unexpected rlm: {rlm}");
        let worst_eh = metrics["pam4_eye_height_worst_v"].as_f64().unwrap();
        assert!(worst_eh > 0.0, "worst eye height must be positive for low-loss line: {worst_eh}");

        // Verify report.html has PAM4 summary cards
        let html = fs::read_to_string(dir.join("report.html")).unwrap();
        assert!(html.contains("Modulation"));
        assert!(html.contains("PAM4"));
        assert!(html.contains("PAM4 RLM"));
        assert!(html.contains("Worst eye height"));
        assert!(html.contains("Worst eye width"));

        // Verify receipt
        let receipt: Value = serde_json::from_slice(&fs::read(dir.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["status"], "complete");
        assert_eq!(receipt["channel_policy"], "touchstone-network-v1");
        assert!(receipt["artifacts"]["eye-metrics.csv"].is_object());
    }

    #[test]
    fn touchstone_network_runs_multi_channel_crosstalk_next_and_fext() {
        let root = Temp::new();
        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();
        req["timebase"]["nbits"] = 256.into();
        // Add two aggressors to the channel specification
        let aggressors = serde_json::json!([
            {
                "name": "fext_agg1",
                "kind": "fext",
                "amplitudeV": 1.0,
                "delaySeconds": 15.0e-12,
                "freqOffsetPpm": 50.0,
                "couplingCoeff": 0.08,
                "prbsOrder": 7,
                "prbsSeed": 111
            },
            {
                "name": "next_agg2",
                "kind": "next",
                "amplitudeV": 0.8,
                "delaySeconds": 0.0,
                "freqOffsetPpm": -30.0,
                "couplingCoeff": 0.05,
                "prbsOrder": 9,
                "prbsSeed": 222
            }
        ]);
        req["channel"]["value"]["aggressors"] = aggressors;

        let output = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "crosstalk_run");
        assert!(output.status.success(), "{output:?}");
        let dir = root.0.join("crosstalk_run");
        // Verify eye-metrics.csv has crosstalk metrics
        let eye_text = fs::read_to_string(dir.join("eye-metrics.csv")).unwrap();
        assert!(eye_text.contains("crosstalk_rms_v"));
        assert!(eye_text.contains("crosstalk_peak_to_peak_v"));
        assert!(eye_text.contains("crosstalk_scr_db"));
        assert!(eye_text.contains("crosstalk_fext_agg1_rms_v"));
        assert!(eye_text.contains("crosstalk_next_agg2_rms_v"));

        // Verify meta.json metrics
        let meta: Value = serde_json::from_slice(&fs::read(dir.join("meta.json")).unwrap()).unwrap();
        let metrics = &meta["backend_metadata"]["metrics"];
        assert_eq!(metrics["crosstalk_aggressor_count"], 2.0);
        let rms = metrics["crosstalk_rms_v"].as_f64().unwrap();
        assert!(rms > 0.0, "crosstalk RMS must be strictly positive: {rms}");
        let p2p = metrics["crosstalk_peak_to_peak_v"].as_f64().unwrap();
        assert!(p2p > 0.0, "crosstalk peak-to-peak must be strictly positive: {p2p}");
        let scr = metrics["crosstalk_scr_db"].as_f64().unwrap();
        assert!(scr.is_finite(), "crosstalk SCR must be finite: {scr}");

        // Verify report.html has crosstalk summary cards
        let html = fs::read_to_string(dir.join("report.html")).unwrap();
        assert!(html.contains("Crosstalk RMS"));
        assert!(html.contains("Crosstalk P-P"));
        assert!(html.contains("SCR"));

        // Verify receipt
        let receipt: Value = serde_json::from_slice(&fs::read(dir.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["status"], "complete");
        assert_eq!(receipt["channel_policy"], "touchstone-network-v1");
        assert!(receipt["artifacts"]["eye-metrics.csv"].is_object());
    }

    #[test]
    fn touchstone_network_runs_measured_tx_pulse_stimulus() {
        let root = Temp::new();
        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();
        req["timebase"]["nbits"] = 256.into();

        // Empirical single-pulse response measured or fitted from lab data
        let pulse = vec![0.0, 0.05, 0.25, 0.70, 1.0, 0.75, 0.35, 0.10, 0.02, 0.0];
        req["tx"]["measuredPulse"] = serde_json::json!({
            "pulseResponseV": pulse,
            "amplitudeScale": 0.9,
            "referencePlane": "tp0a"
        });

        let output = root.run_touchstone(&serde_json::to_vec(&req).unwrap(), "measured_tx_run");
        assert!(output.status.success(), "{output:?}");
        let dir = root.0.join("measured_tx_run");

        // Verify meta.json records that measured pulse was enabled
        let meta: Value = serde_json::from_slice(&fs::read(dir.join("meta.json")).unwrap()).unwrap();
        let metrics = &meta["backend_metadata"]["metrics"];
        assert_eq!(metrics["tx_measured_pulse_enabled"], 1.0);

        // Verify waveforms.csv was exported and contains smooth transitions
        let wave_csv = fs::read_to_string(dir.join("waveforms.csv")).unwrap();
        assert!(wave_csv.contains("tx_waveform_v"));
        assert!(wave_csv.contains("rx_output_v"));

        // Verify receipt
        let receipt: Value = serde_json::from_slice(&fs::read(dir.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["status"], "complete");
        assert_eq!(receipt["channel_policy"], "touchstone-network-v1");
    }

    #[test]
    fn channel_sweep_runs_and_exports_ranked_csv_and_optimal_metrics() {
        let root = Temp::new();
        let mut req: Value = serde_json::from_slice(TEMPLATE_TOUCHSTONE).unwrap();
        req["timebase"]["nbits"] = 256.into();
        req["sweep"] = serde_json::json!({
            "ctlePeakingGainDb": [0.0, 3.0, 6.0],
            "txFfePrecursor": [-0.1, 0.0],
            "txFfePostcursor": [-0.1, 0.0],
            "rankingMetric": "eye_height_worst_v"
        });

        let req_file = root.0.join("sweep_req.json");
        fs::write(&req_file, serde_json::to_vec_pretty(&req).unwrap()).unwrap();
        let out_dir = root.0.join("sweep_run");

        let output = cli(&[
            "channel",
            "sweep",
            req_file.to_str().unwrap(),
            "--output-dir",
            out_dir.to_str().unwrap(),
            "--channel-policy",
            "touchstone-network-v1",
        ]);
        assert!(output.status.success(), "{output:?}");

        // Verify sweep-results.csv
        let csv_text = fs::read_to_string(out_dir.join("sweep-results.csv")).unwrap();
        assert!(csv_text.contains("rank,candidate_id,ctle_boost_db"));
        assert!(csv_text.contains("valid"));

        // Verify meta.json
        let meta: Value = serde_json::from_slice(&fs::read(out_dir.join("meta.json")).unwrap()).unwrap();
        assert_eq!(meta["schema"], "sipi.channel.sweep-result.v1");
        assert_eq!(meta["totalCandidates"], 12);
        assert_eq!(meta["validCandidates"], 12);
        let opt_eh = meta["optimalEyeHeightV"].as_f64().unwrap();
        assert!(opt_eh > 0.0, "optimal eye height must be strictly positive: {opt_eh}");

        // Verify receipt
        let receipt: Value = serde_json::from_slice(&fs::read(out_dir.join("receipt.json")).unwrap()).unwrap();
        assert_eq!(receipt["status"], "complete");
        assert_eq!(receipt["command"], "channel sweep");
        assert!(receipt["artifacts"]["sweep-results.csv"].is_object());
    }
}
