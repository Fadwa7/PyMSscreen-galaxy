"""
pyMSscreen QC score (5 = strongest evidence, 1 = weakest).

  5  MS1 peak, MS2 near peak, consistent MS2 scans, MS1 intensity and S/N passed
  4  MS1 peak, MS2 near peak, consistent MS2 scans
  3  MS1 peak, MS2 near peak
  2  MS1 peak, no MS2 near peak
  1  no MS1 peak

The score is derived from the QA flags in the summary table, so manual review
(ticks, selected peak) is reflected. It describes data quality, not
identification confidence.

Defaults (change here if needed):
- MS2 scans count as consistent when their median pairwise cosine is at least
  CONSISTENCY_MIN. With only one MS2 scan near the peak, consistency cannot be
  assessed and does not lower the score.
- A cross-check warning (RT differs between tags, peak shared with another
  compound) caps the score at WARNING_CAP: such a row needs review.
"""

import numpy as np
import pandas as pd

CONSISTENCY_MIN = 0.8
WARNING_CAP = 2


def _flag(value):
    if isinstance(value, str):
        return value.strip().lower() == "true"
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return bool(value)


def score_row(row):
    """(score, note) for one summary row (dict-like)."""
    if not _flag(row.get("qa_ms1_exists")):
        score, notes = 1, ["no MS1 peak"]
    elif not _flag(row.get("qa_ms2_near")):
        score, notes = 2, ["no MS2 near peak"]
    else:
        consistency = pd.to_numeric(row.get("ms2_consistency"), errors="coerce")
        notes = []
        if pd.notna(consistency) and consistency < CONSISTENCY_MIN:
            score = 3
            notes.append(f"MS2 scans not consistent ({consistency:.2f})")
        elif not (_flag(row.get("qa_ms1_good_int")) and _flag(row.get("qa_ms1_above_noise"))):
            score = 4
            notes.append("MS1 intensity or S/N below threshold")
        else:
            score = 5
        if pd.isna(consistency):
            notes.append("consistency not assessed (fewer than 2 MS2 scans)")

    warnings = row.get("qc_warnings")
    if isinstance(warnings, str) and warnings.strip() and score > WARNING_CAP:
        score = WARNING_CAP
        notes.insert(0, f"capped at {WARNING_CAP}: {warnings.strip()}")
    return score, "; ".join(notes)


def add_qc_score(summary_df):
    """Return a copy of the summary table with qc_score and qc_score_note."""
    df = summary_df.copy()
    results = [score_row(r) for r in df.to_dict("records")]
    df["qc_score"] = [s for s, _ in results]
    df["qc_score_note"] = [n for _, n in results]
    return df
