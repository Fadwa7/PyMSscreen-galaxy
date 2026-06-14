"""
test_extraction.py
==================
Tests for _extract_data_impl from extract_prescreen_mspgen.py.

pyOpenMS is mocked entirely — no native libraries required.
The mock injects a minimal in-memory MSExperiment with controllable
MS1 and MS2 spectra so that every branch of the extraction logic
is exercised against real file I/O and real pandas/numpy code.

Run with:  pytest backend/tests/test_extraction.py -v
"""

import json
import os
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import yaml

from app.routes.extract_prescreen_mspgen import _extract_data_impl, build_feature_base


# ---------------------------------------------------------------------------
# Helpers – build the filesystem fixtures _extract_data_impl reads
# ---------------------------------------------------------------------------

def _write_config(tmp: str, fine_ppm: float = 5.0, coarse_da: float = 0.01) -> None:
    cfg = {
        "tolerance": {
            "ms1 coarse": f"{coarse_da} Da",
            "ms1 fine":   f"{fine_ppm} ppm",
            "eic":        "0.01 Da",
            "rt":         "0.5 min",
        },
        "prescreen": {
            "ms1_int_thresh":     1e5,
            "ms2_int_thresh":     1e3,
            "s2n":                3.0,
            "ret_time_shift_tol": "0.5 min",
        },
    }
    with open(os.path.join(tmp, "extract_config.yaml"), "w") as fh:
        yaml.dump(cfg, fh, default_flow_style=False)


def _write_state(tmp: str, mzml_filename: str, tag: str) -> None:
    state = {
        "working_directory": tmp,
        "compound_csv": os.path.join(tmp, "compounds.csv"),
        "mzml_files": [{"file": os.path.join(tmp, mzml_filename), "tag": tag}],
        "adducts": {"positive": ["[M+H]+"], "negative": []},
    }
    with open(os.path.join(tmp, "state.json"), "w") as fh:
        json.dump(state, fh)


def _write_compound_table(tmp: str, compound_id: int, mz: float,
                           adduct: str, tag: str, mzml_filename: str) -> None:
    df = pd.DataFrame([{
        "ID": compound_id, "Name": "TestCmpd",
        "mz": f"{mz:.6f}", "rt": "",
        "adduct": adduct, "tag": tag,
        "set": "test", "known": "structure",
        "SMILES": "C", "Formula": "CH4",
        "InChIKey": "", "file": mzml_filename,
    }])
    df.to_csv(os.path.join(tmp, "comprehensive_table.csv"), index=False)


# ---------------------------------------------------------------------------
# Mock spectrum factory
# ---------------------------------------------------------------------------

def _make_ms1_spectrum(rt_sec: float, mzs: list[float], ints: list[float]) -> MagicMock:
    sp = MagicMock()
    sp.getMSLevel.return_value = 1
    sp.getRT.return_value = rt_sec
    sp.get_peaks.return_value = (np.array(mzs), np.array(ints))
    return sp


def _make_ms2_spectrum(rt_sec: float, precursor_mz: float,
                        mzs: list[float], ints: list[float],
                        native_id: str = "scan=1") -> MagicMock:
    sp = MagicMock()
    sp.getMSLevel.return_value = 2
    sp.getRT.return_value = rt_sec
    sp.getNativeID.return_value = native_id
    prec = MagicMock()
    prec.getMZ.return_value = precursor_mz
    sp.getPrecursors.return_value = [prec]
    sp.get_peaks.return_value = (np.array(mzs), np.array(ints))
    return sp


def _make_experiment(spectra: list[MagicMock]) -> tuple[type, type]:
    """Return (MockMSExperiment class, MockMzMLFile class) that load the given spectra."""
    mock_exp = MagicMock()
    mock_exp.getSpectra.return_value = spectra

    MockMSExperiment = MagicMock(return_value=mock_exp)
    MockMzMLFile     = MagicMock()
    MockMzMLFile.return_value.load.return_value = None   # load() is a side-effect only

    return MockMSExperiment, MockMzMLFile


# ---------------------------------------------------------------------------
# Convenience: run extraction with a mocked pyOpenMS
# ---------------------------------------------------------------------------

def _run_extraction(tmp: str, spectra: list[MagicMock]) -> dict:
    MockMSExperiment, MockMzMLFile = _make_experiment(spectra)
    with patch(
        "app.routes.extract_prescreen_mspgen.load_pyopenms",
        return_value=(MockMSExperiment, MockMzMLFile),
    ):
        return _extract_data_impl(tmp)


# ===========================================================================
# Fixtures shared across tests
# ===========================================================================

TARGET_MZ  = 195.0877    # [M+H]+ of caffeine neutral mass 194.0803
ADDUCT     = "[M+H]+"
TAG        = "WT"
MZML_FILE  = "sample.mzML"
COMPOUND_ID = 1


