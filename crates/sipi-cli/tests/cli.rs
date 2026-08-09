use std::process::Command;

fn sipi() -> Command {
    Command::new(env!("CARGO_BIN_EXE_sipi"))
}

#[test]
fn capabilities_are_machine_readable_and_uncertified() {
    let output = sipi()
        .args(["capabilities", "--json"])
        .output()
        .expect("run sipi capabilities");

    assert!(output.status.success());
    assert_eq!(
        String::from_utf8(output.stdout).expect("UTF-8 stdout"),
        "{\"schema\":\"sipi.capabilities.v1\",\"product\":{\"name\":\"sipi\",\"version\":\"0.1.0\"},\"platform\":{\"target\":\"x86_64-pc-windows-msvc\",\"certification\":\"uncertified\"},\"capabilities\":[{\"domain\":\"tran\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"channel\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"ibis-ami\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"},{\"domain\":\"com\",\"status\":\"unsupported\",\"reason\":\"not_implemented\"}]}\n"
    );
    assert!(output.stderr.is_empty());
}

#[test]
fn run_is_explicitly_unsupported() {
    let output = sipi().arg("run").output().expect("run sipi run");

    assert_eq!(output.status.code(), Some(69));
    assert!(output.stdout.is_empty());
    assert_eq!(
        String::from_utf8(output.stderr).expect("UTF-8 stderr"),
        "{\"schema\":\"sipi.cli-error.v1\",\"code\":\"unsupported\",\"message\":\"simulation domains are not implemented in the P1-01 foundation\"}\n"
    );
}
