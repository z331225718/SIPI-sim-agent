//! Feature-gated implementation behind the bounded public `sipi com run` route.

use sipi_agent_com_direct::{
    DirectRunErrorV1, DirectRunReportV1, DirectRunRequestV1, load_config_run_com_write_artifacts_v1,
};

pub(crate) fn run_com_direct_for_integration_v1(
    request: &DirectRunRequestV1,
) -> Result<DirectRunReportV1, DirectRunErrorV1> {
    load_config_run_com_write_artifacts_v1(request)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(0);

    fn digest(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    fn root() -> std::path::PathBuf {
        let id = NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "sipi-cli-com-direct-integration-{}-{}-{id}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("clock")
                .as_nanos()
        ));
        fs::create_dir_all(&path).expect("temp root");
        path
    }

    fn write_inputs(root: &std::path::Path) -> (std::path::PathBuf, std::path::PathBuf) {
        let config = root.join("config.json");
        let pulse = root.join("pulse.f64le");
        fs::write(
            &config,
            br#"{"parameters":{"samples_per_ui":8.0,"LEVELS":4.0,"bin_size":0.001,"A_v":0.5,"R_LM":50.0,"SNR_TX":30.0,"sigma_X":0.03,"sigma_RJ":0.0001,"h_J":[0.3,0.5,0.2],"sigma_N":0.01,"A_DD":0.4,"spec_ber":0.0001,"f2":50000000000.0}}"#,
        )
        .expect("config");
        let values = (0..64)
            .scan(0.0, |previous, index| {
                let pulse = 0.02 * (index as f64 * 0.21).sin();
                let impulse = pulse - *previous;
                *previous = pulse;
                Some(impulse)
            })
            .flat_map(f64::to_le_bytes)
            .collect::<Vec<_>>();
        fs::write(&pulse, values).expect("pulse");
        (config, pulse)
    }

    #[test]
    fn feature_gated_adapter_matches_standalone_direct_port() {
        let root = root();
        let (config, pulse) = write_inputs(&root);
        let standalone = DirectRunRequestV1::new(&config, &pulse, root.join("standalone"));
        let integrated = DirectRunRequestV1::new(&config, &pulse, root.join("integrated"));

        let expected =
            load_config_run_com_write_artifacts_v1(&standalone).expect("standalone direct run");
        let actual = run_com_direct_for_integration_v1(&integrated).expect("integrated direct run");

        assert_eq!(
            digest(&serde_json::to_vec(&expected.result).expect("expected JSON")),
            digest(&serde_json::to_vec(&actual.result).expect("actual JSON")),
            "the integration layer must not change the semantic result"
        );
        assert_eq!(expected.result["warnings"], actual.result["warnings"]);
        assert_eq!(
            expected.result["cases"].as_array().map(Vec::len),
            actual.result["cases"].as_array().map(Vec::len)
        );
        assert_eq!(
            expected.result["diagnostics"]["tdiln"],
            actual.result["diagnostics"]["tdiln"]
        );
        for (expected_path, actual_path) in [
            (
                &expected.artifacts.result_json,
                &actual.artifacts.result_json,
            ),
            (
                &expected.artifacts.report_html,
                &actual.artifacts.report_html,
            ),
            (
                &expected.artifacts.diagnostics_json,
                &actual.artifacts.diagnostics_json,
            ),
        ] {
            assert_eq!(
                digest(&fs::read(expected_path).expect("standalone artifact")),
                digest(&fs::read(actual_path).expect("integrated artifact")),
                "artifact content must be unchanged"
            );
        }

        let missing = DirectRunRequestV1::new(
            root.join("missing.json"),
            &pulse,
            root.join("missing-output"),
        );
        let direct_error =
            load_config_run_com_write_artifacts_v1(&missing).expect_err("missing input must fail");
        let adapter_error = run_com_direct_for_integration_v1(&missing)
            .expect_err("adapter must preserve the failure");
        assert_eq!(
            std::mem::discriminant(&direct_error),
            std::mem::discriminant(&adapter_error)
        );
        let _ = fs::remove_dir_all(root);
    }
}
