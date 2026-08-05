use std::collections::BTreeMap;

use pybert_core::{
    AnalysisConfigV1, ChannelInputV1, ChannelResponseV1, ExternalModelRefV1, FfeConfigV1,
    Hertz, ModulationV1, Ohms, PatternV1, ResourceLimitsV1, RxConfigV1,
    SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1, StatisticalEyeConfigV1, TimebaseV1,
    TxConfigV1, Volts,
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

fn input() -> SimulationInputV1 {
    SimulationInputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: "sipi-external-conformance".into(),
        modulation: ModulationV1::Nrz,
        pattern: PatternV1::Prbs { order: 7, seed: 17 },
        timebase: TimebaseV1 {
            sample_interval: Seconds(1.0e-12),
            samples_per_ui: 32,
            data_rate: Hertz(32.0e9),
            nbits: 1024,
        },
        channel: ChannelInputV1::ImpulseResponse(ChannelResponseV1 {
            sample_interval: Seconds(1.0e-12),
            impulse_response_volts_per_second: vec![0.0, 1.0e12, 0.0],
            source_impedance: Ohms(50.0),
            load_impedance: Ohms(50.0),
        }),
        tx: TxConfigV1 {
            amplitude: Volts(1.0),
            ffe: FfeConfigV1 {
                enabled: true,
                weights: vec![0.0, 1.0, 0.0],
                cursor_position: 1,
            },
            additive_noise: None,
            periodic_noise: None,
        },
        rx: RxConfigV1::default(),
        analysis: AnalysisConfigV1 {
            statistical_eye: Some(StatisticalEyeConfigV1 {
                target_ber: 1.0e-12,
                contour_ber_levels: vec![1.0e-12, 1.0e-9],
                rx_rj_ui: Some(0.01),
                rx_dj_ui: Some(0.02),
                tx_rj_ui: None,
                tx_dj_ui: None,
                tx_dcd_ui: None,
                voltage_resolution: Some(Volts(1.0e-3)),
                time_points: 400,
                max_distribution_states: 200_000,
                post_receiver_output: false,
            }),
            ..AnalysisConfigV1::default()
        },
        limits: ResourceLimitsV1::default(),
        external_models: vec![ExternalModelRefV1 {
            kind: "ibis_ami".into(),
            capability: "init".into(),
        }],
        legacy_options: BTreeMap::new(),
    }
}

fn main() {
    let produced = input();
    produced.validate().expect("producer input is valid");
    let payload = serde_json::to_vec(&produced).expect("PyBERT Serialize");
    let base_payload_sha256 = format!("{:x}", Sha256::digest(&payload));
    let producer_schema = serde_json::from_slice::<Value>(&payload).expect("produced JSON")["schema"]
        == SIMULATION_SCHEMA_V1;

    let consumed: SimulationInputV1 = serde_json::from_slice(&payload).expect("PyBERT Deserialize");
    let consumer_accept = consumed.validate().is_ok() && consumed == produced;

    let mut incompatible: Value = serde_json::from_slice(&payload).expect("produced JSON");
    incompatible["schema"] = Value::String("pybert.simulation.v2".into());
    let incompatible = serde_json::to_vec(&incompatible).expect("versioned JSON");
    let incompatible_payload_sha256 = format!("{:x}", Sha256::digest(&incompatible));
    let incompatible: SimulationInputV1 = serde_json::from_slice(&incompatible).expect("PyBERT Deserialize v2");
    let consumer_version_reject = incompatible
        .validate()
        .is_err_and(|error| matches!(error, pybert_core::ContractError::UnsupportedSchema(_)));

    println!(
        "{}",
        serde_json::to_string(&json!({"runner":"pybert_core_rust","results":[
            {"probe":"producer_serializes","decision":if producer_schema {"accept"} else {"reject"},"phase":"schema","base_payload_sha256":base_payload_sha256,"consumed_payload_sha256":base_payload_sha256},
            {"probe":"consumer_deserializes","decision":if consumer_accept {"accept"} else {"reject"},"phase":"schema","base_payload_sha256":base_payload_sha256,"consumed_payload_sha256":base_payload_sha256},
            {"probe":"consumer_version_rejects","decision":if consumer_version_reject {"reject"} else {"accept"},"phase":"schema","code":"unsupported_schema","base_payload_sha256":base_payload_sha256,"consumed_payload_sha256":incompatible_payload_sha256,"derived_from":"producer_serializes"}
        ]})).expect("probe JSON")
    );
}
