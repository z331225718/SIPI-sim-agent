use std::fmt;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;
use std::sync::{Mutex, OnceLock};

static LOG: OnceLock<Mutex<BufWriter<File>>> = OnceLock::new();

pub fn initialize(path: &Path) -> std::io::Result<()> {
    let writer = BufWriter::new(File::create(path)?);
    LOG.set(Mutex::new(writer)).map_err(|_| {
        std::io::Error::new(
            std::io::ErrorKind::AlreadyExists,
            "simulation log was already initialized",
        )
    })
}

pub fn line(arguments: fmt::Arguments<'_>) {
    let Some(log) = LOG.get() else {
        return;
    };
    let Ok(mut writer) = log.lock() else {
        return;
    };
    let _ = writeln!(writer, "{arguments}");
    let _ = writer.flush();
}
