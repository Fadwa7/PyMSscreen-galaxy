"""Step 11: RT Align counts for qa_pass; a new peak recalculates the measured MS1 flags."""
import numpy as np
import pandas as pd
import yaml
from flask import Flask

from app.routes.data_routes import data_bp

KEY = "101_[M+H]+_WT+"
IDS = {"ID": 101, "adduct": "[M+H]+", "tag": "WT+"}
TICKS = {"MS1_Exists": True, "MS2_Exists": True, "MS1_Intensity": True,
         "S2N_ratio": True, "RT_Alignment": True}


def _setup(wd):
    (wd / "ms2_spectra").mkdir()
    (wd / "extract_config.yaml").write_text(yaml.safe_dump({"prescreen": {
        "ms1_int_thresh": 1e4, "ms2_int_thresh": 1e3, "s2n": 3, "ret_time_shift_tol": "0.5 min"}}))
    rt = np.round(np.linspace(0.01, 15, 3000), 4)
    eic = 100 + 1e6 * np.exp(-((rt - 6.3) / 0.08) ** 2) + 5e3 * np.exp(-((rt - 9.1) / 0.08) ** 2)
    pd.DataFrame({"rt": rt, "intensity": eic}).to_csv(wd / "ms2_spectra" / "101_[M+H]+_WT+_EIC.csv", index=False)
    pd.DataFrame({"scan_id": ["s1", "s2"], "ms2_rt": [6.30, 9.10], "ms2_intensity": [1, 1],
                  "peak_list": ["70.0652:5000", "88.0400:5000"]}).to_csv(
        wd / "ms2_spectra" / "101_[M+H]+_WT+_MS2.csv", index=False)
    pd.DataFrame([dict(ID=101, Name="x", adduct="[M+H]+", tag="WT+",
                       qa_ms1_exists=True, qa_ms1_good_int=True, qa_ms1_above_noise=True,
                       qa_ms2_exists=True, qa_ms2_good_int=True, qa_ms2_near=True,
                       qa_pass=True, alignment=True, ms2_sel=True,
                       ms1_rt=6.30, ms2_rt=6.30, peak_list="70.0652:5000")]).to_csv(
        wd / "summary_table.csv", index=False)


def _save(wd, update):
    app = Flask(__name__)
    app.register_blueprint(data_bp)
    with app.test_client() as c:
        r = c.post("/save_qa_flags", json={"working_directory": "ignored", "flags": {KEY: {**IDS, **update}}})
    assert r.status_code == 200, r.get_json()
    return r.get_json(), pd.read_csv(wd / "summary_table.csv").iloc[0]


def test_rt_align_counts_for_qa_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _setup(tmp_path)
    _, row = _save(tmp_path, {**TICKS, "RT_Alignment": False})
    assert not row["qa_ms2_near"] and not row["alignment"]
    assert not row["qa_pass"]
    _, row = _save(tmp_path, TICKS)                      # tick it again
    assert row["qa_ms2_near"] and row["qa_pass"]


def test_new_peak_recalculates_then_reviewer_can_override(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _setup(tmp_path)
    # small peak at 9.1 (5e3, below the 1e4 threshold); old ticks still say True
    res, row = _save(tmp_path, {**TICKS, "MS1_RT": 9.10})
    assert res["recalculated"] == [KEY]
    assert row["ms1_rt"] == 9.10 and row["ms2_rt"] == 9.10
    assert not row["qa_ms1_good_int"]                    # recalculated, old tick ignored
    assert not row["qa_ms1_above_noise"]                 # 5e3 < 3 x trace mean (~2.8e4)
    assert row["qa_ms2_near"] and row["alignment"]
    assert not row["qa_pass"]

    # reviewer overrides in a second save (no peak change)
    res, row = _save(tmp_path, {**TICKS, "MS1_RT": 9.10})
    assert res["recalculated"] == []                     # same peak -> nothing recalculated
    assert row["qa_ms1_good_int"] and row["qa_ms1_above_noise"] and row["qa_pass"]
