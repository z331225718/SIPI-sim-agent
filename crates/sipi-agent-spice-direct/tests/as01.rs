use std::{fs, path::PathBuf, process::Command};

use sipi_agent_spice_direct::fit_sparam::{
    FitSparamError, FitSparamOptions, FitSparamRequest, KernelStatus, LegacyPassivityFlags,
    MAX_FIT_ORDER, MAX_PRIORITY_BANDS, MAX_TOUCHSTONE_BYTES, MAX_TOUCHSTONE_LINE_BYTES,
    MAX_TOUCHSTONE_SAMPLES, PassivityPolicy, PriorityBand, TargetBranch, fit_sparam,
    plan_fit_sparam, read_touchstone, resolve_passivity,
};

#[test]
fn pinned_as01_corpus_covers_full_band_priority_band_and_artifact_overrides() {
    let full = plan_fit_sparam(
        "fixtures/through.s2p",
        FitSparamOptions {
            rms_target: Some(0.001),
            ..FitSparamOptions::default()
        },
    )
    .unwrap();
    assert_eq!(full.target_branch, TargetBranch::FullBand);
    assert_eq!(
        full.artifacts.output,
        PathBuf::from("fixtures/through_fitted.sp")
    );

    let priority = plan_fit_sparam(
        "fixtures/through.s2p",
        FitSparamOptions {
            priority_bands: vec![PriorityBand::new(1.0e6, 1.0e9, 0.01, 1.0).unwrap()],
            ..FitSparamOptions::default()
        },
    )
    .unwrap();
    assert_eq!(priority.target_branch, TargetBranch::PriorityBandOnly);
    assert!(!priority.target_branch.full_band_is_blocking());

    let explicit = plan_fit_sparam(
        "fixtures/through.s2p",
        FitSparamOptions {
            output: Some(PathBuf::from("out/model.sp")),
            report: Some(PathBuf::from("out/result.json")),
            html_report: Some(PathBuf::from("out/result.html")),
            fitted_touchstone: Some(PathBuf::from("out/result.s2p")),
            rfm: Some(PathBuf::from("out/result.rfm")),
            rfm_wrapper: Some(PathBuf::from("out/result_wrapper.sp")),
            log: Some(PathBuf::from("out/result.log")),
            rms_target: Some(0.001),
            ..FitSparamOptions::default()
        },
    )
    .unwrap();
    assert_eq!(explicit.artifacts.output, PathBuf::from("out/model.sp"));
    assert_eq!(explicit.artifacts.report, PathBuf::from("out/result.json"));
    assert_eq!(
        explicit.artifacts.html_report,
        PathBuf::from("out/result.html")
    );
    assert_eq!(
        explicit.artifacts.fitted_touchstone,
        PathBuf::from("out/result.s2p")
    );
    assert_eq!(
        explicit.kernel_status,
        KernelStatus::NativeFixedPoleResidueFit
    );
}

#[test]
fn pinned_as01_corpus_covers_passivity_and_target_rejections() {
    assert_eq!(
        PassivityPolicy::parse("enforce").unwrap(),
        PassivityPolicy::Enforce
    );
    assert_eq!(
        PassivityPolicy::parse("bad").unwrap_err(),
        FitSparamError::UnsupportedPassivity("bad".to_owned())
    );
    assert_eq!(
        resolve_passivity(
            Some(PassivityPolicy::Off),
            LegacyPassivityFlags {
                skip_check: true,
                ..LegacyPassivityFlags::default()
            }
        )
        .unwrap_err(),
        FitSparamError::ConflictingPassivityFlags
    );
    assert_eq!(
        plan_fit_sparam("line.s2p", FitSparamOptions::default()).unwrap_err(),
        FitSparamError::MissingRmsTarget
    );
    assert_eq!(
        plan_fit_sparam(
            "line.s2p",
            FitSparamOptions {
                rms_target: Some(0.001),
                priority_bands: vec![PriorityBand {
                    f_min_hz: 2.0,
                    f_max_hz: 1.0,
                    rms_target: 0.01,
                    weight: 1.0,
                }],
                ..FitSparamOptions::default()
            }
        )
        .unwrap_err(),
        FitSparamError::InvalidPriorityBandRange
    );
}

