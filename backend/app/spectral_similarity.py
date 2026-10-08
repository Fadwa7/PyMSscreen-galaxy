"""
MS2 spectral similarity for the QC score.

cosine_greedy follows the greedy peak matching of matchms' CosineGreedy
(pairs within a fragment m/z tolerance, accepted in order of their intensity
product, each peak used once), so scores are comparable with matchms.
"""

import math

import numpy as np


def parse_peak_list(peak_list):
    """'mz:int;mz:int;...' (pyMSscreen MS2 CSV format) -> (mz array, intensity array), sorted by m/z."""
    if peak_list is None or (isinstance(peak_list, float) and math.isnan(peak_list)):
        return np.empty(0), np.empty(0)
    mzs, ints = [], []
    for token in str(peak_list).split(";"):
        if ":" not in token:
            continue
        a, b = token.split(":", 1)
        try:
            mz, it = float(a), float(b)
        except ValueError:
            continue
        if math.isfinite(mz) and math.isfinite(it) and it > 0:
            mzs.append(mz)
            ints.append(it)
    mzs, ints = np.asarray(mzs, dtype=float), np.asarray(ints, dtype=float)
    order = np.argsort(mzs, kind="stable")
    return mzs[order], ints[order]


def cosine_greedy(spec1, spec2, tolerance=0.01):
    """Cosine similarity (0..1) of two centroided spectra; 0 if either is empty."""
    mz1, int1 = spec1
    mz2, int2 = spec2
    if mz1.size == 0 or mz2.size == 0:
        return 0.0
    norm = math.sqrt(float(np.dot(int1, int1))) * math.sqrt(float(np.dot(int2, int2)))
    if norm == 0:
        return 0.0
    lo = np.searchsorted(mz2, mz1 - tolerance, side="left")
    hi = np.searchsorted(mz2, mz1 + tolerance, side="right")
    pairs = [(int1[i] * int2[j], i, j) for i in range(mz1.size) for j in range(lo[i], hi[i])]
    pairs.sort(key=lambda p: -p[0])
    used1, used2, total = set(), set(), 0.0
    for prod, i, j in pairs:
        if i in used1 or j in used2:
            continue
        used1.add(i)
        used2.add(j)
        total += prod
    return float(min(1.0, total / norm))


def near_scan_consistency(ms2_df, ms1_rt, rt_tol, tolerance=0.01, max_scans=10):
    """
    How similar the MS2 scans near an MS1 peak are to each other.

    Takes the MS2 scans with |ms2_rt - ms1_rt| < rt_tol (at most max_scans,
    closest to the peak first) and returns (median pairwise cosine, number of
    pairs compared). With fewer than two scans there is nothing to compare:
    returns (None, 0).
    """
    if ms2_df is None or ms2_df.empty or ms1_rt is None or "ms2_rt" not in ms2_df.columns:
        return None, 0
    diffs = (ms2_df["ms2_rt"] - ms1_rt).abs()
    near = ms2_df.assign(_d=diffs)[diffs < rt_tol].sort_values("_d").head(max_scans)
    spectra = [parse_peak_list(p) for p in near["peak_list"]]
    spectra = [s for s in spectra if s[0].size]
    if len(spectra) < 2:
        return None, 0
    scores = [cosine_greedy(spectra[i], spectra[j], tolerance)
              for i in range(len(spectra)) for j in range(i + 1, len(spectra))]
    return float(np.median(scores)), len(scores)
