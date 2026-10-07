"""Step 4: manual QA flags are saved for all rows, or a missing row is reported."""
import pandas as pd
from flask import Flask

from app.routes.data_routes import data_bp

FLAG_COLS = ["qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise",
             "qa_ms2_exists", "qa_ms2_good_int", "qa_ms2_near", "qa_pass", "alignment", "ms2_sel"]


def _summary(wd):
    rows = []
    for ID, adduct, tag in [("101", "[M+H]+", "WT+"), ("CMP_001", "[M+H]+", "WT+"), ("202", None, "WT-")]:
        row = dict(ID=ID, Name="x", adduct=adduct, tag=tag)
        row.update({c: True for c in FLAG_COLS})
        row["qa_ms1_exists"] = False
        row["qa_pass"] = False
        rows.append(row)
    pd.DataFrame(rows).to_csv(wd / "summary_table.csv", index=False)


def _save(wd, flags):
    app = Flask(__name__)
    app.register_blueprint(data_bp)
    with app.test_client() as c:
        r = c.post("/save_qa_flags", json={"working_directory": str(wd), "flags": flags})
    assert r.status_code == 200
    return r.get_json(), pd.read_csv(wd / "summary_table.csv", dtype={"ID": str})


def _row(df, ID):
    return df[df["ID"] == ID].iloc[0]


def test_old_key_format_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _summary(tmp_path)
    res, df = _save(tmp_path, {"101_[M+H]+_WT+": {"MS1_Exists": True}})
    assert res["updated_rows"] == 1 and res["not_found"] == []
    assert bool(_row(df, "101")["qa_ms1_exists"]) and bool(_row(df, "101")["qa_pass"])


def test_id_with_underscore(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _summary(tmp_path)
    res, df = _save(tmp_path, {"CMP_001_[M+H]+_WT+": {
        "MS1_Exists": True, "ID": "CMP_001", "adduct": "[M+H]+", "tag": "WT+"}})
    assert res["updated_rows"] == 1
    assert bool(_row(df, "CMP_001")["qa_ms1_exists"])
    assert not bool(_row(df, "101")["qa_ms1_exists"])          # other rows untouched


def test_row_without_adduct(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _summary(tmp_path)
    res, df = _save(tmp_path, {"202_null_WT-": {
        "MS1_Exists": True, "ID": "202", "adduct": None, "tag": "WT-"}})
    assert res["updated_rows"] == 1
    assert bool(_row(df, "202")["qa_ms1_exists"])


def test_missing_row_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    _summary(tmp_path)
    res, _ = _save(tmp_path, {"999_[M+H]+_WT+": {
        "MS1_Exists": True, "ID": "999", "adduct": "[M+H]+", "tag": "WT+"}})
    assert res["updated_rows"] == 0
    assert res["not_found"] == ["999_[M+H]+_WT+"]
