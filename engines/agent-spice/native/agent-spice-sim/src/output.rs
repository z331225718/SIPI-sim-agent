use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;
use std::time::{Duration, Instant};

use crate::error::Result;
use crate::netlist::Analysis;
use crate::result::{SimulationPoint, SimulationResult, SimulationStatistics};
use crate::simulator::SimulationObserver;

const WAVEFORM_FLUSH_INTERVAL: Duration = Duration::from_millis(250);
const WAVEFORM_FLUSH_ROWS: usize = 128;
const PROGRESS_INTERVAL: Duration = Duration::from_secs(1);

pub struct RuntimeObserver {
    waveform: Option<LiveWaveformWriter>,
    last_progress: Instant,
    analysis_started: Instant,
}

impl RuntimeObserver {
    pub fn new(waveform_path: Option<&Path>, analyses: &[Analysis]) -> Result<Self> {
        let waveform = waveform_path
            .zip(selected_analysis(analyses))
            .map(|(path, analysis)| LiveWaveformWriter::new(path, analysis))
            .transpose()?;
        Ok(Self {
            waveform,
            last_progress: Instant::now(),
            analysis_started: Instant::now(),
        })
    }

    pub fn finish(&mut self) -> Result<usize> {
        if let Some(waveform) = &mut self.waveform {
            waveform.flush()?;
            Ok(waveform.rows)
        } else {
            Ok(0)
        }
    }
}

impl SimulationObserver for RuntimeObserver {
    fn analysis_started(&mut self, analysis: &str, total_points: usize) -> Result<()> {
        self.analysis_started = Instant::now();
        self.last_progress = Instant::now();
        eprintln!(
            "[agent-spice-sim] {} started: {} output point(s)",
            analysis.to_ascii_uppercase(),
            total_points
        );
        Ok(())
    }

    fn point(
        &mut self,
        point: &SimulationPoint,
        index: usize,
        total_points: usize,
        statistics: &SimulationStatistics,
    ) -> Result<()> {
        if let Some(waveform) = &mut self.waveform {
            waveform.write_point(point)?;
        }

        let now = Instant::now();
        if index == 1
            || index == total_points
            || now.duration_since(self.last_progress) >= PROGRESS_INTERVAL
        {
            let percent = if total_points == 0 {
                100.0
            } else {
                index as f64 * 100.0 / total_points as f64
            };
            if point.analysis == "tran" {
                eprintln!(
                    "[agent-spice-sim] TRAN {index}/{total_points} ({percent:.1}%) t={:.6e}s accepted={} rejected={}",
                    point.x,
                    statistics.accepted_transient_steps,
                    statistics.rejected_transient_steps
                );
            } else {
                eprintln!(
                    "[agent-spice-sim] {} {index}/{total_points} ({percent:.1}%) x={:.6e}",
                    point.analysis.to_ascii_uppercase(),
                    point.x
                );
            }
            self.last_progress = now;
        }
        Ok(())
    }

    fn analysis_finished(
        &mut self,
        analysis: &str,
        total_points: usize,
        _statistics: &SimulationStatistics,
    ) -> Result<()> {
        if let Some(waveform) = &mut self.waveform {
            waveform.flush_if_analysis(analysis)?;
        }
        eprintln!(
            "[agent-spice-sim] {} completed: {} output point(s) in {:.3}s",
            analysis.to_ascii_uppercase(),
            total_points,
            self.analysis_started.elapsed().as_secs_f64()
        );
        Ok(())
    }
}

struct LiveWaveformWriter {
    analysis: &'static str,
    writer: BufWriter<File>,
    names: Vec<String>,
    initialized: bool,
    rows: usize,
    rows_since_flush: usize,
    last_flush: Instant,
}

impl LiveWaveformWriter {
    fn new(path: &Path, analysis: &'static str) -> Result<Self> {
        Ok(Self {
            analysis,
            writer: BufWriter::new(File::create(path)?),
            names: Vec::new(),
            initialized: false,
            rows: 0,
            rows_since_flush: 0,
            last_flush: Instant::now(),
        })
    }

    fn write_point(&mut self, point: &SimulationPoint) -> Result<()> {
        if point.analysis != self.analysis {
            return Ok(());
        }
        if !self.initialized {
            self.names = if self.analysis == "ac" {
                point.complex.keys().cloned().collect()
            } else {
                point.values.keys().cloned().collect()
            };
            self.write_header()?;
            self.initialized = true;
        }

        write!(self.writer, "{}", point.x)?;
        if self.analysis == "ac" {
            for name in &self.names {
                let value = &point.complex[name];
                write!(self.writer, ",{},{}", value.re, value.im)?;
            }
        } else {
            for name in &self.names {
                write!(self.writer, ",{}", point.values[name])?;
            }
        }
        writeln!(self.writer)?;
        self.rows += 1;
        self.rows_since_flush += 1;

        if self.rows == 1
            || self.rows_since_flush >= WAVEFORM_FLUSH_ROWS
            || self.last_flush.elapsed() >= WAVEFORM_FLUSH_INTERVAL
        {
            self.flush()?;
        }
        Ok(())
    }

    fn write_header(&mut self) -> Result<()> {
        if self.analysis == "ac" {
            write!(self.writer, "frequency")?;
            for name in &self.names {
                write!(self.writer, ",real({name}),imag({name})")?;
            }
        } else {
            write!(
                self.writer,
                "{}",
                if self.analysis == "tran" {
                    "time"
                } else {
                    "sweep"
                }
            )?;
            for name in &self.names {
                write!(self.writer, ",{name}")?;
            }
        }
        writeln!(self.writer)?;
        Ok(())
    }

    fn flush_if_analysis(&mut self, analysis: &str) -> Result<()> {
        if analysis == self.analysis {
            self.flush()?;
        }
        Ok(())
    }

    fn flush(&mut self) -> Result<()> {
        self.writer.flush()?;
        self.rows_since_flush = 0;
        self.last_flush = Instant::now();
        Ok(())
    }
}

fn selected_analysis(analyses: &[Analysis]) -> Option<&'static str> {
    ["tran", "ac", "dc", "op"].into_iter().find(|candidate| {
        analyses.iter().any(|analysis| {
            matches!(
                (candidate, analysis),
                (&"tran", Analysis::Tran { .. })
                    | (&"ac", Analysis::Ac { .. })
                    | (&"dc", Analysis::Dc { .. })
                    | (&"op", Analysis::Op)
            )
        })
    })
}

pub fn write_json(result: &SimulationResult, path: &Path) -> Result<()> {
    let writer = BufWriter::new(File::create(path)?);
    serde_json::to_writer(writer, result)?;
    Ok(())
}
