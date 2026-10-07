import os
import json
import shutil
import yaml
import numpy as np
import pandas as pd
import multiprocessing as mp
from rdkit import Chem
from rdkit.Chem.inchi import MolToInchiKey
from flask import request, jsonify
#from .web_app import app
from app.jobs.job_store import update_job

def load_pyopenms():
    """
    Lazy-load pyOpenMS so importing web_app does not fail during smoke tests.
    """
    try:
        from pyopenms import MSExperiment, MzMLFile
        return MSExperiment, MzMLFile
    except ImportError as exc:
        raise RuntimeError(
            "pyOpenMS could not be loaded. Missing native system libraries, "
            "for example libglib2.0-0."
        ) from exc

def build_feature_base(ID, adduct, tag):
    if pd.isna(adduct):
        adduct = ""
    else:
        adduct = str(adduct).strip()
        if adduct.lower() == "nan":
            adduct = ""

    tag = str(tag).strip()
    if adduct:
        return f"{ID}_{adduct}_{tag}"
    return f"{ID}_{tag}"


def _backup_summary_table(working_dir):
    """
    Copy an existing summary_table.csv to backups/summary_table_<date>_<time>.csv
    before it is overwritten, so manual QA corrections are never lost.
    Returns the backup path, or None if there was no table to back up.
    """
    table = os.path.join(working_dir, "summary_table.csv")
    if not os.path.exists(table):
        return None
    backup_dir = os.path.join(working_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d_%H%M%S")
    backup = os.path.join(backup_dir, f"summary_table_{stamp}.csv")
    n = 1
    while os.path.exists(backup):  # two runs within the same second
        backup = os.path.join(backup_dir, f"summary_table_{stamp}_{n}.csv")
        n += 1
    shutil.copy2(table, backup)
    return backup


def moving_average(values, window=5):
    """
    Centered moving average; at the edges only existing points are averaged.
    Python copy of movingAverage() in frontend CompoundPlot.jsx.
    """
    values = np.asarray(values, dtype=float)
    kernel = np.ones(window)
    return (np.convolve(values, kernel, mode="same")
            / np.convolve(np.ones_like(values), kernel, mode="same"))


def find_top_peaks(rts, intensities, n=3, min_separation=0.15,
                   prominence_frac=0.05, min_width_points=3):
    """
    Top-n MS1 peaks of an EIC trace, as list of dicts {rt, intensity, idx},
    most intense first. Line-by-line Python copy of findTopPeaks() in
    frontend CompoundPlot.jsx, so the summary table and the plot always
    pick the same peaks. Keep both implementations in sync.
    """
    rts = np.asarray(rts, dtype=float)
    ints = np.asarray(intensities, dtype=float)
    if len(rts) == 0 or len(rts) != len(ints):
        return []
    sm = moving_average(ints, 5)
    max_i = sm.max()
    if not np.isfinite(max_i) or max_i <= 0:
        return []
    min_prom = max_i * prominence_frac

    candidates = []
    for i in range(1, len(sm) - 1):
        if sm[i] > sm[i - 1] and sm[i] >= sm[i + 1]:
            l = i - 1
            while l > 0 and sm[l] < sm[l + 1]:
                l -= 1
            r = i + 1
            while r < len(sm) - 1 and sm[r] < sm[r - 1]:
                r += 1
            if r - l < min_width_points:
                continue
            baseline = max(min(sm[l], sm[r]), 1e-12)
            if sm[i] - baseline >= min_prom:
                candidates.append({"rt": float(rts[i]), "intensity": float(ints[i]), "idx": i})

    candidates.sort(key=lambda c: -c["intensity"])  # stable, like JS sort
    picked = []
    for c in candidates:
        if all(abs(p["rt"] - c["rt"]) >= min_separation for p in picked):
            picked.append(c)
            if len(picked) == n:
                break
    return picked


def _clean_str(value):
    """Return '' for missing values (NaN, None, 'nan'), otherwise the value as text."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    value = str(value).strip()
    return "" if value.lower() in {"nan", "none", "null"} else value
# ==========================================================
# EXTRACTION  
# ==========================================================

def _extract_data_impl(working_dir, job_id=None) -> dict:
    try:
        import os, json, yaml
        import pandas as pd
        MSExperiment, MzMLFile = load_pyopenms()

        config_path   = os.path.join(working_dir, "extract_config.yaml")
        state_path    = os.path.join(working_dir, "state.json")
        compound_path = os.path.join(working_dir, "comprehensive_table.csv")

        spectra_dir = os.path.join(working_dir, "ms2_spectra")
        os.makedirs(spectra_dir, exist_ok=True)

        with open(state_path, "r") as f:
            state = json.load(f)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        comp_df = pd.read_csv(compound_path)

        coarse_win = float(config["tolerance"]["ms1 coarse"].replace(" Da", ""))
        fine_ppm   = float(config["tolerance"]["ms1 fine"].replace(" ppm", ""))

        files = state.get("mzml_files", [])
        total = max(1, len(files))
        done  = 0
        error_summary = []

        for file_obj in files:
            f = file_obj["file"]
            mzml_path = f if os.path.isabs(f) else os.path.join(working_dir, f)  # avoid double-join
            tag    = str(file_obj["tag"]).strip()
            #adduct = str(file_obj["adduct"]).strip()
            file_key = os.path.basename(mzml_path)

            # filter comprehensive table rows that belong to THIS mzML file + tag
            # (each row already carries its "adduct")
            df_file = comp_df[
                (comp_df["file"].astype(str) == file_key) &
                (comp_df["tag"].astype(str) == tag)
            ]

            # if nothing to do for this file, continue quickly
            if df_file.empty:
                done += 1
                if job_id:
                    prog = 5 + int(55 * done / total)
                    update_job(working_dir, job_id, progress=prog, message=f"Extraction {done}/{total}…")
                continue

            exp = MSExperiment()
            MzMLFile().load(mzml_path, exp)
            spectra     = exp.getSpectra()
            ms1_spectra = [s for s in spectra if s.getMSLevel() == 1]
            ms2_spectra = [s for s in spectra if s.getMSLevel() == 2]

            for row in df_file.itertuples():
                #row_tag    = str(row.tag).strip()
                row_adduct = str(row.adduct).strip()
                
                mz = float(row.mz)
                fine_delta = mz * fine_ppm / 1_000_000
                low, high  = mz - fine_delta, mz + fine_delta

                # MS1 EIC
                eic_rt, eic_int = [], []
                for sp in ms1_spectra:
                    rt = sp.getRT() / 60.0
                    try:
                        mzs, ints = sp.get_peaks()
                    except Exception as e:
                        msg = f"MS1 get_peaks() failed for ID={row.ID}, RT={rt:.2f} min: {e}"
                        error_summary.append(msg)
                        continue
                    intensity = sum(i for m, i in zip(mzs, ints) if low <= m <= high)
                    eic_rt.append(rt); eic_int.append(intensity)

                eic_df   = pd.DataFrame({"rt": eic_rt, "intensity": eic_int})
                base = build_feature_base(row.ID, row.adduct, tag)
                eic_path = os.path.join(spectra_dir, f"{base}_EIC.csv")
                try:
                    eic_df.to_csv(eic_path, index=False)
                except Exception as e:
                    err = f"Failed to save EIC for ID={row.ID}: {e}"
                    error_summary.append(err)

                # MS2
                matched_ms2 = []
                for sp in ms2_spectra:
                    precursors = sp.getPrecursors()
                    if not precursors:
                        continue
                    p_mz = precursors[0].getMZ()
                    if abs(p_mz - mz) > coarse_win:
                        continue
                    try:
                        ms2_mzs, ms2_ints = sp.get_peaks()
                    except Exception as e:
                        msg = f"MS2 get_peaks() failed for ID={row.ID}, precursor_mz={p_mz:.4f}: {e}"
                        error_summary.append(msg); continue
                    if len(ms2_mzs) == 0:
                        continue
                    peak_list = ";".join(f"{mzv:.4f}:{intv:.0f}" for mzv, intv in zip(ms2_mzs, ms2_ints))
                    matched_ms2.append({
                        "scan_id":       sp.getNativeID() or f"scan_{len(matched_ms2)+1}",
                        "ms2_rt":        sp.getRT() / 60.0,
                        "ms2_intensity": sum(ms2_ints),
                        "peak_list":     peak_list
                    })
                if matched_ms2:
                    ms2_df   = pd.DataFrame(matched_ms2)
                    ms2_path = ms2_path = os.path.join(spectra_dir, f"{base}_MS2.csv")
                    try:
                        ms2_df.to_csv(ms2_path, index=False)
                    except Exception as e:
                        msg = f"Failed to save MS2 for ID={row.ID}: {e}"
                        error_summary.append(msg)

            # progress 5 → 60
            done += 1
            if job_id:
                prog = 5 + int(55 * done / total)
                update_job(working_dir, job_id, progress=prog, message=f"Extraction {done}/{total}…")

        return {"status": "success", "errors": error_summary}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def _prescreen_impl(working_dir, job_id=None) -> dict:
    try:
        import os, yaml
        import pandas as pd
        import numpy as np

        config_path   = os.path.join(working_dir, "extract_config.yaml")
        compound_path = os.path.join(working_dir, "comprehensive_table.csv")
        spectra_dir   = os.path.join(working_dir, "ms2_spectra")

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        ms1_thresh = config["prescreen"]["ms1_int_thresh"]
        ms2_thresh = config["prescreen"]["ms2_int_thresh"]
        s2n        = config["prescreen"]["s2n"]
        rt_tol     = float(str(config["prescreen"]["ret_time_shift_tol"]).replace(" min", ""))

        compound_df  = pd.read_csv(compound_path)
        summary_rows = []

        total = max(1, len(compound_df))
        done  = 0

        for row in compound_df.itertuples():
            base = build_feature_base(row.ID, row.adduct, row.tag)
            eic_path = os.path.join(spectra_dir, f"{base}_EIC.csv")
            ms2_path = os.path.join(spectra_dir, f"{base}_MS2.csv")

            summary = {
                "ID": row.ID, "Name": getattr(row, "Name", ""), "adduct": row.adduct, "tag": row.tag,
                "qa_ms1_exists": False, "qa_ms1_good_int": False, "qa_ms1_above_noise": False,
                "qa_ms2_exists": False, "qa_ms2_good_int": False, "qa_ms2_near": False,
                "qa_pass": False, "alignment": False, "ms2_sel": False,
                "ms1_rt": None, "ms2_rt": None, "peak_list": None
            }

            rt_peak = None
            if os.path.exists(eic_path):
                eic_df = pd.read_csv(eic_path)
                # an all-zero trace has no MS1 signal at all
                if not eic_df.empty and eic_df["intensity"].max() > 0:
                    mean_int = eic_df["intensity"].mean()
                    # --- MS1 peak: same peak finder as the plot (findTopPeaks) ---
                    top_peaks = find_top_peaks(eic_df["rt"], eic_df["intensity"])
                    rt_peak = None
                    peak_int = None
                    if top_peaks:
                        rt_peak  = top_peaks[0]["rt"]
                        peak_int = top_peaks[0]["intensity"]
                    # no peak detected -> no MS1 peak (no fallback to the raw maximum,
                    # which invented a "peak" at the first scan of empty traces)
                    if rt_peak is not None:
                        summary["qa_ms1_exists"] = True
                        summary["ms1_rt"]   = rt_peak
                        summary["alignment"]= True
                        # intensity checks use the chosen peak, not the highest point
                        # of the whole trace (a one-scan spike could pass otherwise)
                        if peak_int > ms1_thresh: summary["qa_ms1_good_int"] = True
                        if peak_int > mean_int * s2n: summary["qa_ms1_above_noise"] = True

            if os.path.exists(ms2_path):
                ms2_df = pd.read_csv(ms2_path)
                if not ms2_df.empty:
                    summary["qa_ms2_exists"] = True
                    summary["qa_ms2_good_int"] = ms2_df["peak_list"].apply(
                        lambda x: any(float(p.split(":")[1]) > ms2_thresh for p in x.split(";") if ":" in p)
                    ).any()
                    if rt_peak is not None and "ms2_rt" in ms2_df.columns:
                        diffs = (ms2_df["ms2_rt"] - rt_peak).abs()
                        if (diffs < rt_tol).any():
                            idx = diffs.idxmin()
                            summary["qa_ms2_near"] = True
                            summary["ms2_sel"]     = True
                            summary["ms2_rt"]      = float(ms2_df.loc[idx, "ms2_rt"])
                            summary["peak_list"] = ms2_df.loc[idx, "peak_list"]
                        else:
                            summary["alignment"]   = False
            else:
                summary["alignment"] = False

            flags = ["qa_ms1_exists","qa_ms1_good_int","qa_ms1_above_noise",
                     "qa_ms2_exists","qa_ms2_good_int","qa_ms2_near"]
            summary["qa_pass"] = all(summary[f] for f in flags)

            summary_rows.append(summary)

            # progress 60 → 99
            done += 1
            if job_id and (done % 20 == 0 or done == total):
                prog = 60 + int(39 * done / total)
                update_job(working_dir, job_id, progress=prog, message=f"Prescreen {done}/{total}…")

        out = os.path.join(working_dir, "summary_table.csv")
        try:
            backup = _backup_summary_table(working_dir)
        except Exception as e:
            # do not overwrite the old table if it could not be backed up
            return {"status": "error",
                    "message": f"Could not back up existing summary_table.csv, nothing was overwritten: {e}"}
        pd.DataFrame(summary_rows).to_csv(out, index=False)
        return {"status": "success", "summary_path": out, "backup_path": backup}
    except Exception as e:
        return {"status": "error", "message": str(e)}



# ==========================================================
# FAST PARALLEL MSP GENERATION
# ==========================================================

def _build_msp_entry(args):

    row, compound_lookup = args

    ID = row["ID"]
    tag = row["tag"]
    adduct = _clean_str(row["adduct"])
    rt = row.get("ms1_rt", "")
    peak_list = row.get("peak_list", "")

    if pd.isna(peak_list) or peak_list == "":
      return None

    # look up by ID + adduct + tag (unique); ID + tag kept as fallback
    comp = compound_lookup.get((ID, adduct, tag)) or compound_lookup.get((ID, tag))

    if comp is None:
        return None

    name = _clean_str(comp.get("Name")) or "Unknown"
    smiles = _clean_str(comp.get("SMILES"))
    precursor = _clean_str(comp.get("mz"))
    formula = _clean_str(comp.get("Formula"))
    inchikey = _clean_str(comp.get("InChIKey"))
   
    peaks = []

    for p in peak_list.split(";"):
        if ":" in p:
            mz, intensity = p.split(":")
            peaks.append((mz.strip(), intensity.strip()))

    lines = []

    lines.append(f"NAME: {name}")
    lines.append(f"COMMENT: ID= {ID}")
    lines.append(f"COMMENT: Tag= {tag}")
    lines.append(f"PRECURSORMZ: {precursor}")
    lines.append(f"PRECURSORTYPE: {adduct}")
    lines.append(f"SMILES: {smiles}")
    lines.append(f"FORMULA: {formula}")
    lines.append(f"InChIKey: {inchikey}")
    

    if _clean_str(rt):
        lines.append(f"RT: {rt}")

    lines.append(f"Num Peaks: {len(peaks)}")

    for mz, intensity in peaks:
        lines.append(f"{mz} {intensity}")

    lines.append("")

    return "\n".join(lines)


def generate_msp_library(working_dir, job_id=None):

    summary_path = os.path.join(working_dir, "summary_table.csv")
    comp_path = os.path.join(working_dir, "comprehensive_table.csv")

    library_dir = os.path.join(working_dir, "spectral_library")
    os.makedirs(library_dir, exist_ok=True)

    summary = pd.read_csv(summary_path)
    summary["qa_pass"] = summary["qa_pass"].astype(str).str.upper() == "TRUE"
    summary["ms2_sel"] = summary["ms2_sel"].astype(str).str.upper() == "TRUE"
    # key = ID + adduct + tag, which is unique even with several adducts per tag
    comp = {}
    for r in pd.read_csv(comp_path).to_dict("records"):
        comp.setdefault((r["ID"], _clean_str(r.get("adduct")), r["tag"]), r)
    valid = summary[
        (summary["qa_pass"] == True) &
        (summary["ms2_sel"] == True)
    ]

    print("Total rows:", len(summary))
    print("Valid rows:", len(valid))

    rows = valid.to_dict("records")
    args = [(row, comp) for row in rows]

    entries = []

    for arg in args:
        entry = _build_msp_entry(arg)
        if entry:
            entries.append(entry)

    print("Total summary rows:", len(summary))
    print("Valid rows for MSP:", len(valid))
    print("Entries generated:", len(entries))
    
    library_file = os.path.join(library_dir, "library_all.msp")

    
    with open(library_file, "w") as f:
        f.write("\n".join(entries))

    return {
        "entries": len(entries),
        "library_path": library_file
    }

def _extraction_outputs_exist(working_dir: str) -> bool:
    spectra_dir = os.path.join(working_dir, "ms2_spectra")
    if not os.path.isdir(spectra_dir):
        return False
    # at least one EIC or MS2 file produced
    for root, _, files in os.walk(spectra_dir):
        for fn in files:
            if fn.endswith("_EIC.csv") or fn.endswith("_MS2.csv"):
                return True
    return False

def _prescreen_outputs_exist(working_dir: str) -> bool:
    return os.path.exists(os.path.join(working_dir, "summary_table.csv"))

def _run_pipeline_background(job_id, working_dir):
    try:
        update_job(working_dir, job_id, state="running",
                   started_at=pd.Timestamp.utcnow().isoformat(),
                   progress=5, message="Starting extraction…")

        # Extraction
        res1 = _extract_data_impl(working_dir, job_id=job_id)
        if res1.get("status") != "success":
            update_job(working_dir, job_id, state="error", progress=0,
                       message=f"Extraction failed: {res1}", finished_at=pd.Timestamp.utcnow().isoformat())
            return

        if not _extraction_outputs_exist(working_dir):
            update_job(working_dir, job_id, state="error", progress=55,
                       message="Extraction finished but no spectra/EIC files found.",
                       finished_at=pd.Timestamp.utcnow().isoformat())
            return

        update_job(working_dir, job_id, progress=60, message="Extraction done. Starting prescreen…")

        # Prescreen
        res2 = _prescreen_impl(working_dir, job_id=job_id)
        if res2.get("status") != "success":
            update_job(working_dir, job_id, state="error", progress=60,
                       message=f"Prescreen failed: {res2}", finished_at=pd.Timestamp.utcnow().isoformat())
            return

        if not _prescreen_outputs_exist(working_dir):
            update_job(working_dir, job_id, state="error", progress=80,
                       message="Prescreen finished but summary_table.csv not found.",
                       finished_at=pd.Timestamp.utcnow().isoformat())
            return

        backup_note = ""
        if res2.get("backup_path"):
            backup_note = f" Previous summary table saved as backups/{os.path.basename(res2['backup_path'])}."
        update_job(working_dir, job_id, state="running", progress=85,
                   message=f"Prescreen complete.{backup_note} Generating MSP library…",
                   finished_at=pd.Timestamp.utcnow().isoformat())
        
        # ---------------------------
        # STEP 3 — MSP library
        # ---------------------------
        try:

            result = generate_msp_library(working_dir, job_id=job_id)

            update_job(
                working_dir,
                job_id,
                progress=98,
                message=f"MSP library generated ({result['entries']} spectra)."
            )

        except Exception as msp_error:
             print("MSP ERROR:", msp_error)   
             update_job(
                working_dir,
                job_id,
                progress=98,
                message=f"MSP generation skipped due to error: {msp_error}"
            )
        
        # ---------------------------
        # FINISH JOB
        # ---------------------------
        update_job(
            working_dir,
            job_id,
            state="done",
            progress=100,
            message="✅ Extraction, prescreening, and msp library generation complete.",
            finished_at=pd.Timestamp.utcnow().isoformat()
        )

    except Exception as e:
        update_job(working_dir, job_id, state="error",
                   message=f"Unhandled error in background pipeline: {e}",
                   finished_at=pd.Timestamp.utcnow().isoformat())



