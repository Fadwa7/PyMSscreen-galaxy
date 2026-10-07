"""Step 7: traces without a peak get no MS1 RT and MS1 Exists = False."""
import numpy as np
import pandas as pd
import yaml

from app.routes.extract_prescreen_mspgen import _prescreen_impl

RT = np.round(np.linspace(0.005, 30, 3000), 4)
TRACES = {
    "1": np.zeros_like(RT),                                        # no signal at all
    "2": 1e6 * np.exp(-((RT - 6.29) / 0.15) ** 2) + 1e3,           # real peak
    "3": 1e6 * np.exp(-((RT - 0.45) / 0.05) ** 2) + 1e3,           # real early peak
    "4": np.linspace(1e5, 0, RT.size),                             # only falls, no peak
}


def _run(wd):
    (wd / "ms2_spectra").mkdir()
    (wd / "extract_config.yaml").write_text(yaml.safe_dump({
        "tolerance": {"ms1 fine": "10 ppm"},
        "prescreen": {"ms1_int_thresh": 1e4, "ms2_int_thresh": 1e3, "s2n": 3,
                      "ret_time_shift_tol": "0.5 min"}}))
    rows = []
    for ID, inten in TRACES.items():
        pd.DataFrame({"rt": RT, "intensity": inten}).to_csv(
            wd / "ms2_spectra" / f"{ID}_[M+H]+_WT+_EIC.csv", index=False)
        rows.append(dict(ID=int(ID), mz=100.0, adduct="[M+H]+", tag="WT+", Name="x"))
    pd.DataFrame(rows).to_csv(wd / "comprehensive_table.csv", index=False)
    assert _prescreen_impl(str(wd))["status"] == "success"
    return pd.read_csv(wd / "summary_table.csv").set_index("ID")


def test_peaks_found_only_where_they_exist(tmp_path):
    s = _run(tmp_path)
    for ID in (1, 4):                                   # no peak -> nothing invented
        assert not s.loc[ID, "qa_ms1_exists"]
        assert pd.isna(s.loc[ID, "ms1_rt"])
        assert not s.loc[ID, "qa_pass"]
    assert s.loc[2, "qa_ms1_exists"] and abs(s.loc[2, "ms1_rt"] - 6.29) < 0.02
    assert s.loc[3, "qa_ms1_exists"] and abs(s.loc[3, "ms1_rt"] - 0.45) < 0.02   # early eluter kept
