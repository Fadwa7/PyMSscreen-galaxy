"""QC score step 1: measured values in the summary table, also after a manual peak change."""
import numpy as np
import pandas as pd
import pytest
import yaml
from flask import Flask

from app.routes.extract_prescreen_mspgen import _prescreen_impl
from app.routes.data_routes import data_bp

RT = np.round(np.linspace(0.01, 15, 3000), 4)
EIC = 100 + 1e6 * np.exp(-((RT - 6.3) / 0.08) ** 2) + 5e4 * np.exp(-((RT - 9.0) / 0.08) ** 2)


def _setup(wd, eic=EIC, ms2_rts=(6.28, 6.33, 9.02)):
    spectra = wd / "ms2_spectra"
    spectra.mkdir()
    (wd / "extract_config.yaml").write_text(yaml.safe_dump({
        "tolerance": {"ms1 fine": "10 ppm"},
        "prescreen": {"ms1_int_thresh": 1e4, "ms2_int_thresh": 1e3, "s2n": 3,
                      "ret_time_shift_tol": "0.5 min"}}))
    pd.DataFrame({"rt": RT, "intensity": eic}).to_csv(spectra / "101_[M+H]+_WT+_EIC.csv", index=False)
    pd.DataFrame({"scan_id": [f"s{i}" for i in range(len(ms2_rts))], "ms2_rt": list(ms2_rts),
                  "ms2_intensity": 1.0, "peak_list": "70.0652:5000"}).to_csv(
        spectra / "101_[M+H]+_WT+_MS2.csv", index=False)
    pd.DataFrame([dict(ID=101, mz=116.0707, adduct="[M+H]+", tag="WT+", Name="x")]).to_csv(
        wd / "comprehensive_table.csv", index=False)
    assert _prescreen_impl(str(wd))["status"] == "success"
    return pd.read_csv(wd / "summary_table.csv").iloc[0]


def test_prescreen_writes_measured_values(tmp_path):
    row = _setup(tmp_path)
    assert row["ms1_rt"] == pytest.approx(6.3, abs=0.01)
    assert row["ms1_apex_intensity"] == pytest.approx(1e6, rel=0.01)
    assert row["ms1_sn"] == pytest.approx(row["ms1_apex_intensity"] / EIC.mean(), rel=1e-6)
    assert row["ms2_n_scans"] == 3
    assert row["ms2_n_near"] == 2                       # 6.28 and 6.33, not 9.02
    assert row["ms2_rt_delta"] == pytest.approx(row["ms2_rt"] - row["ms1_rt"])
    # existing columns keep their place at the front
    assert list(pd.read_csv(tmp_path / "summary_table.csv").columns[:16]) == [
        "ID", "Name", "adduct", "tag", "qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise",
        "qa_ms2_exists", "qa_ms2_good_int", "qa_ms2_near", "qa_pass", "alignment", "ms2_sel",
        "ms1_rt", "ms2_rt", "peak_list"]


def test_no_peak_gives_empty_values(tmp_path):
    row = _setup(tmp_path, eic=np.zeros_like(RT))
    assert pd.isna(row["ms1_apex_intensity"]) and pd.isna(row["ms1_sn"])
    assert row["ms2_n_scans"] == 3 and row["ms2_n_near"] == 0
    assert pd.isna(row["ms2_rt_delta"])


def test_manual_peak_change_updates_values(tmp_path, monkeypatch):
    _setup(tmp_path)
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    app = Flask(__name__)
    app.register_blueprint(data_bp)
    update = {"ID": 101, "adduct": "[M+H]+", "tag": "WT+", "MS1_RT": float(RT[np.argmin(abs(RT - 9.0))]),
              "MS1_Exists": True, "MS2_Exists": True, "MS1_Intensity": True, "S2N_ratio": True,
              "RT_Alignment": True}
    with app.test_client() as c:
        r = c.post("/save_qa_flags", json={"flags": {"101_[M+H]+_WT+": update}})
    assert r.status_code == 200
    row = pd.read_csv(tmp_path / "summary_table.csv").iloc[0]
    assert row["ms1_apex_intensity"] == pytest.approx(5e4, rel=0.02)
    assert row["ms1_sn"] == pytest.approx(row["ms1_apex_intensity"] / EIC.mean(), rel=1e-6)
    assert row["ms2_n_near"] == 1                       # only 9.02 near the new peak
    assert row["ms2_rt_delta"] == pytest.approx(9.02 - row["ms1_rt"])
