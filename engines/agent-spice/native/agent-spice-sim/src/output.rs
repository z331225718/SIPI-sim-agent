use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;

use crate::error::Result;
use crate::result::SimulationResult;

pub fn write_json(result: &SimulationResult, path: &Path) -> Result<()> {
    let writer = BufWriter::new(File::create(path)?);
    serde_json::to_writer(writer, result)?;
    Ok(())
}

pub fn write_waveform(result: &SimulationResult, path: &Path) -> Result<usize> {
    let Some(analysis) = ["tran", "ac", "dc", "op"].into_iter().find(|analysis| {
        result
            .points
            .iter()
            .any(|point| point.analysis == *analysis)
    }) else {
        return Ok(0);
    };
    let first = result
        .points
        .iter()
        .find(|point| point.analysis == analysis)
        .expect("selected waveform analysis has at least one point");
    let names: Vec<&str> = if analysis == "ac" {
        first.complex.keys().map(String::as_str).collect()
    } else {
        first.values.keys().map(String::as_str).collect()
    };
    let mut writer = BufWriter::new(File::create(path)?);
    if analysis == "ac" {
        write!(writer, "frequency")?;
        for name in &names {
            write!(writer, ",real({name}),imag({name})")?;
        }
    } else {
        write!(
            writer,
            "{}",
            if analysis == "tran" { "time" } else { "sweep" }
        )?;
        for name in &names {
            write!(writer, ",{name}")?;
        }
    }
    writeln!(writer)?;

    let mut count = 0usize;
    for point in &result.points {
        if point.analysis != analysis {
            continue;
        }
        write!(writer, "{}", point.x)?;
        if analysis == "ac" {
            for name in &names {
                let value = &point.complex[*name];
                write!(writer, ",{},{}", value.re, value.im)?;
            }
        } else {
            for name in &names {
                write!(writer, ",{}", point.values[*name])?;
            }
        }
        writeln!(writer)?;
        count += 1;
    }
    Ok(count)
}
