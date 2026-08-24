//! External-only search-loop support cross-check runner (P5-04t).
//!
//! Exercises the private support helpers (rectangular_pulse_response,
//! peak_window, shift_matrix, sample offsets, skip-local-search, anchored
//! cursor, validate) on JSON inputs and reports the results. Ignored by
//! default; external-custody tooling only.

use std::path::PathBuf;

use serde_json::Value;
use sipi_com::{
    SEARCH_LOOP_POLICY_V1, SearchLoopOptionsV1, anchored_cursor, peak_window, r480_sample_offsets,
    rectangular_pulse_response_v1, shift_matrix, skip_high_pass_local_search, skip_local_search,
    validate_supported_branch,
};

fn f64s(value: &Value) -> Vec<f64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|i| i.as_f64().expect("f64"))
        .collect()
}
fn i64s(value: &Value) -> Vec<i64> {
    value
        .as_array()
        .expect("array")
        .iter()
        .map(|i| i.as_i64().expect("i64"))
        .collect()
}

fn search_case(value: &Value) -> serde_json::Value {
    use sipi_com::{
        CandidateEvalOptionsV1, CandidateEvalParamsV1, CtleParamsV1, ReceiverNoiseOptionsV1,
        ReceiverNoiseParamsV1, SearchFullOptionsV1, SearchFullParamsV1, XtalkChannelV1,
        search_r480_nonmmse_no_xtalk_v1,
    };
    let c = &value["search"];
    let p = &c["full_params"];
    let rn = &p["receiver_noise"];
    let ct = &p["ctle"];
    let cand = &p["candidate"];
    let o = &c["full_options"];
    let cand_opts = &o["candidate"];
    let rn_opts = &o["receiver"];
    let receiver_params = ReceiverNoiseParamsV1 {
        fb: rn["fb"].as_f64().expect("fb"),
        btorder: rn["btorder"].as_u64().expect("bt") as usize,
        fb_bt_cutoff: rn["fb_bt_cutoff"].as_f64().expect("fbt"),
        fb_bw_cutoff: rn["fb_bw_cutoff"].as_f64().expect("fbw"),
        rc_start: rn["rc_start"].as_f64().expect("rcs"),
        rc_end: rn["rc_end"].as_f64().expect("rce"),
        eta_0: rn["eta_0"].as_f64().expect("eta"),
        accm_max_freq: rn["accm_max_freq"].as_f64().expect("accm"),
        ac_cm_rms: f64s(&rn["ac_cm_rms"]),
        ctle_gdc_values: f64s(&rn["ctle_gdc_values"]),
        ctle_fz: f64s(&rn["ctle_fz"]),
        ctle_fp1: f64s(&rn["ctle_fp1"]),
        ctle_fp2: f64s(&rn["ctle_fp2"]),
        ctle_type: rn["ctle_type"].as_str().expect("rct").to_string(),
        f_hp: f64s(&rn["f_hp"]),
        f_hp_z: f64s(&rn["f_hp_z"]),
        f_hp_p: f64s(&rn["f_hp_p"]),
    };
    let ctle = CtleParamsV1 {
        ctle_gdc_values: f64s(&ct["ctle_gdc_values"]),
        ctle_fz: f64s(&ct["ctle_fz"]),
        ctle_fp1: f64s(&ct["ctle_fp1"]),
        ctle_fp2: f64s(&ct["ctle_fp2"]),
        ctle_type: ct["ctle_type"].as_str().expect("ct").to_string(),
        f_hp: f64s(&ct["f_hp"]),
        f_hp_z: f64s(&ct["f_hp_z"]),
        f_hp_p: f64s(&ct["f_hp_p"]),
    };
    let candidate = CandidateEvalParamsV1 {
        samples_per_ui: cand["samples_per_ui"].as_u64().expect("cspu") as usize,
        r_lm: cand["r_lm"].as_f64().expect("clm"),
        levels: cand["levels"].as_u64().expect("clv") as usize,
        sigma_x: cand["sigma_x"].as_f64().expect("csx"),
        dfe_delta: cand["dfe_delta"].as_f64().expect("cdf"),
        n_tail_start: cand["n_tail_start"].as_i64().expect("cnts"),
        b_float_rss_max: cand["b_float_rss_max"].as_f64().expect("cbrss"),
        a_dd: cand["a_dd"].as_f64().expect("cadd"),
        sigma_rj: cand["sigma_rj"].as_f64().expect("csrj"),
        t_o: cand["t_o"].as_f64().expect("cto"),
        min_veo_test: cand["min_veo_test"].as_f64().expect("cmvt"),
        noise_crest_factor: cand["noise_crest_factor"].as_f64().expect("cncf"),
        spec_ber: cand["spec_ber"].as_f64().expect("csb"),
        samples_for_c2m: cand["samples_for_c2m"].as_u64().expect("csfc") as usize,
        ql: cand["ql"].as_f64().expect("cql"),
        floating_dfe: cand["floating_dfe"].as_bool().expect("cfd"),
        ndfe: cand["ndfe"].as_i64().expect("cnd"),
        n_bmax: cand["n_bmax"].as_i64().expect("cnbmax"),
        n_bf: cand["n_bf"].as_i64().expect("cnbf"),
        n_bg: cand["n_bg"].as_i64().expect("cnbg"),
        bmaxg: cand["bmaxg"].as_f64().expect("cbmaxg"),
        bmax: f64s(&cand["bmax"]),
        bmin: f64s(&cand["bmin"]),
    };
    let candidate_opts = CandidateEvalOptionsV1 {
        snr_txw_c0: cand_opts["snr_txw_c0"].as_bool().expect("st0"),
        wc_portz: cand_opts["wc_portz"].as_bool().expect("wcp"),
        tx_rd_sel: cand_opts["tx_rd_sel"].as_i64().expect("trs"),
        pkg_len_select: i64s(&cand_opts["pkg_len_select"]),
        sndr: f64s(&cand_opts["sndr"]),
        limit_jitter_contrib_to_dfe_span: cand_opts["limit_jitter_contrib_to_dfe_span"]
            .as_bool()
            .expect("lj"),
        force_pdf_bin_size: cand_opts["force_pdf_bin_size"].as_bool().expect("fps"),
        bin_size: cand_opts["bin_size"].as_f64().expect("bs"),
        force_bbn_q_factor: cand_opts["force_bbn_q_factor"].as_bool().expect("fbq"),
        bbn_q_factor: cand_opts["bbn_q_factor"].as_f64().expect("bq"),
        histogram_window_weight: cand_opts["histogram_window_weight"]
            .as_str()
            .expect("hww")
            .to_string(),
    };
    let receiver_opts = ReceiverNoiseOptionsV1 {
        bessel_thomson: rn_opts["bessel_thomson"].as_bool().expect("bt"),
        butterworth: rn_opts["butterworth"].as_bool().expect("bw"),
        raised_cosine: rn_opts["raised_cosine"].as_bool().expect("rc"),
        use_eta0_psd: rn_opts["use_eta0_psd"].as_bool().expect("eta0"),
        wc_portz: rn_opts["wc_portz"].as_bool().expect("wcp"),
        pkg_len_select: i64s(&rn_opts["pkg_len_select"]),
    };
    let mut tx_ffe_values = std::collections::BTreeMap::new();
    if let Some(obj) = p["tx_ffe_values"].as_object() {
        for (name, arr) in obj {
            let vals: Vec<f64> = arr
                .as_array()
                .expect("arr")
                .iter()
                .map(|v| v.as_f64().expect("f"))
                .collect();
            tx_ffe_values.insert(name.clone(), vals);
        }
    }
    let full_params = SearchFullParamsV1 {
        samples_per_ui: p["samples_per_ui"].as_u64().expect("spu") as usize,
        fb: p["fb"].as_f64().expect("fb"),
        f2: p
            .get("f2")
            .and_then(Value::as_f64)
            .unwrap_or_else(|| p["fb"].as_f64().expect("fb")),
        tx_ffe_values,
        tx_ffe_c0_min: p["tx_ffe_c0_min"].as_f64().expect("c0"),
        ts_anchor: p["ts_anchor"].as_i64().expect("tsa"),
        local_search: p["local_search"].as_f64().expect("ls"),
        ts_sample_adj_range: i64s(&p["ts_sample_adj_range"]),
        include_ctle: p["include_ctle"].as_bool().expect("ict"),
        gdc_min: p["gdc_min"].as_f64().expect("gdc"),
        gqual: p["gqual"]
            .as_array()
            .expect("gq")
            .iter()
            .map(f64s)
            .collect(),
        g2qual: f64s(&p["g2qual"]),
        dfe_first_max: p["dfe_first_max"].as_f64().expect("dfm"),
        receiver_noise: receiver_params,
        ctle,
        candidate,
    };
    let full_options = SearchFullOptionsV1 {
        ffe_opt_method: o["ffe_opt_method"].as_str().expect("fom").to_string(),
        rx_ffe_enabled: o["rx_ffe_enabled"].as_bool().expect("rx"),
        ts_srch_mode: o["ts_srch_mode"].as_str().expect("tsm").to_string(),
        cdr: o["cdr"].as_str().expect("cdr").to_string(),
        receiver: receiver_opts,
        candidate: candidate_opts,
    };
    let impulse = f64s(&c["impulse"]);
    let freq = f64s(&c["frequency_hz"]);
    let noise_freq = f64s(&c["noise_frequency_hz"]);
    let xt_freq = f64s(&c["crosstalk_frequency_hz"]);
    let crosstalk: Vec<XtalkChannelV1> = Vec::new();
    let result = search_r480_nonmmse_no_xtalk_v1(
        &impulse,
        &freq,
        &noise_freq,
        &xt_freq,
        &crosstalk,
        |_, _, _| 0.0,
        None,
        false,
        &[],
        0,
        &full_params,
        &full_options,
    );
    match result {
        Ok(res) => {
            serde_json::json!({ "ok": true, "fom_db": res.fom_db, "ctle_index": res.ctle_index,
            "high_pass_index": res.high_pass_index, "tx_grid_index": res.tx_grid_index,
            "cursor_index": res.cursor_index, "sigma_tx_v": res.sigma_tx_v })
        }
        Err(err) => serde_json::json!({ "ok": false, "error": format!("{err:?}") }),
    }
}

