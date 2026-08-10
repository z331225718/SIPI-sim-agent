use std::{env, path::Path};

fn main() {
    let mut arguments = env::args_os();
    let _program = arguments.next();
    let Some(flag) = arguments.next() else {
        std::process::exit(2)
    };
    let Some(root) = arguments.next() else {
        std::process::exit(2)
    };
    if flag != "--job-root"
        || arguments.next().is_some()
        || sipi_ami_worker::run_one_job(Path::new(&root)).is_err()
    {
        std::process::exit(1);
    }
}
