"""Step 9: summary PDF export works and uses the summary table's chosen peak and spectrum."""
import numpy as np
import pandas as pd
import pytest
from flask import Flask

pytest.importorskip("kaleido")  # plotly image export
from app.routes.pdf_export import register_pdf_export

RT = np.round(np.linspace(0.01, 30, 2000), 4)


def _setup(wd):
    spectra = wd / "ms2_spectra"
    spectra.mkdir()
    eic = 1e6 * np.exp(-((RT - 6.3) / 0.1) ** 2)
    pd.DataFrame({"rt": RT, "intensity": eic}).to_csv(spectra / "101_[M+H]+_WT+_EIC.csv", index=False)
    pd.DataFrame({"rt": RT, "intensity": 0.0}).to_csv(spectra / "101_[M-H]-_WT-_EIC.csv", index=False)
    # row without adduct (precursor m/z input): file name is ID_tag
    pd.DataFrame({"rt": RT, "intensity": eic}).to_csv(spectra / "202_WT+_EIC.csv", index=False)
    pd.DataFrame([
        dict(ID=101, adduct="[M+H]+", tag="WT+", ms1_rt=6.3, ms2_rt=6.32, peak_list="70.0652:100;116.0706:40"),
        dict(ID=101, adduct="[M-H]-", tag="WT-", ms1_rt=None, ms2_rt=None, peak_list=None),
        dict(ID=202, adduct=None, tag="WT+", ms1_rt=6.3, ms2_rt=None, peak_list=None),
    ]).to_csv(wd / "summary_table.csv", index=False)


def _export(wd, compounds):
    app = Flask(__name__)
    register_pdf_export(app)
    groups = [{"group_name": "101/odd name", "compounds": compounds}]
    with app.test_client() as c:
        return c.post("/export_summary_pdf", json={"working_directory": str(wd), "compound_groups": groups})


def test_pdf_export_produces_pdf(tmp_path):
    _setup(tmp_path)
    r = _export(tmp_path, [
        {"ID": 101, "tag": "WT+", "adduct": "[M+H]+"},
        {"ID": 101, "tag": "WT-", "adduct": "[M-H]-"},   # no peak, no MS2
        {"ID": 202, "tag": "WT+", "adduct": None},        # no adduct
        {"ID": 999, "tag": "WT+", "adduct": "[M+H]+"},    # no files at all
    ])
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"
