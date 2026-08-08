//! Numeric parity against reference values (sourced from
//! tests/test_rust_engine.py). Calls the library directly so no subprocess
//! or working-directory coupling is involved.
use std::path::Path;

use agent_spice_sim::error::Result;
use agent_spice_sim::netlist::Deck;
use agent_spice_sim::simulator::{SimulationObserver, run_with_observer};

struct NullObserver;
impl SimulationObserver for NullObserver {}

fn fixture(rel: &str) -> String {
    format!("{}/{}", env!("CARGO_MANIFEST_DIR"), rel)
}

/// Reference: tests/test_rust_engine.py divider OP {in=5.0, out=2.5}.
#[test]
fn divider_op_matches_oracle() -> Result<()> {
    let deck = Deck::parse_file(
        Path::new(&fixture(
            "../../native/AgentSpice.Engine/fixtures/divider.cir",
        )),
        None,
    )?;
    let mut observer = NullObserver;
    let result = run_with_observer(&deck, None, &mut observer, true)?;
    let op = result
        .points
        .iter()
        .find(|point| point.analysis == "op")
        .expect("op analysis point exists");
    assert_eq!(op.values["in"], 5.0);
    assert!((op.values["out"] - 2.5).abs() < 1e-9);
    // 1 op + 6 dc sweep points (V1 = 0,1,2,3,4,5).
    assert_eq!(result.points.len(), 7);
    Ok(())
}
