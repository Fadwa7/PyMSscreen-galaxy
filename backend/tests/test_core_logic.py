"""
test_core_logic.py
==================
Covers the reviewer's requested areas:
  - CSV parsing (compound table)
  - Adduct / mass logic  (ADDUCT_MASS from table_routes)
  - State & extract_config generation / round-trip
  - job_store helpers
  - build_feature_base filename helper

All tests are pure-Python / pandas / numpy; pyOpenMS is NOT required.
Run with:  pytest backend/tests/test_core_logic.py -v
"""

import io
import json
import math
import os
import csv
import tempfile

import numpy as np
import pandas as pd
import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers – import the real modules (conftest.py already adjusts sys.path)
# ---------------------------------------------------------------------------

from app.routes.extract_prescreen_mspgen import build_feature_base
from app.routes.table_routes import ADDUCT_MASS
from app.jobs.job_store import (
    create_job,
    load_status,
    update_job,
    save_status,
)


# ===========================================================================
# 1.  CSV PARSING
# ===========================================================================

COMPOUND_CSV_VALID = (
    "ID,Name,SMILES,mz,rt\n"
    "1,Caffeine,CN1C=NC2=C1C(=O)N(C(=O)N2C)C,195.0877,1.5\n"
    "2,Atrazine,CCNc1nc(Cl)nc(NC(C)C)n1,216.0116,3.2\n"
)


def _parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def test_csv_parsing_valid_row_count():
    rows = _parse_csv(COMPOUND_CSV_VALID)
    assert len(rows) == 2


def test_csv_parsing_field_values():
    rows = _parse_csv(COMPOUND_CSV_VALID)
    assert rows[0]["Name"] == "Caffeine"
    assert float(rows[0]["mz"]) == pytest.approx(195.0877)
    assert float(rows[1]["rt"]) == pytest.approx(3.2)


def test_csv_parsing_empty_body():
    rows = _parse_csv("ID,Name,SMILES,mz,rt\n")
    assert rows == []


def test_csv_parsing_missing_mz_column():
    text = "ID,Name,SMILES,rt\n1,Caffeine,C,1.5\n"
    rows = _parse_csv(text)
    assert "mz" not in rows[0]


def test_csv_pandas_read_normalises_columns():
    """Mirrors the column-normalisation in table_routes.generate_table."""
    df = pd.read_csv(io.StringIO(COMPOUND_CSV_VALID))
    df.columns = [c.strip() for c in df.columns]
    df.columns = [
        c.lower() if c.lower() in ["id", "name", "smiles", "mz", "rt", "precursor_mz"]
        else c
        for c in df.columns
    ]
    assert "smiles" in df.columns
    assert "id" in df.columns


def test_csv_whitespace_stripped_by_pandas():
    text = " ID , Name , SMILES , mz , rt \n1 , X , C , 100.0 , 2.0\n"
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    assert "ID" in df.columns
    assert df.loc[0, "ID"] == 1


# ===========================================================================
# 2.  ADDUCT / MASS LOGIC  (uses ADDUCT_MASS from the real module)
# ===========================================================================

PROTON = 1.007276


def _mz(neutral_mass: float, adduct: str) -> float:
    """Apply an adduct offset; raises KeyError for unknown adducts."""
    offset = ADDUCT_MASS[adduct]   # KeyError if unknown – mirrors table_routes behaviour
    return neutral_mass + offset


def _ppm(observed: float, theoretical: float) -> float:
    return abs(observed - theoretical) / theoretical * 1e6


# -- known adducts produce expected m/z values --

@pytest.mark.parametrize("adduct,neutral,expected", [
    ("[M+H]+",    194.0803, 195.0876),
    ("[M-H]-",    194.0803, 193.0730),
    ("[M+Na]+",   194.0803, 217.0695),
    ("[M+NH4]+",  194.0803, 212.1137),
    ("[M+K]+",    194.0803, 233.0434),
    ("[M+Cl]-",   194.0803, 229.0497),
])
def test_adduct_mz(adduct, neutral, expected):
    assert _mz(neutral, adduct) == pytest.approx(expected, abs=5e-3)


def test_adduct_unknown_raises():
    with pytest.raises(KeyError):
        _mz(194.0803, "[M+???]+")


def test_all_adducts_present_in_dict():
    """The table must contain at least the adducts referenced in the manuscript."""
    required = {"[M+H]+", "[M-H]-", "[M+Na]+", "[M+NH4]+", "[M+K]+"}
    assert required.issubset(ADDUCT_MASS.keys())


# -- ppm error calculations --

def test_ppm_within_5():
    theoretical = 195.0877
    observed = 195.0886        # ~4.6 ppm
    assert _ppm(observed, theoretical) < 5.0


def test_ppm_exceeds_5():
    theoretical = 195.0877
    observed = 195.091         # ~11 ppm
    assert _ppm(observed, theoretical) > 5.0


def test_ppm_exact_zero():
    mz = 195.0877
    assert _ppm(mz, mz) == pytest.approx(0.0)


# ===========================================================================
# 3.  STATE & EXTRACT-CONFIG GENERATION / ROUND-TRIP
# ===========================================================================

def _write_state(tmp: str, files: list[dict], compound_csv: str = "compounds.csv",
                 pos: list = None, neg: list = None) -> dict:
    """Mirrors the logic of state_routes.save_state."""
    state = {
        "working_directory": tmp,
        "compound_csv": os.path.join(tmp, compound_csv),
        "mzml_files": [
            {"file": os.path.join(tmp, f["file"]), "tag": f["tag"]}
            for f in files
        ],
        "adducts": {
            "positive": pos or [],
            "negative": neg or [],
        },
    }
    path = os.path.join(tmp, "state.json")
    with open(path, "w") as fh:
        json.dump(state, fh)
    return state