fn main() {
    let mut input = None;
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--input" => input = Some(PathBuf::from(value())),
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(input) = input else {
        println!("usage: p5_04t_search_loop_runner --input <json> [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&input).expect("read input");
    let value: Value = serde_json::from_slice(&bytes).expect("input json");
    let mut output = serde_json::json!({ "policy": SEARCH_LOOP_POLICY_V1 });
    if let Some(case) = value.get("rectangular") {
        let out = rectangular_pulse_response_v1(
            &f64s(&case["impulse"]),
            case["samples_per_ui"].as_u64().expect("spu") as usize,
        )
        .expect("rect");
        output["rectangular"] = serde_json::json!(out);
    }
    if let Some(case) = value.get("peak_window") {
        let (start, stop) = peak_window(
            &f64s(&case["response"]),
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            case["is_pulse"].as_bool().expect("isp"),
        )
        .expect("peak");
        output["peak_window"] = serde_json::json!({ "start": start, "stop": stop });
    }
    if let Some(case) = value.get("shift_matrix") {
        let m = shift_matrix(
            &f64s(&case["pulse"]),
            case["precursor_count"].as_u64().expect("pc") as usize,
            case["samples_per_ui"].as_u64().expect("spu") as usize,
            case["tap_count"].as_u64().expect("tc") as usize,
        );
        output["shift_matrix"] = serde_json::json!(m);
    }
    if let Some(case) = value.get("sample_offsets") {
        let v = r480_sample_offsets(&i64s(&case["range"]), case["mode"].as_str().expect("mode"))
            .expect("offsets");
        output["sample_offsets"] = serde_json::json!(v);
    }
    if let Some(case) = value.get("skip_local") {
        let best = case["best"].as_array().map(|b| {
            b.iter()
                .map(|i| i.as_i64().expect("i64"))
                .collect::<Vec<i64>>()
        });
        let sweep = i64s(&case["sweep"])
            .into_iter()
            .map(|v| v as usize)
            .collect::<Vec<usize>>();
        let skip = skip_local_search(
            &i64s(&case["current"]),
            best.as_deref(),
            &sweep,
            case["local_search"].as_f64().expect("ls"),
        );
        output["skip_local"] = serde_json::json!(skip);
    }
    if let Some(case) = value.get("skip_hp") {
        let skip = skip_high_pass_local_search(
            case["ctle_index"].as_u64().expect("ci") as usize,
            case["high_pass_index"].as_i64().expect("hpi"),
            case["best_high_pass_index"].as_i64(),
            case["local_search"].as_f64().expect("ls"),
        );
        output["skip_hp"] = serde_json::json!(skip);
    }
    if let Some(case) = value.get("anchored") {
        let c = anchored_cursor(
            case["cursor"].as_i64().expect("cur"),
            case["peak"].as_i64().expect("peak"),
            case["ts_anchor"].as_i64().expect("anchor"),
            &f64s(&case["sbr"]),
            case["samples_per_ui"].as_u64().expect("spu") as usize,
        );
        output["anchored"] = match c {
            Ok(index) => serde_json::json!({ "ok": true, "index": index }),
            Err(_) => serde_json::json!({ "ok": false, "error": "anchor" }),
        };
    }
    if let Some(case) = value.get("validate") {
        let opts = SearchLoopOptionsV1 {
            ffe_opt_method: case["ffe_opt_method"].as_str().expect("method").to_string(),
            rxffe: case["rxffe"].as_bool().expect("rxffe"),
            cdr: "MM".to_string(),
            ts_srch_mode: "full-sweep".to_string(),
            include_ctle: true,
            local_search_enabled: false,
        };
        output["validate"] = serde_json::json!(validate_supported_branch(&opts).is_ok());
        eprintln!("DBG has_search={}", value.get("search").is_some());
        if value.get("search").is_some() {
            output["search"] = search_case(&value);
        }
    }
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string(&output).expect("json")).expect("write");
    } else {
        println!("{}", serde_json::to_string(&output).expect("json"));
    }
}