@pytest.fixture()
def workspace(tmp_path):
    """Write the three config/state/table files every test needs."""
    tmp = str(tmp_path)
    _write_config(tmp, fine_ppm=5.0, coarse_da=0.01)
    _write_state(tmp, MZML_FILE, TAG)
    _write_compound_table(tmp, COMPOUND_ID, TARGET_MZ, ADDUCT, TAG, MZML_FILE)
    return tmp


# ===========================================================================
# 1.  Return value and status
# ===========================================================================

def test_extraction_returns_success(workspace):
    spectra = [_make_ms1_spectrum(60.0, [TARGET_MZ], [1e6])]
    result  = _run_extraction(workspace, spectra)
    assert result["status"] == "success"


def test_extraction_returns_error_list(workspace):
    spectra = [_make_ms1_spectrum(60.0, [TARGET_MZ], [1e6])]
    result  = _run_extraction(workspace, spectra)
    assert "errors" in result
    assert isinstance(result["errors"], list)


# ===========================================================================
# 2.  EIC output
# ===========================================================================

def test_eic_csv_is_created(workspace):
    spectra = [
        _make_ms1_spectrum(60.0,  [TARGET_MZ], [5e5]),
        _make_ms1_spectrum(120.0, [TARGET_MZ], [9e5]),
        _make_ms1_spectrum(180.0, [TARGET_MZ], [3e5]),
    ]
    _run_extraction(workspace, spectra)

    base     = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    eic_path = os.path.join(workspace, "ms2_spectra", f"{base}_EIC.csv")
    assert os.path.exists(eic_path), "EIC CSV not written"


def test_eic_csv_has_correct_columns(workspace):
    spectra = [_make_ms1_spectrum(60.0, [TARGET_MZ], [5e5])]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_EIC.csv"))
    assert set(df.columns) == {"rt", "intensity"}


def test_eic_rt_converted_to_minutes(workspace):
    spectra = [_make_ms1_spectrum(120.0, [TARGET_MZ], [5e5])]   # 120 s → 2.0 min
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_EIC.csv"))
    assert df["rt"].iloc[0] == pytest.approx(2.0)


def test_eic_row_count_matches_ms1_spectra(workspace):
    spectra = [
        _make_ms1_spectrum(t * 30.0, [TARGET_MZ], [1e5])
        for t in range(10)
    ]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_EIC.csv"))
    assert len(df) == 10


def test_eic_intensity_sums_within_ppm_window(workspace):
    """Only m/z values within the fine-ppm window contribute to the EIC intensity."""
    delta = TARGET_MZ * 5 / 1e6   # exactly 5 ppm
    in_window  = TARGET_MZ + delta * 0.9   # inside
    out_window = TARGET_MZ + delta * 1.1   # outside

    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ, in_window, out_window], [1e5, 2e5, 9e9]),
    ]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_EIC.csv"))
    # The 9e9 out-of-window ion must not appear
    assert df["intensity"].iloc[0] == pytest.approx(1e5 + 2e5, rel=1e-6)


def test_eic_zero_intensity_when_no_ms1_in_window(workspace):
    """If no MS1 peak falls within the ppm window the EIC intensity is 0."""
    far_mz = TARGET_MZ + 1.0   # 1 Da away — way outside 5 ppm
    spectra = [_make_ms1_spectrum(60.0, [far_mz], [9e9])]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_EIC.csv"))
    assert df["intensity"].iloc[0] == pytest.approx(0.0)


# ===========================================================================
# 3.  MS2 output
# ===========================================================================

def test_ms2_csv_created_when_precursor_matches(workspace):
    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ], [5e5]),
        _make_ms2_spectrum(65.0, TARGET_MZ, [100.0, 200.0], [3000.0, 8000.0]),
    ]
    _run_extraction(workspace, spectra)

    base     = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    ms2_path = os.path.join(workspace, "ms2_spectra", f"{base}_MS2.csv")
    assert os.path.exists(ms2_path)


def test_ms2_csv_has_correct_columns(workspace):
    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ], [5e5]),
        _make_ms2_spectrum(65.0, TARGET_MZ, [100.0], [5000.0]),
    ]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_MS2.csv"))
    assert {"scan_id", "ms2_rt", "ms2_intensity", "peak_list"}.issubset(df.columns)


def test_ms2_rt_converted_to_minutes(workspace):
    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ], [5e5]),
        _make_ms2_spectrum(90.0, TARGET_MZ, [100.0], [5000.0]),  # 90 s → 1.5 min
    ]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_MS2.csv"))
    assert df["ms2_rt"].iloc[0] == pytest.approx(1.5)


