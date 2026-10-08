"""QC score bundle: MS2 consistency, score rules, and wiring into prescreen and manual saves."""
import numpy as np
import pandas as pd
import pytest
import yaml
from flask import Flask

from app.qc_score import score_row
from app.spectral_similarity import cosine_greedy, near_scan_consistency, parse_peak_list
from app.routes.extract_prescreen_mspgen import _prescreen_impl
from app.routes.data_routes import data_bp

OK = dict(qa_ms1_exists=True, qa_ms2_near=True, qa_ms1_good_int=True,
          qa_ms1_above_noise=True, ms2_consistency=0.95, qc_warnings="")


# ---------- MS2 similarity ----------
def test_cosine_identical_scaled_and_disjoint():
    a = parse_peak_list("70.0652:100;116.0706:40")
    b = parse_peak_list("70.0650:1000;116.0708:400")
    assert cosine_greedy(a, b) == pytest.approx(1.0)
    assert cosine_greedy(a, parse_peak_list("200.1:5;300.2:9")) == 0.0


def test_near_scan_consistency():
    ms2 = pd.DataFrame({"ms2_rt": [6.28, 6.33, 9.0],
                        "peak_list": ["70.0652:100;116.0706:40", "70.0651:90;116.0707:45", "200:1"]})
    cons, pairs = near_scan_consistency(ms2, 6.3, 0.5)
    assert pairs == 1 and cons > 0.99                   # only the two scans near 6.3
    assert near_scan_consistency(ms2, 9.0, 0.5) == (None, 0)   # a single scan


# ---------- score rules ----------
@pytest.mark.parametrize("change, score", [
    ({}, 5),
    ({"qa_ms1_above_noise": False}, 4),
    ({"ms2_consistency": 0.5}, 3),
    ({"qa_ms2_near": False}, 2),
    ({"qa_ms1_exists": False}, 1),
    ({"ms2_consistency": np.nan}, 5),                    # one MS2 scan: not assessed, no penalty
    ({"qc_warnings": "RT differs from STD- by 10.24 min"}, 2),
    ({"qc_warnings": "Same peak as 19 Isoleucine", "qa_ms1_exists": False}, 1),
    ({"qa_ms1_exists": "True", "qa_ms2_near": "False"}, 2),   # flags read from CSV as text
])
def test_score_rules(change, score):
    assert score_row({**OK, **change})[0] == score


def test_capped_note_mentions_warning():
    _, note = score_row({**OK, "qc_warnings": "RT differs from STD- by 10.24 min"})
    assert note.startswith("capped at 2: RT differs")


# ---------- wiring ----------
RT = np.round(np.linspace(0.01, 15, 3000), 4)


def _prescreen(wd):
    sp = wd / "ms2_spectra"
    sp.mkdir()
    (wd / "extract_config.yaml").write_text(yaml.safe_dump({
        "tolerance": {"ms1 fine": "10 ppm"},
        "prescreen": {"ms1_int_thresh": 1e4, "ms2_int_thresh": 1e3, "s2n": 3, "ret_time_shift_tol": "0.5 min"}}))
    eic = 100 + 1e6 * np.exp(-((RT - 6.3) / 0.08) ** 2)
    pd.DataFrame({"rt": RT, "intensity": eic}).to_csv(sp / "101_[M+H]+_WT+_EIC.csv", index=False)
    pd.DataFrame({"scan_id": ["a", "b"], "ms2_rt": [6.28, 6.33], "ms2_intensity": 1.0,
                  "peak_list": ["70.0652:5000;116.0706:2000", "70.0651:4800;116.0707:2100"]}).to_csv(
        sp / "101_[M+H]+_WT+_MS2.csv", index=False)
    pd.DataFrame([dict(ID=101, mz=116.0707, adduct="[M+H]+", tag="WT+", Name="Proline")]).to_csv(
        wd / "comprehensive_table.csv", index=False)
    assert _prescreen_impl(str(wd))["status"] == "success"
    return pd.read_csv(wd / "summary_table.csv").iloc[0]


def test_prescreen_writes_score(tmp_path):
    row = _prescreen(tmp_path)
    assert row["ms2_n_compared"] == 1 and row["ms2_consistency"] > 0.99
    assert row["qc_score"] == 5


def test_reviewer_tick_updates_score(tmp_path, monkeypatch):
    _prescreen(tmp_path)
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    app = Flask(__name__)
    app.register_blueprint(data_bp)
    flags = {"ID": 101, "adduct": "[M+H]+", "tag": "WT+", "MS1_Exists": True, "MS2_Exists": True,
             "MS1_Intensity": True, "S2N_ratio": True, "RT_Alignment": False}
    with app.test_client() as c:
        c.post("/save_qa_flags", json={"flags": {"101_[M+H]+_WT+": flags}})
    row = pd.read_csv(tmp_path / "summary_table.csv").iloc[0]
    assert row["qc_score"] == 2 and row["qc_score_note"] == "no MS2 near peak"
