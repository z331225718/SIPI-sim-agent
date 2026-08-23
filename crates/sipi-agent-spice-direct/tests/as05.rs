use sipi_agent_spice_direct::{
    Backend, DependencyAdmission, ExecutionStage, PreparationStatus, RunHspiceRequest,
    admit_run_hspice, audit_deck,
};

#[test]
fn relative_and_escaping_dependencies_are_visible_to_admission() {
    let admission = admit_run_hspice(
        "demo",
        ".include 'models/pdn.inc'\n.lib '../outside.lib' tt\n.end\n",
        RunHspiceRequest::new("native", "runs", false).unwrap(),
    )
    .unwrap();
    assert_eq!(
        admission.cases[0]
            .dependencies
            .iter()
            .map(|item| item.admission)
            .collect::<Vec<_>>(),
        [
            DependencyAdmission::RelativeRequiresSourceRoot,
            DependencyAdmission::LexicallyEscapesSourceRoot
        ]
    );
}

#[test]
fn prepared_artifact_contract_is_backend_specific_without_execution() {
    for (backend, needs_case_sp) in [
        (Backend::Native, false),
        (Backend::Ngspice, false),
        (Backend::Xyce, false),
        (Backend::XyceXdm, true),
    ] {
        let request = RunHspiceRequest::new(backend.name(), "runs", false).unwrap();
        let admission = admit_run_hspice("demo", ".end\n", request).unwrap();
        let paths = &admission.cases[0].output_paths;
        assert!(paths.iter().any(|path| path.ends_with("case.cir")));
        assert!(
            paths
                .iter()
                .any(|path| path.ends_with("compat_report.json"))
        );
        assert_eq!(
            paths.iter().any(|path| path.ends_with("case.sp")),
            needs_case_sp
        );
        assert_eq!(admission.execution_stage, ExecutionStage::NotExecuted);
        assert_eq!(
            admission.cases[0].preparation_status,
            PreparationStatus::Compatible
        );
    }
}

#[test]
fn project_manifest_and_run_directory_match_upstream_contract() {
    let manifest = serde_yaml::from_str::<serde_yaml::Value>(
        "name: demo_pdn\nbackend: NGSPICE\ninputs:\n  hspice_deck: decks/main.sp\noutputs:\n  root: runs-out\n",
    )
    .unwrap();
    let parsed = sipi_agent_spice_direct::ProjectManifest::from_mapping(&manifest).unwrap();
    assert_eq!(parsed.name, "demo_pdn");
    assert_eq!(parsed.backend, Backend::Ngspice);
    assert_eq!(
        parsed.hspice_deck.as_deref(),
        Some(std::path::Path::new("decks/main.sp"))
    );
    assert_eq!(parsed.output_root, std::path::PathBuf::from("runs-out"));
    let root = std::env::temp_dir().join(format!("sipi-as05-project-{}", std::process::id()));
    let run =
        sipi_agent_spice_direct::prepare_project_run_directory(&root, "demo_pdn", "base").unwrap();
    assert_eq!(run, root.join("demo_pdn/base"));
    assert!(run.is_dir());
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn project_manifest_dispatch_reaches_deck_backend_and_report_contract() {
    let root = std::env::temp_dir().join(format!("sipi-as05-project-run-{}", std::process::id()));
    std::fs::create_dir_all(root.join("decks")).unwrap();
    std::fs::write(root.join("decks/main.sp"), ".tran 1p 1n\n.end\n").unwrap();
    std::fs::write(
        root.join("project.yaml"),
        "name: demo_pdn\nbackend: native\ninputs:\n  hspice_deck: decks/main.sp\noutputs:\n  root: runs-out\n",
    )
    .unwrap();
    let result =
        sipi_agent_spice_direct::run_hspice_project(root.join("project.yaml"), false, None)
            .unwrap();
    assert_eq!(result.status, PreparationStatus::Compatible);
    assert!(root.join("runs-out/main/main__base/case.cir").is_file());
    assert!(root.join("runs-out/main/run_report.json").is_file());
    let _ = std::fs::remove_dir_all(root);
}

#[test]
fn pinned_differential_corpus_covers_quotes_repeat_rejections_backends_alter_and_missing_end() {
    let quoted = audit_deck(
        ".include 'models/pdn with space.inc'\n.lib \"./corners with space.lib\" tt\n.end\n",
    );
    assert_eq!(quoted.includes, ["models/pdn with space.inc"]);
    assert_eq!(quoted.libraries[0].path, "./corners with space.lib");
    assert_eq!(quoted.libraries[0].section.as_deref(), Some("tt"));

    let source = ".include 'models/pdn with space.inc'\n.lib \"./corners with space.lib\" tt\nIcursig vdd 0 pwl(\n+ 0ps 1 3500ps 2 6000ps 3\n+ R=3500ps ) M=4\n.alter fast\n.param corner=2\n";
    for backend in Backend::ALL {
        let admission = admit_run_hspice(
            "corpus",
            source,
            RunHspiceRequest::new(backend.name(), "runs", false).unwrap(),
        )
        .unwrap();
        assert_eq!(admission.cases.len(), 2);
        assert!(
            admission
                .cases
                .iter()
                .all(|case| !case.case.text.contains(".end"))
        );
        assert_eq!(
            admission.cases[1].case.kind,
            sipi_agent_spice_direct::CaseKind::Alter
        );
        if backend == Backend::Ngspice {
            assert_eq!(
                admission.cases[0].actions[0].kind,
                "rewrite_current_pwl_repeat"
            );
            assert!(
                admission.cases[0]
                    .deck_text
                    .contains("Bcursig vdd 0 I = (4) * pwl((time <= 3500ps")
            );
            assert!(admission.cases[0].unsupported.is_empty());
        } else {
            assert!(admission.cases[0].actions.is_empty());
        }
    }

    let missing_point = admit_run_hspice(
        "invalid-point",
        "Icursig vdd 0 pwl(\n+ 0ps 1 6000ps 3\n+ R=3500ps )\n.end\n",
        RunHspiceRequest::new("ngspice", "runs", false).unwrap(),
    )
    .unwrap();
    assert_eq!(
        missing_point.cases[0].unsupported[0].reason,
        "current_pwl_repeat_point_not_found"
    );
    assert_eq!(
        missing_point.cases[0].preparation_status,
        PreparationStatus::Blocked
    );

    let invalid_window = admit_run_hspice(
        "invalid-window",
        "Icursig vdd 0 pwl(\n+ 0ps 1 3500ps 2\n+ R=3500ps )\n.end\n",
        RunHspiceRequest::new("ngspice", "runs", false).unwrap(),
    )
    .unwrap();
    assert_eq!(
        invalid_window.cases[0].unsupported[0].reason,
        "invalid_current_pwl_repeat_window"
    );
    assert_eq!(
        invalid_window.cases[0].preparation_status,
        PreparationStatus::Blocked
    );
}
