//! Branch-level probes for the pinned native request surface.
//!
//! These tests intentionally exercise one field/branch combination at a time;
//! the aggregate sim-native replay is not a substitute for proving that a
//! request field reaches the native stage that owns it.

use std::collections::BTreeMap;

use sipi_pybert_direct::{
    AdditiveNoiseV1, AnalysisConfigV1, ChannelInputV1, ChannelResponseV1, CtleConfigV1,
    DfeConfigV1, FfeConfigV1, Hertz, MetallicLineChannelV1, ModulationV1, NativeCancellationToken,
    NativeSimulationError, Ohms, PatternV1, PeriodicNoiseV1, ResourceLimitsV1, RxConfigV1,
    SIMULATION_SCHEMA_V1, Seconds, SimulationInputV1, StatisticalEyeConfigV1, TxConfigV1,
    ViterbiConfigV1, Volts, simulate_native_v1, simulate_native_v1_with_cancellation,
};

fn impulse() -> ChannelInputV1 {
    ChannelInputV1::ImpulseResponse(ChannelResponseV1 {
        sample_interval: Seconds(1.0e-12),
        impulse_response_volts_per_second: vec![1.0e12, 0.15e12, -0.03e12],
        source_impedance: Ohms(50.0),
        load_impedance: Ohms(50.0),
    })
}

fn base(run_id: &str) -> SimulationInputV1 {
    SimulationInputV1 {
        schema: SIMULATION_SCHEMA_V1.into(),
        run_id: run_id.into(),
        modulation: ModulationV1::Nrz,
        pattern: PatternV1::Prbs { order: 7, seed: 17 },
        timebase: sipi_pybert_direct::TimebaseV1 {
            sample_interval: Seconds(1.0e-12),
            samples_per_ui: 4,
            data_rate: Hertz(250.0e9),
            nbits: 128,
        },
        channel: impulse(),
        tx: TxConfigV1 {
            amplitude: Volts(0.8),
            ffe: FfeConfigV1::default(),
            additive_noise: None,
            periodic_noise: None,
        },
        rx: RxConfigV1 {
            native_ctle_enabled: false,
            ctle: None,
            ffe: FfeConfigV1::default(),
            dfe_taps: 0,
            dfe: None,
            viterbi_enabled: false,
            viterbi: None,
        },
        analysis: AnalysisConfigV1 {
            statistical_eye: None,
            include_jitter: false,
            include_bathtub: false,
            ber_eye_bits: Some(64),
            jitter_eye_uis: None,
            jitter_rel_thresh: None,
        },
        limits: ResourceLimitsV1 {
            max_total_samples: 2_000_000,
            max_memory_bytes: 256 * 1024 * 1024,
            max_distribution_states: 10_000,
        },
        external_models: Vec::new(),
        legacy_options: BTreeMap::new(),
    }
}

fn dfe() -> DfeConfigV1 {
    DfeConfigV1 {
        gain: 0.1,
        decision_scaler: Volts(0.4),
        n_ave: 4,
        delta_t: Seconds(1.0e-13),
        alpha: 0.01,
        n_lock_ave: 4,
        rel_lock_tol: 0.1,
        lock_sustain: 2,
        ideal: true,
        bandwidth: Hertz(12.0e9),
        use_agc: true,
        agc_n_ave: 4,
        tap_limits: Some(vec![(-0.2, 0.2)]),
    }
}

fn run(input: &SimulationInputV1) -> sipi_pybert_direct::SimulationOutputV1 {
    simulate_native_v1(input).unwrap_or_else(|error| {
        panic!("{} failed: {error}", input.run_id);
    })
}

#[test]
fn native_request_reaches_impulse_tx_rx_ffe_dfe_ber_branches() {
    let mut input = base("branch-ffe-dfe-ber");
    input.tx.ffe = FfeConfigV1 {
        enabled: true,
        weights: vec![0.05, 0.1, 0.8, 0.1, 0.05],
        cursor_position: 2,
    };
    input.rx.ffe = FfeConfigV1 {
        enabled: true,
        weights: vec![0.0, 1.0, 0.0],
        cursor_position: 1,
    };
    input.rx.dfe_taps = 1;
    input.rx.dfe = Some(dfe());
    let output = run(&input);
    assert!(output.arrays.contains_key("rx_ffe_impulse_v_per_v"));
    assert!(output.arrays.contains_key("dfe_output_v"));
    assert!(output.metrics.contains_key("ber"));
}

