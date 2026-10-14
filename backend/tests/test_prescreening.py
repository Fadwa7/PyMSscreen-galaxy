"""
test_prescreening.py
====================
Tests for _prescreen_impl from extract_prescreen_mspgen.py.

_prescreen_impl is called directly with no mocking — it runs against a
real temporary filesystem populated with synthetic EIC and MS2 CSV files
that mirror what _extract_data_impl produces. Each test isolates one QA
flag so failures are unambiguous.

QA flags tested
---------------
qa_ms1_exists        — an MS1 peak was found in the EIC (at least 3 scans above
                       10% of its height; isolated single scans are not peaks)
qa_ms1_good_int      — height of the chosen peak > ms1_int_thresh
qa_ms1_above_noise   — height of the chosen peak > mean of the EIC * s2n
qa_ms2_exists        — MS2 file present and non-empty
qa_ms2_good_int      — at least one MS2 fragment above ms2_int_thresh
qa_ms2_near          — closest MS2 scan within ret_time_shift_tol of MS1 peak
qa_pass              — all six flags True simultaneously

Run with:  pytest backend/tests/test_prescreening.py -v
"""

import os

import pandas as pd
import pytest
import yaml

from app.routes.extract_prescreen_mspgen import _prescreen_impl, build_feature_base


# ===========================================================================
# Filesystem fixture helpers
# ===========================================================================

def _write_extract_config(tmp: str, ms1_intensity_threshold: float = 1e5,
                           ms2_intensity_threshold: float = 1e3,
                           ms1_sn_ratio: float = 3.0,
                           retention_time_delay: float = 0.5) -> None:
    """
    Write extract_config.yaml matching the structure written by
    state_routes.save_extract_config and read by _prescreen_impl.
    """
    cfg = {
        "tolerance": {
            "ms1 coarse": "0.01 Da",
            "ms1 fine":   "5 ppm",
            "eic":        "0.01 Da",
            "rt":         "0.5 min",
        },
        "prescreen": {
            "ms1_int_thresh":     float(ms1_intensity_threshold),
            "ms2_int_thresh":     float(ms2_intensity_threshold),
            "s2n":                float(ms1_sn_ratio),
            "ret_time_shift_tol": f"{retention_time_delay} min",
        },
    }
    with open(os.path.join(tmp, "extract_config.yaml"), "w") as fh:
        yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)


def _write_compound_table(tmp: str, compound_id: int = 1,
                           adduct: str = "[M+H]+", tag: str = "WT") -> None:
    """
    Write comprehensive_table.csv with one row — the minimum needed by
    _prescreen_impl to iterate compounds.
    """
    df = pd.DataFrame([{
        "ID": compound_id, "Name": "TestCmpd",
        "mz": "195.087600", "rt": "",
        "adduct": adduct, "tag": tag,
        "set": "test", "known": "structure",
        "SMILES": "C", "Formula": "CH4",
        "InChIKey": "", "file": "dummy.mzML",
    }])
    df.to_csv(os.path.join(tmp, "comprehensive_table.csv"), index=False)


def _write_eic(tmp: str, intensities: list, compound_id: int = 1,
               adduct: str = "[M+H]+", tag: str = "WT") -> None:
    spectra_dir = os.path.join(tmp, "ms2_spectra")
    os.makedirs(spectra_dir, exist_ok=True)
    base = build_feature_base(compound_id, adduct, tag)
    rts  = [i * 0.1 for i in range(len(intensities))]
    pd.DataFrame({"rt": rts, "intensity": intensities}).to_csv(
        os.path.join(spectra_dir, f"{base}_EIC.csv"), index=False
    )


def _write_ms2(tmp: str, rows: list, compound_id: int = 1,
               adduct: str = "[M+H]+", tag: str = "WT") -> None:
    spectra_dir = os.path.join(tmp, "ms2_spectra")
    os.makedirs(spectra_dir, exist_ok=True)
    base = build_feature_base(compound_id, adduct, tag)
    pd.DataFrame(rows).to_csv(
        os.path.join(spectra_dir, f"{base}_MS2.csv"), index=False
    )


def _build_fixture(tmp: str, eic_intensities: list,
                   ms2_rows: list | None = None,
                   compound_id: int = 1,
                   adduct: str = "[M+H]+",
                   tag: str = "WT",
                   ms1_thresh: float = 1e5,
                   ms2_thresh: float = 1e3,
                   s2n: float = 3.0,
                   rt_tol: float = 0.5) -> None:
    _write_extract_config(tmp, ms1_thresh, ms2_thresh, s2n, rt_tol)
    _write_compound_table(tmp, compound_id, adduct, tag)
    _write_eic(tmp, eic_intensities, compound_id, adduct, tag)
    if ms2_rows is not None:
        _write_ms2(tmp, ms2_rows, compound_id, adduct, tag)


def _run(tmp: str) -> dict:
    """Run _prescreen_impl and return the first summary row as a dict."""
    result = _prescreen_impl(tmp)
    assert result["status"] == "success", f"_prescreen_impl failed: {result}"
    summary = pd.read_csv(os.path.join(tmp, "summary_table.csv"))
    assert len(summary) == 1
    return summary.iloc[0].to_dict()


