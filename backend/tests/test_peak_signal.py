"""Peaks need signal in several scans; the marker sits at the peak's highest point."""
import numpy as np
import pandas as pd
import yaml

from app.routes.extract_prescreen_mspgen import _prescreen_impl, find_top_peaks

RT = np.round(np.linspace(0.01, 30, 1600), 4)          # ~1.1 s per scan, like the real data


def test_isolated_single_scans_are_not_peaks():
    trace = np.zeros_like(RT)
    trace[[450, 770]] = [7.6e3, 2.1e4]                  # like 22 [M+H]+ Outlet_1_pos
    assert find_top_peaks(RT, trace) == []


def test_narrow_real_peak_is_kept_and_marked_at_its_top():
    trace = np.zeros_like(RT)
    trace[125:131] = [2e5, 6e5, 1.27e6, 9e5, 4e5, 1e5]  # 6 scans, like inlet_1_pos at 2.37 min
    peaks = find_top_peaks(RT, trace)
    assert len(peaks) == 1
    assert peaks[0]["intensity"] == 1.27e6              # marker at the highest point, never at 0
    assert peaks[0]["rt"] == RT[127]


def test_spike_on_nonzero_background_is_not_chosen():
    trace = 100 + 6e4 * np.exp(-((RT - 3.1) / 0.08) ** 2)
    trace[np.argmin(abs(RT - 29.94))] = 2.4e5            # one-scan spike, higher than the peak
    peaks = find_top_peaks(RT, trace)
    assert abs(peaks[0]["rt"] - 3.1) < 0.03 and all(abs(p["rt"] - 29.94) > 0.1 for p in peaks)


def test_prescreen_reports_no_ms1_for_isolated_scan(tmp_path):
    (tmp_path / "ms2_spectra").mkdir()
    (tmp_path / "extract_config.yaml").write_text(yaml.safe_dump({
        "tolerance": {"ms1 fine": "10 ppm"},
        "prescreen": {"ms1_int_thresh": 1e3, "ms2_int_thresh": 1e3, "s2n": 3, "ret_time_shift_tol": "0.5 min"}}))
    trace = np.zeros_like(RT)
    trace[700] = 1.17e4                                   # like 22 [M-H]- inlet_1_neg
    pd.DataFrame({"rt": RT, "intensity": trace}).to_csv(
        tmp_path / "ms2_spectra" / "22_[M-H]-_inlet_1_neg_EIC.csv", index=False)
    pd.DataFrame([dict(ID=22, mz=159.0906, adduct="[M-H]-", tag="inlet_1_neg", Name="x")]).to_csv(
        tmp_path / "comprehensive_table.csv", index=False)
    assert _prescreen_impl(str(tmp_path))["status"] == "success"
    row = pd.read_csv(tmp_path / "summary_table.csv").iloc[0]
    assert not row["qa_ms1_exists"] and pd.isna(row["ms1_rt"]) and row["qc_score"] == 1