#[test]
fn native_request_reaches_imported_ctle_impulse_branch() {
    let mut input = base("branch-ctle-imported-impulse");
    input.rx.native_ctle_enabled = true;
    input.rx.ctle = Some(CtleConfigV1 {
        bandwidth: Hertz(12.0e9),
        peak_frequency: Hertz(5.0e9),
        peak_magnitude_db: 1.7,
        frequency_step_hz: None,
        frequency_max_hz: None,
        impulse_response_v_per_v: Some(vec![1.0, 0.25, -0.05]),
    });
    let output = run(&input);
    assert_eq!(
        output.arrays["rx_filter_impulse_v_per_v"],
        vec![1.0, 0.25, -0.05]
    );
}

#[test]
fn native_request_reaches_explicit_bits_and_disabled_equalizers() {
    let mut input = base("branch-explicit-disabled");
    input.pattern = PatternV1::ExplicitBits {
        bit_count: 16,
        bits: vec![0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1],
    };
    input.timebase.nbits = 16;
    input.tx.ffe = FfeConfigV1 {
        enabled: false,
        weights: vec![0.0, 1.0, 0.0],
        cursor_position: 1,
    };
    input.rx.ffe = FfeConfigV1 {
        enabled: false,
        weights: vec![],
        cursor_position: 0,
    };
    let output = run(&input);
    assert_eq!(output.metrics["generated_bits"], 16.0);
    assert!(output.arrays.contains_key("symbols_v"));
}

#[test]
fn native_request_reaches_every_upstream_prbs_order() {
    for order in [7, 9, 11, 13, 15, 19, 20, 23, 31] {
        let mut input = base(&format!("branch-prbs-{order}"));
        input.pattern = PatternV1::Prbs { order, seed: 17 };
        input.timebase.nbits = 32;
        let output = run(&input);
        assert_eq!(output.metrics["generated_bits"], 32.0);
    }
}

#[test]
fn native_request_reaches_all_modulation_branches() {
    let mut pam4 = base("branch-pam4");
    pam4.modulation = ModulationV1::Pam4;
    pam4.rx.dfe_taps = 1;
    pam4.rx.dfe = Some(dfe());
    let pam4_output = run(&pam4);
    assert!(pam4_output.arrays.contains_key("dfe_bits"));

    let mut duo = base("branch-duobinary");
    duo.modulation = ModulationV1::DuoBinary;
    let duo_output = run(&duo);
    assert!(duo_output.arrays.contains_key("symbols_v"));
}

#[test]
fn native_request_reaches_adaptive_dfe_and_duobinary_receiver_branches() {
    let mut adaptive = base("branch-dfe-adaptive-agc-off");
    adaptive.rx.dfe_taps = 1;
    adaptive.rx.dfe = Some(DfeConfigV1 {
        ideal: false,
        use_agc: false,
        ..dfe()
    });
    let adaptive_output = run(&adaptive);
    assert!(adaptive_output.arrays.contains_key("dfe_tap_weights_v"));

    let mut duo = base("branch-dfe-duobinary");
    duo.modulation = ModulationV1::DuoBinary;
    duo.rx.dfe_taps = 1;
    duo.rx.dfe = Some(dfe());
    let duo_output = run(&duo);
    assert!(duo_output.arrays.contains_key("dfe_bits"));
}

#[test]
fn native_request_reaches_additive_periodic_noise_branch() {
    let mut input = base("branch-noise");
    let sample_count = (input.timebase.nbits * u64::from(input.timebase.samples_per_ui)) as usize;
    input.tx.additive_noise = Some(AdditiveNoiseV1 {
        samples_v: (0..sample_count)
            .map(|index| if index % 11 == 0 { 1.0e-3 } else { 0.0 })
            .collect(),
        effective_seed: Some(17),
    });
    input.tx.periodic_noise = Some(PeriodicNoiseV1 {
        magnitude: Volts(2.0e-3),
        frequency: Hertz(2.0e9),
    });
    let output = run(&input);
    assert!(output.arrays.contains_key("additive_noise_v"));
    assert!(output.arrays.contains_key("periodic_noise_v"));
    assert!(output.arrays.contains_key("receiver_input_noise_v"));
    assert_eq!(output.metrics.get("effective_noise_seed"), Some(&17.0));
}

