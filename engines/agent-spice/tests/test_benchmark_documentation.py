from pathlib import Path


DELETED_BENCHMARK_DOCS = {
    "docs/sparam-large-port-idem-benchmark.md",
    "docs/idem-init-probe.md",
    "docs/idem_algorithm_analysis.md",
    "docs/passivity_benchmark_analysis_Gemini.md",
    "docs/sparam-passivity-next-directions_GLM5p2.md",
    "docs/walkthrough.md",
    "docs/superpowers/plans/2026-07-07-idem-passivity-enforcement.md",
    "docs/superpowers/plans/2026-07-08-passivity-ground-truth-to-idem.md",
    "docs/superpowers/plans/2026-07-09-passivity-direction-validation-plan.md",
    "docs/superpowers/plans/2026-07-09-passivity-next-directions.md",
    "docs/superpowers/plans/2026-07-10-data-driven-full-pole-discovery.md",
    "docs/superpowers/plans/2026-07-10-randomized-loewner-common-poles.md",
    "docs/superpowers/plans/2026-07-10-pole-placement-direction-d.md",
    "docs/superpowers/plans/2026-07-10-pole-placement-d4-d6.md",
}


def test_historical_benchmark_docs_are_removed_and_readme_points_to_canonical_report():
    assert not [path for path in DELETED_BENCHMARK_DOCS if Path(path).exists()]
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "docs/sparam-idem-full-benchmark.md" in readme
    assert "docs/sparam-large-port-idem-benchmark.md" not in readme


def test_current_target_driven_contract_docs_are_preserved():
    assert Path("docs/superpowers/specs/2026-07-10-target-driven-sparam-fit-design.md").is_file()
    assert Path("docs/superpowers/plans/2026-07-10-target-driven-sparam-fit.md").is_file()
