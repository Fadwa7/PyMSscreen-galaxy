"""Step 5: manually selected MS1 peak updates RT, MS2 selection, qa_pass and library_all.msp."""
import pandas as pd
import yaml
from flask import Flask

from app.routes.data_routes import data_bp

FLAGS = {"MS1_Exists": True, "MS2_Exists": True, "MS1_Intensity": True,
         "S2N_ratio": True, "RT_Alignment": True}
KEY = "101_[M+H]+_WT+"
IDS = {"ID": 101, "adduct": "[M+H]+", "tag": "WT+"}


def _setup(wd):
    (wd / "ms2_spectra").mkdir()
    (wd / "extract_config.yaml").write_text(yaml.safe_dump(
        {"prescreen": {"ret_time_shift_tol": "0.5 min"}}))
    # MS2 scans: one near the automatic peak (6.30), one near the correct peak (9.10)
    pd.DataFrame({"scan_id": ["s1", "s2"], "ms2_rt": [6.30, 9.10], "ms2_intensity": [1, 1],
                  "peak_list": ["70.0652:100", "88.0400:200"]}).to_csv(
        wd / "ms2_spectra" / "101_[M+H]+_WT+_MS2.csv", index=False)
    summary = dict(ID=101, Name="Example", adduct="[M+H]+", tag="WT+",
                   qa_ms1_exists=True, qa_ms1_good_int=True, qa_ms1_above_noise=True,
                   qa_ms2_exists=True, qa_ms2_good_int=True, qa_ms2_near=True,
                   qa_pass=True, alignment=True, ms2_sel=True,
                   ms1_rt=6.28, ms2_rt=6.30, peak_list="70.0652:100")
    pd.DataFrame([summary]).to_csv(wd / "summary_table.csv", index=False)
    pd.DataFrame([dict(ID=101, mz=116.0707, rt=None, adduct="[M+H]+", tag="WT+", Name="Example",
                       SMILES=None, Formula=None, InChIKey=None, file="s.mzML")]).to_csv(
        wd / "comprehensive_table.csv", index=False)


def _save(wd, update):
    app = Flask(__name__)
    app.register_blueprint(data_bp)
    with app.test_client() as c:
        r = c.post("/save_qa_flags", json={"working_directory": str(wd), "flags": {KEY: update}})
    assert r.status_code == 200, r.get_json()
    row = pd.read_csv(wd / "summary_table.csv").iloc[0]
    msp = (wd / "spectral_library" / "library_all.msp").read_text()
    return r.get_json(), row, msp


def test_select_other_peak_with_ms2(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _setup(tmp_path)
    res, row, msp = _save(tmp_path, {**FLAGS, **IDS, "MS1_RT": 9.12})
    assert row["ms1_rt"] == 9.12
    assert row["ms2_rt"] == 9.10 and row["peak_list"] == "88.0400:200"
    assert bool(row["qa_ms2_near"]) and bool(row["qa_pass"]) and bool(row["manual_peak"])
    assert res["no_ms2_near_peak"] == [] and res["msp_entries"] == 1
    assert "RT: 9.12" in msp and "88.0400 200" in msp


def test_select_peak_without_ms2(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _setup(tmp_path)
    res, row, msp = _save(tmp_path, {**FLAGS, **IDS, "MS1_RT": 12.0})
    assert row["ms1_rt"] == 12.0
    assert not bool(row["qa_ms2_near"]) and not bool(row["qa_pass"])
    assert pd.isna(row["peak_list"])
    assert res["no_ms2_near_peak"] == [KEY]
    assert res["msp_entries"] == 0 and "NAME:" not in msp      # removed from the library


def test_no_peak_change_keeps_peak(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _setup(tmp_path)
    res, row, msp = _save(tmp_path, {**FLAGS, **IDS})
    assert row["ms1_rt"] == 6.28 and row["peak_list"] == "70.0652:100"
    assert "manual_peak" not in row.index
    assert res["msp_entries"] == 1 and "RT: 6.28" in msp


def test_flag_change_updates_library(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _setup(tmp_path)
    _, row, msp = _save(tmp_path, {**FLAGS, **IDS, "MS1_Exists": False})
    assert not bool(row["qa_pass"])
    assert "NAME:" not in msp