#[test]
fn minimal_numeric_route_reads_fits_and_writes_the_artifact_family() {
    let root = std::env::temp_dir().join(format!("sipi-as01-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let input = root.join("through.s2p");
    let text = "# Hz S RI R 50\n0 0 0 0.5 0 0.5 0 0 0\n1000000 0 0 0.5 0 0.5 0 0 0\n2000000 0 0 0.5 0 0.5 0 0 0\n3000000 0 0 0.5 0 0.5 0 0 0\n4000000 0 0 0.5 0 0.5 0 0 0\n5000000 0 0 0.5 0 0.5 0 0 0\n";
    fs::write(&input, text).unwrap();
    let network = read_touchstone(&input).unwrap();
    assert_eq!(network.ports(), 2);
    assert_eq!(network.sample_count(), 6);
    let options = FitSparamOptions {
        report: Some(root.join("result.json")),
        fitted_touchstone: Some(root.join("result.s2p")),
        log: Some(root.join("result.log")),
        rms_target: Some(1.0e-3),
        passivity: Some(PassivityPolicy::Off),
        min_order: 1,
        max_order: Some(1),
        n_poles_real: 1,
        n_poles_cmplx: 0,
        enforce_dc: false,
        ..FitSparamOptions::default()
    };
    let request = FitSparamRequest::new(&input, options).unwrap();
    let result = fit_sparam(&request).unwrap();
    assert!(result.target_met);
    assert_eq!(result.selected_order, 1);
    assert!(result.rms_error < 1.0e-3);
    for path in [
        result.artifacts.report,
        result.artifacts.fitted_touchstone,
        result.artifacts.log,
    ] {
        assert!(path.is_file(), "missing artifact {}", path.display());
    }
    let report = fs::read_to_string(root.join("result.json")).unwrap();
    assert!(report.contains("as-01-fit-sparam-result-v1"));
    assert!(!root.join("through_fitted.sp").exists());
    assert!(!root.join("through_fitted.rfm").exists());
    assert!(!root.join("through_fitted_rfm_wrapper.sp").exists());
    assert!(!root.join("through_fitted_report.html").exists());
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn unsolvable_order_fails_closed_instead_of_retrying_forever() {
    let root = std::env::temp_dir().join(format!("sipi-as01-unsolvable-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let input = root.join("single.s2p");
    fs::write(
        &input,
        "# Hz S RI R 50\n0 0 0 0.5 0 0.5 0 0 0\n1000000 0 0 0.5 0 0.5 0 0 0\n",
    )
    .unwrap();

    let error = fit_sparam(
        &FitSparamRequest::new(
            &input,
            FitSparamOptions {
                report: Some(root.join("single.json")),
                fitted_touchstone: Some(root.join("single_fitted.s2p")),
                log: Some(root.join("single.log")),
                rms_target: Some(1.0e-3),
                passivity: Some(PassivityPolicy::Off),
                min_order: 10,
                max_order: Some(10),
                ..FitSparamOptions::default()
            },
        )
        .unwrap(),
    )
    .unwrap_err();
    assert!(matches!(error, FitSparamError::FitNumericalFailure(_)));
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn sampled_passivity_check_is_observational_and_bounded() {
    let root = std::env::temp_dir().join(format!("sipi-as01-passivity-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let input = root.join("passive.s2p");
    fs::write(
        &input,
        "# Hz S RI R 50\n0 0 0 0.1 0 0.1 0 0 0\n1000000 0 0 0.1 0 0.1 0 0 0\n2000000 0 0 0.1 0 0.1 0 0 0\n",
    )
    .unwrap();
    let result = fit_sparam(
        &FitSparamRequest::new(
            &input,
            FitSparamOptions {
                report: Some(root.join("passive.json")),
                fitted_touchstone: Some(root.join("passive_fitted.s2p")),
                log: Some(root.join("passive.log")),
                rms_target: Some(1.0),
                passivity: Some(PassivityPolicy::Check),
                min_order: 1,
                max_order: Some(1),
                n_poles_real: 1,
                n_poles_cmplx: 0,
                enforce_dc: false,
                ..FitSparamOptions::default()
            },
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(
        result.passivity,
        sipi_agent_spice_direct::fit_sparam::PassivityObservation::SampledPass
    );
    assert!(result.target_met);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn touchstone_formats_and_port_boundary_are_explicit() {
    let root = std::env::temp_dir().join(format!("sipi-as01-formats-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let rows = "0 {a} {b} {c} {d} {e} {f} {g} {h}\n1000000 {a} {b} {c} {d} {e} {f} {g} {h}\n";
    let ri = rows
        .replace("{a}", "0")
        .replace("{b}", "0")
        .replace("{c}", "0.5")
        .replace("{d}", "0")
        .replace("{e}", "0.5")
        .replace("{f}", "0")
        .replace("{g}", "0")
        .replace("{h}", "0");
    fs::write(root.join("ri.s2p"), format!("# Hz S RI R 50\n{ri}")).unwrap();
    fs::write(
        root.join("ma.s2p"),
        "# MHz S MA R 50\n0 0 0 0.5 90 0.5 90 0 0\n1 0 0 0.5 90 0.5 90 0 0\n",
    )
    .unwrap();
    fs::write(
        root.join("db.s2p"),
        "# GHz S DB R 50\n0 0 0 -6.020599913 0 -6.020599913 0 0 0\n1 0 0 -6.020599913 0 -6.020599913 0 0 0\n",
    )
    .unwrap();
    assert!((read_touchstone(root.join("ri.s2p")).unwrap().samples()[0][1].re - 0.5).abs() < 1e-12);
    assert!((read_touchstone(root.join("ma.s2p")).unwrap().samples()[0][1].im - 0.5).abs() < 1e-12);
    assert!((read_touchstone(root.join("db.s2p")).unwrap().samples()[0][1].re - 0.5).abs() < 1e-6);
    let wide_row = (0..33).map(|_| "0").collect::<Vec<_>>().join(" ");
    fs::write(
        root.join("wide.s4p"),
        format!("# Hz S RI R 50\n{wide_row}\n{wide_row}\n"),
    )
    .unwrap();
    assert!(matches!(
        FitSparamRequest::new(
            root.join("wide.s4p"),
            FitSparamOptions {
                rms_target: Some(1.0),
                passivity: Some(PassivityPolicy::Off),
                ..FitSparamOptions::default()
            }
        )
        .and_then(|request| fit_sparam(&request)),
        Err(FitSparamError::UnsupportedPortCount(4))
    ));
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn execution_budgets_and_unimplemented_artifacts_fail_closed() {
    assert!(matches!(
        plan_fit_sparam(
            "line.s2p",
            FitSparamOptions {
                rms_target: Some(1.0),
                max_order: Some(MAX_FIT_ORDER + 1),
                ..FitSparamOptions::default()
            }
        ),
        Err(FitSparamError::BudgetExceeded {
            kind: "fit order",
            ..
        })
    ));
    assert!(matches!(
        plan_fit_sparam(
            "line.s2p",
            FitSparamOptions {
                priority_bands: vec![
                    PriorityBand::new(0.0, 1.0, 1.0, 1.0).unwrap();
                    MAX_PRIORITY_BANDS + 1
                ],
                ..FitSparamOptions::default()
            }
        ),
        Err(FitSparamError::BudgetExceeded {
            kind: "priority band count",
            ..
        })
    ));
    let request = FitSparamRequest::new(
        "missing.s2p",
        FitSparamOptions {
            output: Some(PathBuf::from("model.sp")),
            rms_target: Some(1.0),
            ..FitSparamOptions::default()
        },
    )
    .unwrap();
    assert_eq!(
        fit_sparam(&request).unwrap_err(),
        FitSparamError::UnsupportedExecutionOption("--output")
    );

    let root = std::env::temp_dir().join(format!("sipi-as01-budgets-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    let long_line = root.join("long.s2p");
    fs::write(
        &long_line,
        format!(
            "# Hz S RI R 50\n!{}\n0 0 0 0.5 0 0.5 0 0 0\n1 0 0 0.5 0 0.5 0 0 0\n",
            "x".repeat(MAX_TOUCHSTONE_LINE_BYTES + 1)
        ),
    )
    .unwrap();
    assert!(matches!(
        read_touchstone(&long_line),
        Err(FitSparamError::BudgetExceeded {
            kind: "Touchstone line bytes",
            ..
        })
    ));

    let oversized = root.join("oversized.s2p");
    fs::File::create(&oversized)
        .unwrap()
        .set_len((MAX_TOUCHSTONE_BYTES + 1) as u64)
        .unwrap();
    assert!(matches!(
        read_touchstone(&oversized),
        Err(FitSparamError::BudgetExceeded {
            kind: "Touchstone input bytes",
            ..
        })
    ));

    let dense = root.join("dense.s2p");
    let mut dense_text = String::from("# Hz S RI R 50\n");
    for sample in 0..6_000 {
        dense_text.push_str(&format!("{sample} 0 0 0.5 0 0.5 0 0 0\n"));
    }
    fs::write(&dense, dense_text).unwrap();
    let error = fit_sparam(
        &FitSparamRequest::new(
            &dense,
            FitSparamOptions {
                report: Some(root.join("dense.json")),
                fitted_touchstone: Some(root.join("dense_fitted.s2p")),
                log: Some(root.join("dense.log")),
                rms_target: Some(1.0),
                passivity: Some(PassivityPolicy::Off),
                min_order: MAX_FIT_ORDER,
                max_order: Some(MAX_FIT_ORDER),
                enforce_dc: false,
                ..FitSparamOptions::default()
            },
        )
        .unwrap(),
    )
    .unwrap_err();
    assert!(matches!(
        error,
        FitSparamError::BudgetExceeded {
            kind: "least-squares matrix cells",
            ..
        }
    ));

    let too_many_samples = root.join("too-many.s2p");
    let mut sample_text = String::from("# Hz S RI R 50\n");
    for sample in 0..=MAX_TOUCHSTONE_SAMPLES {
        sample_text.push_str(&format!("{sample} 0 0 0.5 0 0.5 0 0 0\n"));
    }
    fs::write(&too_many_samples, sample_text).unwrap();
    assert!(matches!(
        read_touchstone(&too_many_samples),
        Err(FitSparamError::BudgetExceeded {
            kind: "Touchstone sample count",
            ..
        })
    ));
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn cli_rejects_options_that_the_numeric_route_does_not_consume() {
    let binary = env!("CARGO_BIN_EXE_sipi-agent-spice-fit-sparam");
    let cases = [
        vec!["--output", "model.sp"],
        vec!["--html-report", "report.html"],
        vec!["--rfm", "model.rfm"],
        vec!["--rfm-wrapper", "wrapper.sp"],
        vec!["--report-top-rms", "5"],
        vec!["--outside-band-weight", "0.1"],
        vec!["--priority-band", "0:1e6:0.1:2"],
        vec!["--quality-profile", "explore"],
        vec!["--fail-on-quality"],
        vec!["--allow-quality-warnings"],
        vec!["--subckt-name", "s_equivalent"],
        vec!["--tuning-profile", "profile.json"],
        vec!["--fit-iterations", "14"],
        vec!["--hf-complex-pairs", "2"],
        vec!["--hf-pair-damping", "0.03"],
        vec!["--hf-pair-start-fraction", "0.68"],
        vec!["--passivity-max-iterations", "3"],
        vec!["--passivity-samples", "8"],
        vec!["--passivity-active-variables", "3072"],
        vec!["--pole-spacing", "resonance"],
    ];
    for extra in cases {
        let output = Command::new(binary)
            .args(["fit-sparam", "input.s2p"])
            .args(&extra)
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(2), "case {extra:?}");
        assert!(
            String::from_utf8_lossy(&output.stderr).contains("not implemented"),
            "case {extra:?}: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
}

fn alias_test_options(paths: &[PathBuf; 4]) -> FitSparamOptions {
    FitSparamOptions {
        report: Some(paths[1].clone()),
        fitted_touchstone: Some(paths[2].clone()),
        log: Some(paths[3].clone()),
        rms_target: Some(1.0),
        passivity: Some(PassivityPolicy::Off),
        min_order: 1,
        max_order: Some(1),
        n_poles_real: 1,
        n_poles_cmplx: 0,
        enforce_dc: false,
        output: None,
        html_report: None,
        rfm: None,
        rfm_wrapper: None,
        tuning_profile: None,
        ..FitSparamOptions::default()
    }
}

fn assert_alias_rejected_without_writes(paths: &[PathBuf; 4]) {
    let snapshots = paths
        .iter()
        .map(|path| (path.clone(), fs::read(path).ok()))
        .collect::<Vec<_>>();
    let request = FitSparamRequest::new(&paths[0], alias_test_options(paths)).unwrap();
    assert!(matches!(
        fit_sparam(&request),
        Err(FitSparamError::DuplicateOutputPath(_))
    ));
    for (path, before) in snapshots {
        match before {
            Some(bytes) => assert_eq!(
                fs::read(&path).unwrap(),
                bytes,
                "changed {}",
                path.display()
            ),
            None => assert!(!path.exists(), "created {}", path.display()),
        }
    }
}

#[test]
fn input_and_output_aliases_fail_before_any_existing_file_changes() {
    const INPUT: &str = "# Hz S RI R 50\n0 0 0 0.5 0 0.5 0 0 0\n1 0 0 0.5 0 0.5 0 0 0\n";
    let root = std::env::temp_dir().join(format!("sipi-as01-aliases-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();

    for (case, (left, right)) in [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
        .into_iter()
        .enumerate()
    {
        let case_root = root.join(format!("same-{case}"));
        fs::create_dir_all(&case_root).unwrap();
        let mut paths = [
            case_root.join("input.s2p"),
            case_root.join("report.json"),
            case_root.join("fitted.s2p"),
            case_root.join("fit.log"),
        ];
        paths[right] = paths[left].clone();
        fs::write(&paths[0], INPUT).unwrap();
        for path in paths.iter().skip(1) {
            if !path.exists() {
                fs::write(path, format!("sentinel-{case}")).unwrap();
            }
        }
        assert_alias_rejected_without_writes(&paths);
    }

    let dotdot_root = root.join("dotdot");
    fs::create_dir_all(dotdot_root.join("child")).unwrap();
    let dotdot_paths = [
        dotdot_root.join("input.s2p"),
        dotdot_root.join("child").join("..").join("input.s2p"),
        dotdot_root.join("fitted.s2p"),
        dotdot_root.join("fit.log"),
    ];
    fs::write(&dotdot_paths[0], INPUT).unwrap();
    fs::write(&dotdot_paths[2], "fitted-sentinel").unwrap();
    fs::write(&dotdot_paths[3], "log-sentinel").unwrap();
    assert_alias_rejected_without_writes(&dotdot_paths);

    let hardlink_root = root.join("hardlink");
    fs::create_dir_all(&hardlink_root).unwrap();
    let hardlink_paths = [
        hardlink_root.join("input.s2p"),
        hardlink_root.join("report.json"),
        hardlink_root.join("fitted.s2p"),
        hardlink_root.join("fit.log"),
    ];
    fs::write(&hardlink_paths[0], INPUT).unwrap();
    fs::hard_link(&hardlink_paths[0], &hardlink_paths[1]).unwrap();
    fs::write(&hardlink_paths[2], "fitted-sentinel").unwrap();
    fs::write(&hardlink_paths[3], "log-sentinel").unwrap();
    assert_alias_rejected_without_writes(&hardlink_paths);

    let output_hardlink_root = root.join("output-hardlink");
    fs::create_dir_all(&output_hardlink_root).unwrap();
    let output_hardlink_paths = [
        output_hardlink_root.join("input.s2p"),
        output_hardlink_root.join("report.json"),
        output_hardlink_root.join("fitted.s2p"),
        output_hardlink_root.join("fit.log"),
    ];
    fs::write(&output_hardlink_paths[0], INPUT).unwrap();
    fs::write(&output_hardlink_paths[1], "output-sentinel").unwrap();
    fs::hard_link(&output_hardlink_paths[1], &output_hardlink_paths[3]).unwrap();
    fs::write(&output_hardlink_paths[2], "fitted-sentinel").unwrap();
    assert_alias_rejected_without_writes(&output_hardlink_paths);

    let symlink_root = root.join("symlink");
    fs::create_dir_all(&symlink_root).unwrap();
    let symlink_paths = [
        symlink_root.join("input.s2p"),
        symlink_root.join("report.json"),
        symlink_root.join("fitted.s2p"),
        symlink_root.join("fit.log"),
    ];
    fs::write(&symlink_paths[0], INPUT).unwrap();
    let symlink_result = {
        #[cfg(windows)]
        {
            std::os::windows::fs::symlink_file(&symlink_paths[0], &symlink_paths[1])
        }
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(&symlink_paths[0], &symlink_paths[1])
        }
    };
    if symlink_result.is_ok() {
        fs::write(&symlink_paths[2], "fitted-sentinel").unwrap();
        fs::write(&symlink_paths[3], "log-sentinel").unwrap();
        assert_alias_rejected_without_writes(&symlink_paths);
    }

    let symlink_parent_root = root.join("symlink-parent");
    let real_parent = symlink_parent_root.join("real");
    let alias_parent = symlink_parent_root.join("alias");
    fs::create_dir_all(&real_parent).unwrap();
    let directory_symlink_result = {
        #[cfg(windows)]
        {
            std::os::windows::fs::symlink_dir(&real_parent, &alias_parent)
        }
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(&real_parent, &alias_parent)
        }
    };
    if directory_symlink_result.is_ok() {
        let symlink_parent_paths = [
            symlink_parent_root.join("input.s2p"),
            real_parent.join("result.json"),
            symlink_parent_root.join("fitted.s2p"),
            alias_parent.join("result.json"),
        ];
        fs::write(&symlink_parent_paths[0], INPUT).unwrap();
        fs::write(&symlink_parent_paths[2], "fitted-sentinel").unwrap();
        assert_alias_rejected_without_writes(&symlink_parent_paths);
    }

    let _ = fs::remove_dir_all(&root);
}
