"""QC score step 2: cross-checks between rows (RT agreement between tags, shared peaks)."""
import numpy as np
import pandas as pd
import yaml
from flask import Flask

from app.routes.extract_prescreen_mspgen import add_cross_checks
from app.routes.data_routes import data_bp


def _summary(rows):
    return pd.DataFrame([dict(ID=i, Name=n, adduct=a, tag=t, ms1_rt=rt) for i, n, a, t, rt in rows])


def _comp(rows):
    return pd.DataFrame([dict(ID=i, adduct=a, tag=t, mz=mz) for i, a, t, mz in rows])


def test_rt_disagreement_between_tags():
    s = _summary([(12, "Cysteine", "[M-H]-", "STD-", 12.01), (12, "Cysteine", "[M+H]+", "STD+", 1.77),
                  (2, "Serine", "[M-H]-", "STD-", 11.16), (2, "Serine", "[M+H]+", "STD+", 11.17)])
    c = _comp([(12, "[M-H]-", "STD-", 120.0125), (12, "[M+H]+", "STD+", 122.0270),
               (2, "[M-H]-", "STD-", 104.0353), (2, "[M+H]+", "STD+", 106.0499)])
    out = add_cross_checks(s, c, rt_tol=0.5, ppm_tol=10).set_index(["ID", "tag"])
    assert out.loc[(12, "STD+"), "qc_warnings"] == "RT differs from STD- by 10.24 min"
    assert out.loc[(12, "STD-"), "rt_diff_other_tags"] > 10
    assert out.loc[(2, "STD+"), "qc_warnings"] == ""            # agrees within 0.01 min


def test_isomers_share_a_peak():
    s = _summary([(5, "Leucine", "[M+H]+", "STD+", 4.3042), (19, "Isoleucine", "[M+H]+", "STD+", 4.3042),
                  (20, "Methionine", "[M+H]+", "STD+", 4.3042)])        # same RT, other m/z
    c = _comp([(5, "[M+H]+", "STD+", 132.1019), (19, "[M+H]+", "STD+", 132.1019),
               (20, "[M+H]+", "STD+", 150.0583)])
    out = add_cross_checks(s, c, rt_tol=0.5, ppm_tol=10).set_index("ID")
    assert out.loc[5, "shared_peak_with"] == "19 Isoleucine"
    assert out.loc[19, "qc_warnings"] == "Same peak as 5 Leucine"
    assert out.loc[20, "qc_warnings"] == ""                     # same RT but different m/z


def test_missing_peaks_are_ignored():
    s = _summary([(1, "A", "[M+H]+", "T+", np.nan), (1, "A", "[M-H]-", "T-", 5.0)])
    c = _comp([(1, "[M+H]+", "T+", 100.0), (1, "[M-H]-", "T-", 98.0)])
    out = add_cross_checks(s, c, rt_tol=0.5, ppm_tol=10)
    assert out["rt_diff_other_tags"].isna().all()
    assert (out["qc_warnings"] == "").all()


def test_manual_peak_change_refreshes_warnings(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    (tmp_path / "extract_config.yaml").write_text(yaml.safe_dump({
        "tolerance": {"ms1 fine": "10 ppm"}, "prescreen": {"ret_time_shift_tol": "0.5 min"}}))
    s = _summary([(12, "Cysteine", "[M-H]-", "STD-", 12.01), (12, "Cysteine", "[M+H]+", "STD+", 1.77)])
    for col in ["qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise", "qa_ms2_exists",
                "qa_ms2_good_int", "qa_ms2_near", "qa_pass", "alignment", "ms2_sel"]:
        s[col] = True
    s["ms2_rt"], s["peak_list"] = np.nan, np.nan
    c = _comp([(12, "[M-H]-", "STD-", 120.0125), (12, "[M+H]+", "STD+", 122.0270)])
    add_cross_checks(s, c, 0.5, 10).to_csv(tmp_path / "summary_table.csv", index=False)
    c.to_csv(tmp_path / "comprehensive_table.csv", index=False)

    app = Flask(__name__)
    app.register_blueprint(data_bp)
    with app.test_client() as cl:                                # reviewer picks the peak at 12.04
        cl.post("/save_qa_flags", json={"flags": {"12_[M+H]+_STD+": {
            "ID": 12, "adduct": "[M+H]+", "tag": "STD+", "MS1_RT": 12.04}}})
    out = pd.read_csv(tmp_path / "summary_table.csv").fillna({"qc_warnings": ""})
    assert (out["qc_warnings"] == "").all()                      # RTs now agree