#[test]
fn native_request_reaches_analytic_ctle_and_metallic_line_grid_branches() {
    let mut ctle = base("branch-ctle");
    ctle.rx.native_ctle_enabled = true;
    ctle.rx.ctle = Some(CtleConfigV1 {
        bandwidth: Hertz(12.0e9),
        peak_frequency: Hertz(5.0e9),
        peak_magnitude_db: 1.7,
        frequency_step_hz: Some(Hertz(10.0e9)),
        frequency_max_hz: Some(Hertz(40.0e9)),
        impulse_response_v_per_v: None,
    });
    let ctle_output = run(&ctle);
    assert!(
        ctle_output
            .arrays
            .get("rx_filter_impulse_v_per_v")
            .is_some_and(|values| values.len() > 1)
    );

    let mut line = base("branch-metallic-grid");
    line.channel = ChannelInputV1::MetallicLine(MetallicLineChannelV1 {
        sample_interval: Seconds(1.0e-12),
        length_m: 0.05,
        skin_effect_resistance_ohm_per_m: 1.452,
        crossover_angular_frequency_rad_per_s: 10.0e6,
        dc_resistance_ohm_per_m: 0.1876,
        characteristic_impedance: Ohms(100.0),
        propagation_velocity_m_per_s: 0.67 * 3.0e8,
        loss_tangent: 0.02,
        source_impedance: Ohms(50.0),
        source_capacitance_f: 0.5e-12,
        load_impedance: Ohms(100.0),
        load_capacitance_f: 0.5e-12,
        apply_raised_cosine_window: true,
        frequency_step_hz: Some(Hertz(10.0e9)),
        frequency_max_hz: Some(Hertz(40.0e9)),
        impulse_length: Some(Seconds(1.0e-9)),
    });
    let line_output = run(&line);
    assert!(
        line_output
            .arrays
            .contains_key("legacy_channel_frequency_hz")
    );
    assert!(line_output.arrays.contains_key("legacy_stage_ctle_re"));
}

#[test]
fn native_request_reaches_native_fft_channel_and_ctle_defaults() {
    let mut ctle = base("branch-ctle-native-grid");
    ctle.rx.native_ctle_enabled = true;
    ctle.rx.ctle = Some(CtleConfigV1 {
        bandwidth: Hertz(12.0e9),
        peak_frequency: Hertz(5.0e9),
        peak_magnitude_db: 1.7,
        frequency_step_hz: None,
        frequency_max_hz: None,
        impulse_response_v_per_v: None,
    });
    let ctle_output = run(&ctle);
    assert!(ctle_output.arrays.contains_key("rx_filter_impulse_v_per_v"));

    let mut line = base("branch-metallic-native-grid");
    line.channel = ChannelInputV1::MetallicLine(MetallicLineChannelV1 {
        sample_interval: Seconds(1.0e-12),
        length_m: 0.05,
        skin_effect_resistance_ohm_per_m: 1.452,
        crossover_angular_frequency_rad_per_s: 10.0e6,
        dc_resistance_ohm_per_m: 0.1876,
        characteristic_impedance: Ohms(100.0),
        propagation_velocity_m_per_s: 0.67 * 3.0e8,
        loss_tangent: 0.02,
        source_impedance: Ohms(50.0),
        source_capacitance_f: 0.5e-12,
        load_impedance: Ohms(100.0),
        load_capacitance_f: 0.5e-12,
        apply_raised_cosine_window: false,
        frequency_step_hz: None,
        frequency_max_hz: None,
        impulse_length: None,
    });
    let line_output = run(&line);
    assert!(
        !line_output
            .arrays
            .contains_key("legacy_channel_frequency_hz")
    );
    assert!(line_output.arrays.contains_key("channel_impulse_v_per_v"));
}

#[test]
fn native_request_reaches_jitter_bathtub_and_statistical_eye_branches() {
    let mut jitter = base("branch-jitter-bathtub");
    jitter.timebase.nbits = 2048;
    jitter.analysis.include_jitter = true;
    jitter.analysis.include_bathtub = true;
    jitter.analysis.jitter_eye_uis = Some(512);
    let jitter_output = run(&jitter);
    assert!(jitter_output.metrics.contains_key("jitter_dfe_random_s"));
    assert!(jitter_output.arrays.contains_key("bathtub_dfe_ber"));

    let mut eye = base("branch-statistical-eye");
    eye.timebase.nbits = 256;
    eye.analysis.statistical_eye = Some(StatisticalEyeConfigV1 {
        target_ber: 1.0e-5,
        contour_ber_levels: vec![1.0e-4, 1.0e-3],
        rx_rj_ui: Some(0.001),
        rx_dj_ui: Some(0.001),
        tx_rj_ui: Some(0.001),
        tx_dj_ui: Some(0.001),
        tx_dcd_ui: Some(0.001),
        voltage_resolution: Some(Volts(1.0e-3)),
        time_points: 32,
        max_distribution_states: 10_000,
        post_receiver_output: true,
    });
    let eye_output = run(&eye);
    assert!(
        eye_output
            .arrays
            .contains_key("statistical_eye_impulse_v_per_v")
    );
    assert!(eye_output.arrays.contains_key("eye_contour_0_x_ui"));
    assert_eq!(eye_output.metrics["eye_is_pre_dfe_linear"], 0.0);

    let mut pre_dfe_eye = eye;
    pre_dfe_eye.run_id = "branch-statistical-eye-pre-dfe".into();
    pre_dfe_eye
        .analysis
        .statistical_eye
        .as_mut()
        .expect("statistical eye config")
        .post_receiver_output = false;
    let pre_dfe_output = run(&pre_dfe_eye);
    assert_eq!(pre_dfe_output.metrics["eye_is_pre_dfe_linear"], 1.0);
}