def test_ms2_peak_list_format(workspace):
    """peak_list must be semicolon-separated 'mz:intensity' pairs."""
    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ], [5e5]),
        _make_ms2_spectrum(65.0, TARGET_MZ, [100.0, 200.0], [3000.0, 8000.0]),
    ]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_MS2.csv"))
    peak_list = df["peak_list"].iloc[0]
    pairs = [p.split(":") for p in peak_list.split(";") if ":" in p]
    assert len(pairs) == 2
    assert float(pairs[0][0]) == pytest.approx(100.0, abs=0.01)
    assert float(pairs[1][1]) == pytest.approx(8000.0, abs=1)


def test_ms2_not_created_when_precursor_outside_coarse_window(workspace):
    """A precursor 1 Da away (>> 0.01 Da coarse window) must not be matched."""
    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ], [5e5]),
        _make_ms2_spectrum(65.0, TARGET_MZ + 1.0, [100.0], [5000.0]),
    ]
    _run_extraction(workspace, spectra)

    base     = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    ms2_path = os.path.join(workspace, "ms2_spectra", f"{base}_MS2.csv")
    assert not os.path.exists(ms2_path)


def test_ms2_multiple_matching_scans_all_written(workspace):
    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ], [5e5]),
        _make_ms2_spectrum(62.0, TARGET_MZ, [100.0], [2000.0], native_id="scan=1"),
        _make_ms2_spectrum(64.0, TARGET_MZ, [200.0], [4000.0], native_id="scan=2"),
        _make_ms2_spectrum(66.0, TARGET_MZ, [300.0], [6000.0], native_id="scan=3"),
    ]
    _run_extraction(workspace, spectra)

    base = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    df   = pd.read_csv(os.path.join(workspace, "ms2_spectra", f"{base}_MS2.csv"))
    assert len(df) == 3


# ===========================================================================
# 4.  Edge cases
# ===========================================================================

def test_extraction_empty_spectra_list(workspace):
    """No spectra at all → success, empty EIC (all zeros)."""
    result = _run_extraction(workspace, [])
    assert result["status"] == "success"


def test_extraction_only_ms2_spectra(workspace):
    """Only MS2 present → EIC is empty (no MS1), no MS2 file either
    (MS2 matching requires a precursor within the coarse window, which
    is still checked, but the EIC will be empty)."""
    spectra = [
        _make_ms2_spectrum(65.0, TARGET_MZ, [100.0], [5000.0]),
    ]
    result = _run_extraction(workspace, spectra)
    assert result["status"] == "success"

    base     = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    eic_path = os.path.join(workspace, "ms2_spectra", f"{base}_EIC.csv")
    # EIC is always written (even if all zeros)
    assert os.path.exists(eic_path)
    df = pd.read_csv(eic_path)
    assert df["intensity"].sum() == pytest.approx(0.0)


def test_extraction_get_peaks_error_recorded(workspace):
    """If get_peaks() raises, the error is captured in result['errors'],
    not propagated as an exception."""
    bad_sp = _make_ms1_spectrum(60.0, [], [])
    bad_sp.get_peaks.side_effect = RuntimeError("corrupt spectrum")

    result = _run_extraction(workspace, [bad_sp])
    assert result["status"] == "success"
    assert any("get_peaks" in e or "corrupt" in e for e in result["errors"])


def test_extraction_ms2_empty_peak_list_skipped(workspace):
    """MS2 spectrum with zero peaks must not be written to the CSV."""
    spectra = [
        _make_ms1_spectrum(60.0, [TARGET_MZ], [5e5]),
        _make_ms2_spectrum(65.0, TARGET_MZ, [], []),   # empty peaks
    ]
    _run_extraction(workspace, spectra)

    base     = build_feature_base(COMPOUND_ID, ADDUCT, TAG)
    ms2_path = os.path.join(workspace, "ms2_spectra", f"{base}_MS2.csv")
    assert not os.path.exists(ms2_path)


def test_extraction_spectra_dir_created(workspace):
    _run_extraction(workspace, [])
    assert os.path.isdir(os.path.join(workspace, "ms2_spectra"))


def test_extraction_missing_state_returns_error(tmp_path):
    """If state.json is absent, impl must return status='error', not raise."""
    tmp = str(tmp_path)
    _write_config(tmp)
    # No state.json, no comprehensive_table.csv written intentionally
    result = _run_extraction(tmp, [])
    assert result["status"] == "error"


def test_extraction_missing_config_returns_error(tmp_path):
    """If extract_config.yaml is absent, impl must return status='error'."""
    tmp = str(tmp_path)
    _write_state(tmp, MZML_FILE, TAG)
    _write_compound_table(tmp, COMPOUND_ID, TARGET_MZ, ADDUCT, TAG, MZML_FILE)
    # No config file
    result = _run_extraction(tmp, [])
    assert result["status"] == "error"