# ===========================================================================
# 1.  Positive case — all flags pass
# ===========================================================================

def test_all_qa_flags_pass(tmp_path):
    """
    High-intensity EIC with a clear peak and a well-aligned MS2 scan
    should set all six QA flags and qa_pass to True.
    """
    ints = [0] * 10 + [5e5] * 5 + [0] * 10   # peak centred at rt = 1.0 min
    ms2  = [{"scan_id": "s1", "ms2_rt": 1.0,
              "ms2_intensity": 5e4, "peak_list": "100.00:2000;200.00:5000"}]
    _build_fixture(str(tmp_path), ints, ms2)
    row = _run(str(tmp_path))

    assert row["qa_ms1_exists"]
    assert row["qa_ms1_good_int"]
    assert row["qa_ms1_above_noise"]
    assert row["qa_ms2_exists"]
    assert row["qa_ms2_good_int"]
    assert row["qa_ms2_near"]
    assert row["qa_pass"]


# ===========================================================================
# 2.  qa_ms1_exists
# ===========================================================================

def test_qa_ms1_exists_false_when_no_eic_file(tmp_path):
    """
    If the EIC file is not written at all (e.g. no MS1 data matched),
    qa_ms1_exists must be False and qa_pass must be False.
    """
    _write_extract_config(str(tmp_path))
    _write_compound_table(str(tmp_path))
    # deliberately skip _write_eic
    row = _run(str(tmp_path))
    assert not row["qa_ms1_exists"]
    assert not row["qa_pass"]


# ===========================================================================
# 3.  qa_ms1_good_int
# ===========================================================================

def test_qa_ms1_good_int_false_below_threshold(tmp_path):
    """
    EIC peak at 1e4 with threshold 1e5 → qa_ms1_good_int False.
    Mirrors: if max_int > ms1_thresh in _prescreen_impl.
    """
    ints = [0] * 5 + [1e4] * 3 + [0] * 5
    _build_fixture(str(tmp_path), ints, ms1_thresh=1e5)
    row = _run(str(tmp_path))
    assert not row["qa_ms1_good_int"]
    assert not row["qa_pass"]


def test_qa_ms1_good_int_true_above_threshold(tmp_path):
    ints = [0] * 5 + [5e5] * 5 + [0] * 5
    _build_fixture(str(tmp_path), ints, ms1_thresh=1e5)
    row = _run(str(tmp_path))
    assert row["qa_ms1_good_int"]


# ===========================================================================
# 4.  qa_ms1_above_noise
# ===========================================================================

def test_qa_ms1_above_noise_false_flat_signal(tmp_path):
    """
    Flat EIC: max == mean, so max / mean = 1 < s2n = 3 → flag False.
    Mirrors: if max_int > mean_int * s2n in _prescreen_impl.
    """
    ints = [1e5] * 20
    ms2  = [{"scan_id": "s1", "ms2_rt": 1.0,
              "ms2_intensity": 5e4, "peak_list": "100.00:2000"}]
    _build_fixture(str(tmp_path), ints, ms2, ms1_thresh=5e4, s2n=3)
    row = _run(str(tmp_path))
    assert not row["qa_ms1_above_noise"]


def test_qa_ms1_above_noise_true_clear_peak(tmp_path):
    """
    Sharp peak against a flat baseline: max >> mean * s2n → flag True.
    The peak spans 3 scans: a single-scan spike is not counted as a peak.
    """
    ints = [1e3] * 9 + [2e5, 5e5, 2e5] + [1e3] * 9
    ms2  = [{"scan_id": "s1", "ms2_rt": 1.0,
              "ms2_intensity": 5e4, "peak_list": "100.00:2000"}]
    _build_fixture(str(tmp_path), ints, ms2, ms1_thresh=1e4, s2n=3)
    row = _run(str(tmp_path))
    assert row["qa_ms1_above_noise"]


# ===========================================================================
# 5.  qa_ms2_exists
# ===========================================================================

def test_qa_ms2_exists_false_when_no_ms2_file(tmp_path):
    """
    No MS2 CSV written → qa_ms2_exists False, qa_pass False.
    """
    ints = [0] * 5 + [5e5] * 5 + [0] * 5
    _build_fixture(str(tmp_path), ints, ms2_rows=None)
    row = _run(str(tmp_path))
    assert not row["qa_ms2_exists"]
    assert not row["qa_pass"]


# ===========================================================================
# 6.  qa_ms2_good_int
# ===========================================================================

def test_qa_ms2_good_int_false_all_fragments_below_threshold(tmp_path):
    """
    All fragment intensities below ms2_int_thresh → qa_ms2_good_int False.
    Mirrors: ms2_df["peak_list"].apply(lambda x: any(float(p.split(":")[1])
             > ms2_thresh ...)).any()
    """
    ints = [0] * 5 + [5e5] * 5 + [0] * 5
    ms2  = [{"scan_id": "s1", "ms2_rt": 0.5,
              "ms2_intensity": 100, "peak_list": "100.00:50;200.00:80"}]
    _build_fixture(str(tmp_path), ints, ms2, ms2_thresh=1e3)
    row = _run(str(tmp_path))
    assert not row["qa_ms2_good_int"]


