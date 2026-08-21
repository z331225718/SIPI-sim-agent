#![forbid(unsafe_code)]

use std::io::{self, Read, Write};

use sipi_tran::{ExactRcMeasurementDeckLimitsV1, parse_and_simulate_exact_rc_measurement_deck_v1};
use sipi_types::AxisView;

const SCHEMA: &str = "sipi.tran.exact-rc-measurement-harness.v1";
const MAX_DECK_BYTES: usize = 4096;

fn main() {
    if let Err(error) = run(io::stdin().lock(), io::stdout().lock()) {
        eprintln!("sipi-tran-exact-rc-measurement-stdin: {error}");
        std::process::exit(1);
    }
}

fn run(mut input: impl Read, mut output: impl Write) -> Result<(), Box<dyn std::error::Error>> {
    let mut deck_bytes = Vec::with_capacity(MAX_DECK_BYTES + 1);
    input
        .by_ref()
        .take((MAX_DECK_BYTES + 1) as u64)
        .read_to_end(&mut deck_bytes)?;
    if deck_bytes.len() > MAX_DECK_BYTES {
        return Err("deck exceeds the harness byte budget".into());
    }
    let deck = std::str::from_utf8(&deck_bytes)?;
    let limits = ExactRcMeasurementDeckLimitsV1::try_new(MAX_DECK_BYTES, 7, 16, 32)?;
    let result = parse_and_simulate_exact_rc_measurement_deck_v1(deck, limits)?;
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