#[test]
fn native_request_reaches_independent_jitter_and_bathtub_switches() {
    let mut jitter_only = base("branch-jitter-only");
    jitter_only.timebase.nbits = 2048;
    jitter_only.analysis.include_jitter = true;
    jitter_only.analysis.include_bathtub = false;
    let jitter_output = run(&jitter_only);
    assert!(jitter_output.metrics.contains_key("jitter_dfe_random_s"));
    assert!(!jitter_output.arrays.contains_key("bathtub_dfe_ber"));

    let mut bathtub_only = base("branch-bathtub-only");
    bathtub_only.timebase.nbits = 2048;
    bathtub_only.analysis.include_jitter = false;
    bathtub_only.analysis.include_bathtub = true;
    let bathtub_output = run(&bathtub_only);
    assert!(bathtub_output.arrays.contains_key("bathtub_dfe_ber"));
}

#[test]
fn native_request_reaches_viterbi_isi_and_pam4_fec_branches() {
    let mut isi = base("branch-viterbi-isi");
    isi.channel = ChannelInputV1::ImpulseResponse(ChannelResponseV1 {
        sample_interval: Seconds(1.0e-12),
        impulse_response_volts_per_second: vec![
            1.0e12, 0.15e12, -0.03e12, 0.02e12, -0.01e12, 0.005e12, 0.0, 0.0, 0.0,
        ],
        source_impedance: Ohms(50.0),
        load_impedance: Ohms(50.0),
    });
    isi.rx.dfe_taps = 1;
    isi.rx.dfe = Some(dfe());
    isi.rx.viterbi_enabled = true;
    isi.rx.viterbi = Some(ViterbiConfigV1 {
        state_symbols: 2,
        fec: false,
        noise_sigma_v: Some(Volts(0.01)),
        max_states: 128,
    });
    let isi_output = run(&isi);
    assert!(isi_output.arrays.contains_key("viterbi_state_path"));
    assert!(isi_output.arrays.contains_key("viterbi_bits"));

    let mut fec = base("branch-viterbi-fec");
    fec.modulation = ModulationV1::Pam4;
    fec.timebase.nbits = 64;
    fec.rx.dfe_taps = 1;
    fec.rx.dfe = Some(dfe());
    fec.rx.viterbi_enabled = true;
    fec.rx.viterbi = Some(ViterbiConfigV1 {
        state_symbols: 2,
        fec: true,
        noise_sigma_v: None,
        max_states: 128,
    });
    let fec_output = run(&fec);
    assert!(fec_output.arrays.contains_key("viterbi_state_path"));
    assert!(fec_output.metrics.contains_key("fec_encoded_bit_count"));
}