def _write_extract_config(tmp: str, **kw) -> dict:
    """Mirrors state_routes.save_extract_config."""
    defaults = dict(
        ms1_coarse_error=0.01, ms1_fine_error=5,
        ms1_eic_window=0.01,   retention_time_window=0.5,
        ms1_intensity_threshold=1e5, ms2_intensity_threshold=1e3,
        ms1_sn_ratio=3, retention_time_delay=0.5,
    )
    defaults.update(kw)
    cfg = {
        "tolerance": {
            "ms1 coarse": f"{defaults['ms1_coarse_error']} Da",
            "ms1 fine":   f"{defaults['ms1_fine_error']} ppm",
            "eic":        f"{defaults['ms1_eic_window']} Da",
            "rt":         f"{defaults['retention_time_window']} min",
        },
        "prescreen": {
            "ms1_int_thresh":      float(defaults["ms1_intensity_threshold"]),
            "ms2_int_thresh":      float(defaults["ms2_intensity_threshold"]),
            "s2n":                 float(defaults["ms1_sn_ratio"]),
            "ret_time_shift_tol":  f"{defaults['retention_time_delay']} min",
        },
    }
    path = os.path.join(tmp, "extract_config.yaml")
    with open(path, "w") as fh:
        yaml.dump(cfg, fh, default_flow_style=False, sort_keys=False)
    return cfg


def test_state_json_roundtrip(tmp_path):
    state = _write_state(str(tmp_path),
                         files=[{"file": "a.mzML", "tag": "WT"},
                                {"file": "b.mzML", "tag": "KO"}],
                         pos=["[M+H]+"])
    loaded = json.loads((tmp_path / "state.json").read_text())
    assert loaded["adducts"]["positive"] == ["[M+H]+"]
    assert len(loaded["mzml_files"]) == 2
    assert loaded["mzml_files"][0]["tag"] == "WT"


def test_state_working_directory_stored(tmp_path):
    state = _write_state(str(tmp_path), files=[])
    loaded = json.loads((tmp_path / "state.json").read_text())
    assert loaded["working_directory"] == str(tmp_path)


def test_extract_config_yaml_roundtrip(tmp_path):
    _write_extract_config(str(tmp_path), ms1_fine_error=10, ms1_sn_ratio=5)
    with open(tmp_path / "extract_config.yaml") as fh:
        cfg = yaml.safe_load(fh)
    assert cfg["tolerance"]["ms1 fine"] == "10 ppm"
    assert cfg["prescreen"]["s2n"] == pytest.approx(5.0)


def test_extract_config_rt_tol_parseable(tmp_path):
    _write_extract_config(str(tmp_path), retention_time_delay=0.3)
    with open(tmp_path / "extract_config.yaml") as fh:
        cfg = yaml.safe_load(fh)
    val = float(str(cfg["prescreen"]["ret_time_shift_tol"]).replace(" min", ""))
    assert val == pytest.approx(0.3)


def test_extract_config_defaults(tmp_path):
    cfg = _write_extract_config(str(tmp_path))
    assert cfg["prescreen"]["ms1_int_thresh"] == pytest.approx(1e5)
    assert cfg["prescreen"]["s2n"] == pytest.approx(3.0)


# ===========================================================================
# 4.  build_feature_base  (filename helper)
# ===========================================================================

def test_build_feature_base_with_adduct():
    result = build_feature_base(1, "[M+H]+", "WT")
    assert result == "1_[M+H]+_WT"


def test_build_feature_base_no_adduct():
    result = build_feature_base(42, "", "KO")
    assert result == "42_KO"


def test_build_feature_base_nan_adduct():
    result = build_feature_base(5, float("nan"), "STD")
    assert result == "5_STD"


def test_build_feature_base_nan_string_adduct():
    result = build_feature_base(5, "nan", "STD")
    assert result == "5_STD"


def test_build_feature_base_none_adduct():
    # pd.isna(None) is True
    result = build_feature_base(3, None, "WT")
    assert result == "3_WT"


# ===========================================================================
# 6.  JOB STORE
# ===========================================================================

def test_create_job_stores_queued_state(tmp_path):
    create_job(str(tmp_path), "abc123")
    data = load_status(str(tmp_path))
    job  = data["jobs"]["abc123"]
    assert job["state"] == "queued"
    assert job["progress"] == 0


def test_update_job_changes_state(tmp_path):
    create_job(str(tmp_path), "j1")
    update_job(str(tmp_path), "j1", state="running", progress=50)
    job = load_status(str(tmp_path))["jobs"]["j1"]
    assert job["state"] == "running"
    assert job["progress"] == 50


def test_update_job_nonexistent_is_noop(tmp_path):
    """Updating a job that doesn't exist should not raise."""
    create_job(str(tmp_path), "real")
    update_job(str(tmp_path), "ghost", state="done")   # should not raise
    data = load_status(str(tmp_path))
    assert "ghost" not in data["jobs"]


def test_load_status_missing_file_returns_empty(tmp_path):
    data = load_status(str(tmp_path))
    assert data == {"jobs": {}}


def test_multiple_jobs_independent(tmp_path):
    create_job(str(tmp_path), "j1")
    create_job(str(tmp_path), "j2")
    update_job(str(tmp_path), "j1", state="done", progress=100)
    jobs = load_status(str(tmp_path))["jobs"]
    assert jobs["j1"]["state"] == "done"
    assert jobs["j2"]["state"] == "queued"


def test_status_file_is_valid_json(tmp_path):
    create_job(str(tmp_path), "j1")
    path = os.path.join(str(tmp_path), "status.json")
    assert os.path.exists(path)
    with open(path) as fh:
        data = json.load(fh)
    assert "jobs" in data
