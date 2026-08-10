#![forbid(unsafe_code)]

//! Explicit comparator-only export for the fixed RC/PULSE profile.
//!
//! This binary is feature-gated, accepts no input, and is not wired into the
//! product CLI. It exists only so an external comparator can consume the
//! product-owned typed result without a legacy parser or fallback route.

use std::io::{self, Write};

use sipi_tran::{RcPulseTransientV1, simulate_rc_pulse};
use sipi_types::AxisView;

const SCHEMA: &str = "sipi.tran.rc-pulse-harness.v1";

fn main() {
    if let Err(error) = run(io::stdout().lock()) {
        eprintln!("sipi-tran-rc-pulse-harness: {error}");
        std::process::exit(1);
    }
}

fn run(mut output: impl Write) -> Result<(), Box<dyn std::error::Error>> {
    let result = simulate_rc_pulse(RcPulseTransientV1::fixed_profile())?;
    let AxisView::Explicit(times) = result.time_axis().view() else {
        return Err("fixed RC/PULSE result must expose an explicit time axis".into());
    };

    write!(
        output,
        "{{\"schema\":\"{SCHEMA}\",\"profileId\":\"{}\",\"timeSeconds\":",
        RcPulseTransientV1::fixed_profile().profile_id()
    )?;
    write_values(&mut output, times.iter().map(|value| value.get()))?;
    write!(output, ",\"voltageInVolts\":")?;
    write_values(
        &mut output,
        result
            .voltage_in()
            .samples()
            .iter()
            .map(|value| value.get()),
    )?;
    write!(output, ",\"voltageOutVolts\":")?;
    write_values(
        &mut output,
        result
            .voltage_out()
            .samples()
            .iter()
            .map(|value| value.get()),
    )?;
    writeln!(output, "}}")?;
    Ok(())
}

fn write_values(
    output: &mut impl Write,
    values: impl ExactSizeIterator<Item = f64>,
) -> io::Result<()> {
    write!(output, "[")?;
    for (index, value) in values.enumerate() {
        if index != 0 {
            write!(output, ",")?;
        }
        write!(output, "{value}")?;
    }
    write!(output, "]")
}