#[test]
fn native_request_fail_closed_branches_are_explicit() {
    let mut empty = base("branch-empty-explicit");
    empty.pattern = PatternV1::ExplicitBits {
        bit_count: 8,
        bits: vec![],
    };
    empty.timebase.nbits = 8;
    assert!(matches!(
        simulate_native_v1(&empty),
        Err(NativeSimulationError::UnsupportedPattern)
    ));

    let mut external = base("branch-external-model");
    external.channel =
        sipi_pybert_direct::ChannelInputV1::ExternalModel(sipi_pybert_direct::ExternalModelRefV1 {
            kind: "ibis_ami_tx".into(),
            capability: "host_driven".into(),
        });
    assert!(matches!(
        simulate_native_v1(&external),
        Err(NativeSimulationError::UnsupportedChannel)
            | Err(NativeSimulationError::UnsupportedExternalModel)
    ));

    let mut external_list = base("branch-external-list");
    external_list
        .external_models
        .push(sipi_pybert_direct::ExternalModelRefV1 {
            kind: "ibis_ami_rx".into(),
            capability: "host_driven".into(),
        });
    assert!(matches!(
        simulate_native_v1(&external_list),
        Err(NativeSimulationError::UnsupportedExternalModel)
    ));

    let mut no_dfe = base("branch-missing-dfe");
    no_dfe.rx.dfe_taps = 1;
    assert!(matches!(
        simulate_native_v1(&no_dfe),
        Err(NativeSimulationError::MissingDfeConfiguration)
    ));

    let mut no_ctle = base("branch-missing-ctle");
    no_ctle.rx.native_ctle_enabled = true;
    assert!(matches!(
        simulate_native_v1(&no_ctle),
        Err(NativeSimulationError::MissingCtleConfiguration)
    ));

    let mut fec_nrz = base("branch-fec-nrz");
    fec_nrz.rx.dfe_taps = 1;
    fec_nrz.rx.dfe = Some(dfe());
    fec_nrz.rx.viterbi_enabled = true;
    fec_nrz.rx.viterbi = Some(ViterbiConfigV1 {
        state_symbols: 2,
        fec: true,
        noise_sigma_v: None,
        max_states: 128,
    });
    assert!(matches!(
        simulate_native_v1(&fec_nrz),
        Err(NativeSimulationError::UnsupportedFecModulation)
    ));

    let mut legacy_options = base("branch-legacy-options");
    legacy_options
        .legacy_options
        .insert("unmigrated".into(), true.into());
    assert!(matches!(
        simulate_native_v1(&legacy_options),
        Err(NativeSimulationError::UnsupportedLegacyOptions)
    ));

    let mut additive_length = base("branch-additive-length");
    additive_length.tx.additive_noise = Some(AdditiveNoiseV1 {
        samples_v: vec![0.0],
        effective_seed: Some(17),
    });
    assert!(matches!(
        simulate_native_v1(&additive_length),
        Err(NativeSimulationError::AdditiveNoiseLengthMismatch)
    ));

    let mut no_viterbi = base("branch-missing-viterbi");
    no_viterbi.rx.viterbi_enabled = true;
    assert!(matches!(
        simulate_native_v1(&no_viterbi),
        Err(NativeSimulationError::MissingViterbiConfiguration)
    ));

    let mut no_viterbi_dfe = base("branch-missing-viterbi-dfe");
    no_viterbi_dfe.rx.viterbi_enabled = true;
    no_viterbi_dfe.rx.viterbi = Some(ViterbiConfigV1 {
        state_symbols: 2,
        fec: false,
        noise_sigma_v: Some(Volts(0.01)),
        max_states: 128,
    });
    assert!(matches!(
        simulate_native_v1(&no_viterbi_dfe),
        Err(NativeSimulationError::MissingViterbiDfe)
    ));

    let mut bad_channel_timebase = base("branch-channel-timebase");
    if let ChannelInputV1::ImpulseResponse(response) = &mut bad_channel_timebase.channel {
        response.sample_interval = Seconds(2.0e-12);
    }
    assert!(matches!(
        simulate_native_v1(&bad_channel_timebase),
        Err(NativeSimulationError::UnsupportedChannel)
    ));

    let mut bad_eye_modulation = base("branch-eye-modulation");
    bad_eye_modulation.modulation = ModulationV1::Pam4;
    bad_eye_modulation.analysis.statistical_eye = Some(StatisticalEyeConfigV1 {
        target_ber: 1.0e-5,
        contour_ber_levels: vec![],
        rx_rj_ui: None,
        rx_dj_ui: None,
        tx_rj_ui: None,
        tx_dj_ui: None,
        tx_dcd_ui: None,
        voltage_resolution: None,
        time_points: 32,
        max_distribution_states: 10_000,
        post_receiver_output: false,
    });
    assert!(matches!(
        simulate_native_v1(&bad_eye_modulation),
        Err(NativeSimulationError::UnsupportedStatisticalEyeModulation)
    ));

    let mut bad_limit = base("branch-resource-limit");
    bad_limit.limits.max_total_samples = 1;
    assert!(matches!(
        simulate_native_v1(&bad_limit),
        Err(NativeSimulationError::ResourceLimitExceeded)
    ));

    let cancellation = NativeCancellationToken::default();
    cancellation.cancel();
    assert!(matches!(
        simulate_native_v1_with_cancellation(&base("branch-cancel"), &cancellation),
        Err(NativeSimulationError::Cancelled)
    ));
}