def test_qa_ms2_good_int_true_one_fragment_above_threshold(tmp_path):
    ints = [0] * 5 + [5e5] * 5 + [0] * 5
    ms2  = [{"scan_id": "s1", "ms2_rt": 0.5,
              "ms2_intensity": 5e4, "peak_list": "100.00:50;200.00:5000"}]
    _build_fixture(str(tmp_path), ints, ms2, ms2_thresh=1e3)
    row = _run(str(tmp_path))
    assert row["qa_ms2_good_int"]


# ===========================================================================
# 7.  qa_ms2_near  (RT alignment)
# ===========================================================================

def test_qa_ms2_near_false_rt_outside_tolerance(tmp_path):
    """
    MS2 scan at rt=9.9 min, MS1 peak at ~0.5 min, tolerance 0.5 min
    → RT difference 9.4 min >> tolerance → qa_ms2_near False.
    Mirrors: if (diffs < rt_tol).any() in _prescreen_impl.
    """
    ints = [0] * 5 + [5e5] * 5 + [0] * 5
    ms2  = [{"scan_id": "s1", "ms2_rt": 9.9,
              "ms2_intensity": 5e4, "peak_list": "100.00:2000;200.00:5000"}]
    _build_fixture(str(tmp_path), ints, ms2, rt_tol=0.5)
    row = _run(str(tmp_path))
    assert not row["qa_ms2_near"]
    assert not row["qa_pass"]


def test_qa_ms2_near_true_rt_within_tolerance(tmp_path):
    ints = [0] * 10 + [5e5] * 5 + [0] * 10
    ms2  = [{"scan_id": "s1", "ms2_rt": 1.0,
              "ms2_intensity": 5e4, "peak_list": "100.00:2000;200.00:5000"}]
    _build_fixture(str(tmp_path), ints, ms2, rt_tol=0.5)
    row = _run(str(tmp_path))
    assert row["qa_ms2_near"]


# ===========================================================================
# 8.  Nearest MS2 scan selection
# ===========================================================================

def test_nearest_ms2_scan_selected(tmp_path):
    """
    When three MS2 scans exist, the one closest to the MS1 apex is chosen.
    Mirrors: idx = diffs.idxmin() in _prescreen_impl.
    """
    ints = [0] * 10 + [5e5] * 5 + [0] * 10   # apex at rt ~ 1.0 min
    ms2  = [
        {"scan_id": "s1", "ms2_rt": 0.3, "ms2_intensity": 1e4,
         "peak_list": "100.00:2000"},
        {"scan_id": "s2", "ms2_rt": 1.0, "ms2_intensity": 5e4,
         "peak_list": "200.00:6000"},
        {"scan_id": "s3", "ms2_rt": 2.5, "ms2_intensity": 2e4,
         "peak_list": "300.00:3000"},
    ]
    _build_fixture(str(tmp_path), ints, ms2, rt_tol=0.5)
    row = _run(str(tmp_path))
    assert row["qa_ms2_near"]
    assert float(row["ms2_rt"]) == pytest.approx(1.0, abs=0.05)


# ===========================================================================
# 9.  Output file
# ===========================================================================

def test_summary_table_written(tmp_path):
    """_prescreen_impl must always write summary_table.csv."""
    ints = [5e5] * 10
    _build_fixture(str(tmp_path), ints)
    _prescreen_impl(str(tmp_path))
    assert os.path.exists(os.path.join(str(tmp_path), "summary_table.csv"))


def test_summary_table_columns(tmp_path):
    """
    summary_table.csv must contain the columns documented in
    extraction_routes.prescreen_data docstring.
    """
    ints = [0] * 5 + [5e5] * 5 + [0] * 5
    ms2  = [{"scan_id": "s1", "ms2_rt": 0.5,
              "ms2_intensity": 5e4, "peak_list": "100.00:2000"}]
    _build_fixture(str(tmp_path), ints, ms2)
    _prescreen_impl(str(tmp_path))
    df = pd.read_csv(os.path.join(str(tmp_path), "summary_table.csv"))
    required = {"ID", "adduct", "tag",
                "qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise",
                "qa_ms2_exists", "qa_ms2_good_int", "qa_ms2_near",
                "qa_pass", "alignment", "ms2_sel", "ms1_rt", "ms2_rt"}
    assert required.issubset(set(df.columns))


# ===========================================================================
# 10.  Error handling
# ===========================================================================

def test_missing_config_returns_error(tmp_path):
    """Missing extract_config.yaml → status error, no crash."""
    _write_compound_table(str(tmp_path))
    result = _prescreen_impl(str(tmp_path))
    assert result["status"] == "error"


def test_missing_compound_table_returns_error(tmp_path):
    """Missing comprehensive_table.csv → status error, no crash."""
    _write_extract_config(str(tmp_path))
    result = _prescreen_impl(str(tmp_path))
    assert result["status"] == "error"
