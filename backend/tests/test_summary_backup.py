"""Step 6: re-running the prescreen keeps the old summary table as a backup."""
import os

import pandas as pd
import yaml

from app.routes.extract_prescreen_mspgen import _prescreen_impl


def _setup(wd):
    (wd / "extract_config.yaml").write_text(yaml.safe_dump({
        "tolerance": {"ms1 fine": "10 ppm"},
        "prescreen": {"ms1_int_thresh": 1e4, "ms2_int_thresh": 1e3, "s2n": 3,
                      "ret_time_shift_tol": "0.5 min"}}))
    pd.DataFrame([dict(ID=101, mz=116.0707, adduct="[M+H]+", tag="WT+", Name="Example",
                       file="s.mzML")]).to_csv(wd / "comprehensive_table.csv", index=False)


def test_first_run_makes_no_backup(tmp_path):
    _setup(tmp_path)
    res = _prescreen_impl(str(tmp_path))
    assert res["status"] == "success"
    assert res["backup_path"] is None
    assert not (tmp_path / "backups").exists()


def test_rerun_backs_up_manual_corrections(tmp_path):
    _setup(tmp_path)
    _prescreen_impl(str(tmp_path))
    # simulate a manual correction in the existing table
    df = pd.read_csv(tmp_path / "summary_table.csv")
    df["manual_peak"] = True
    df.to_csv(tmp_path / "summary_table.csv", index=False)
    old = (tmp_path / "summary_table.csv").read_text()

    res1 = _prescreen_impl(str(tmp_path))
    res2 = _prescreen_impl(str(tmp_path))          # second re-run, possibly same second

    assert open(res1["backup_path"]).read() == old             # corrections kept in backup
    assert res1["backup_path"] != res2["backup_path"]          # nothing overwritten
    assert len(os.listdir(tmp_path / "backups")) == 2
    assert "manual_peak" not in pd.read_csv(tmp_path / "summary_table.csv").columns  # fresh table
