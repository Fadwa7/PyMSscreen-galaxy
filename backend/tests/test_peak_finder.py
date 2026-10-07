"""Step 8: backend uses the plot's peak finder; intensity checks use the chosen peak."""
import numpy as np
import pytest
import pandas as pd
import yaml

from app.routes.extract_prescreen_mspgen import _prescreen_impl, find_top_peaks

RT = np.round(np.linspace(0.005, 30, 3000), 4)


def gauss(center, height, width=0.08):
    return height * np.exp(-((RT - center) / width) ** 2)


def test_top_peaks_ordered_and_separated():
    trace = gauss(3.10, 6e4) + gauss(12.45, 1.5e4) + gauss(3.45, 1.1e4) + 100
    peaks = find_top_peaks(RT, trace)
    assert [p["rt"] for p in peaks] == pytest.approx([3.10, 12.45, 3.45], abs=0.02)


def test_one_scan_spike_is_not_chosen():
    trace = gauss(3.10, 6e4) + 100
    trace[np.argmin(abs(RT - 29.94))] = 2.4e5          # single-scan spike near run end
    peaks = find_top_peaks(RT, trace)
    assert abs(peaks[0]["rt"] - 3.10) < 0.02            # real peak is #1, not the spike


def test_no_peaks_in_empty_trace():
    assert find_top_peaks(RT, np.zeros_like(RT)) == []


def test_prescreen_uses_chosen_peak_intensity(tmp_path):
    (tmp_path / "ms2_spectra").mkdir()
    (tmp_path / "extract_config.yaml").write_text(yaml.safe_dump({
        "tolerance": {"ms1 fine": "10 ppm"},
        "prescreen": {"ms1_int_thresh": 1e5, "ms2_int_thresh": 1e3, "s2n": 3,
                      "ret_time_shift_tol": "0.5 min"}}))
    trace = gauss(3.10, 6e4) + 100
    trace[np.argmin(abs(RT - 29.94))] = 2.4e5            # spike above the 1e5 threshold
    pd.DataFrame({"rt": RT, "intensity": trace}).to_csv(
        tmp_path / "ms2_spectra" / "104_[M-H]-_WT-_EIC.csv", index=False)
    pd.DataFrame([dict(ID=104, mz=134.0448, adduct="[M-H]-", tag="WT-", Name="x")]).to_csv(
        tmp_path / "comprehensive_table.csv", index=False)

    assert _prescreen_impl(str(tmp_path))["status"] == "success"
    row = pd.read_csv(tmp_path / "summary_table.csv").iloc[0]
    assert abs(row["ms1_rt"] - 3.10) < 0.02            # real peak, not the spike
    assert row["qa_ms1_exists"]
    assert not row["qa_ms1_good_int"]                   # real peak (6e4) is below 1e5
