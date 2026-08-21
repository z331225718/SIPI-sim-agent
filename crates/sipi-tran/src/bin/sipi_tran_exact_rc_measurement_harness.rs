#![forbid(unsafe_code)]

use std::io::{self, Write};

use sipi_tran::{ExactRcMeasurementDeckLimitsV1, parse_and_simulate_exact_rc_measurement_deck_v1};
use sipi_types::AxisView;

const SCHEMA: &str = "sipi.tran.exact-rc-measurement-harness.v1";
const DECK: &str = "Agent-Spice bounded RC measurement\n\
V1 in 0 PULSE(0 1 1u 1n 1n 10u 20u)\n\
R1 in out 1k\n\
C1 out 0 1u\n\
.tran 1u 3u\n\
.measure TRAN vmax MAX V(out)\n\
.end\n";

fn main() {
    if let Err(error) = run(io::stdout().lock()) {
        eprintln!("sipi-tran-exact-rc-measurement-harness: {error}");
        std::process::exit(1);
    }
}

fn run(mut output: impl Write) -> Result<(), Box<dyn std::error::Error>> {
    let limits = ExactRcMeasurementDeckLimitsV1::try_new(4096, 7, 16, 32)?;
    let result = parse_and_simulate_exact_rc_measurement_deck_v1(DECK, limits)?;
    let AxisView::Explicit(times) = result.transient().time_axis().view() else {
        return Err("exact RC measurement result must expose an explicit time axis".into());
    };
    write!(output, "{{\"schema\":\"{SCHEMA}\",\"timeSeconds\":")?;
    write_values(&mut output, times.iter().map(|value| value.get()))?;
    write!(output, ",\"voltageInVolts\":")?;
    write_values(
        &mut output,
        result
            .transient()
            .voltage_in()
            .samples()
            .iter()
            .map(|value| value.get()),
    )?;
    write!(output, ",\"voltageOutVolts\":")?;
    write_values(
        &mut output,
        result
            .transient()
            .voltage_out()
            .samples()
            .iter()
            .map(|value| value.get()),
    )?;
    writeln!(
        output,
        ",\"measurement\":{{\"analysis\":\"tran\",\"name\":\"{}\",\"operation\":\"max\",\"target\":\"v(out)\",\"valueVolts\":{}}}}}",
        result.measurement().name(),
        result.measurement().value().get(),
    )?;
    Ok(())
}

fn write_values(output: &mut impl Write, values: impl Iterator<Item = f64>) -> io::Result<()> {
    write!(output, "[")?;
    for (index, value) in values.enumerate() {
        if index != 0 {
            write!(output, ",")?;
        }
        write!(output, "{value}")?;
    }
    write!(output, "]")
}
