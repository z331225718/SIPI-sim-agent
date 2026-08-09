use sipi_contracts::{
    CapabilityCatalogV1, ContractError, WireWaveformV1, deterministic_json, parse_waveform_v1,
};

const VALID_WAVEFORM: &[u8] = include_bytes!("fixtures/waveform-valid.v1.json");
const UNKNOWN_FIELD: &[u8] = include_bytes!("fixtures/waveform-unknown-field.v1.json");
const VERSION_REJECT: &[u8] = include_bytes!("fixtures/waveform-version-reject.v1.json");
const LENGTH_REJECT: &[u8] = include_bytes!("fixtures/waveform-length-reject.v1.json");

#[test]
fn product_owned_fixture_round_trips_through_validated_core() {
    let waveform = parse_waveform_v1(VALID_WAVEFORM).expect("valid product fixture");
    let wire = WireWaveformV1::from(&waveform);

    assert_eq!(
        deterministic_json(&wire).unwrap(),
        br#"{"schema":"sipi.contract.v1","axis":{"encoding":"explicit","values":[0.0,1.0]},"samples":[1.0,2.0]}"#,
    );
}

#[test]
fn product_owned_negative_fixtures_fail_closed() {
    assert!(matches!(
        parse_waveform_v1(UNKNOWN_FIELD),
        Err(ContractError::Json(_))
    ));
    assert_eq!(
        parse_waveform_v1(VERSION_REJECT),
        Err(ContractError::Version)
    );
    assert!(matches!(
        parse_waveform_v1(LENGTH_REJECT),
        Err(ContractError::Type(_))
    ));
}

#[test]
fn product_catalog_has_no_implemented_domain() {
    assert!(
        CapabilityCatalogV1::unsupported()
            .capabilities
            .iter()
            .all(|capability| capability.status == "unsupported")
    );
}
