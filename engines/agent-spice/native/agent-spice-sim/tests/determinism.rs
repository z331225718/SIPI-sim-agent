//! Determinism: same deck must produce bit-identical results across runs.
use std::path::Path;

use agent_spice_sim::error::Result;
use agent_spice_sim::netlist::Deck;
use agent_spice_sim::simulator::{SimulationObserver, run_with_observer};

struct NullObserver;
impl SimulationObserver for NullObserver {}

fn fixture(rel: &str) -> String {
    format!("{}/{}", env!("CARGO_MANIFEST_DIR"), rel)
}

#[test]
fn same_deck_runs_are_bit_identical() -> Result<()> {
    let path = fixture("../../native/AgentSpice.Engine/fixtures/divider.cir");
    let deck_a = Deck::parse_file(Path::new(&path), None)?;
    let mut observer_a = NullObserver;
    let first = run_with_observer(&deck_a, None, &mut observer_a, true)?;

    let deck_b = Deck::parse_file(Path::new(&path), None)?;
    let mut observer_b = NullObserver;
    let second = run_with_observer(&deck_b, None, &mut observer_b, true)?;

    assert_eq!(first.nodes, second.nodes);
    assert_eq!(first.points.len(), second.points.len());
    for (a, b) in first.points.iter().zip(second.points.iter()) {
        assert_eq!(a.analysis, b.analysis);
        assert_eq!(a.x.to_bits(), b.x.to_bits());
        assert_eq!(a.values, b.values);
    }
    assert_eq!(
        format!("{:?}", first.statistics),
        format!("{:?}", second.statistics)
    );
    Ok(())
}
