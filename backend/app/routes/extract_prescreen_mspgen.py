import os
import json
import yaml
import pandas as pd
import multiprocessing as mp

from pyopenms import MSExperiment, MzMLFile
from rdkit import Chem
from rdkit.Chem.inchi import MolToInchiKey
from flask import request, jsonify
#from .web_app import app
from app.jobs.job_store import update_job

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
# ==========================================================
# EXTRACTION  
# ==========================================================

def _extract_data_impl(working_dir, job_id=None) -> dict:
    try:
        import os, json, yaml
        import pandas as pd
        from pyopenms import MSExperiment, MzMLFile

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
                if not eic_df.empty:
                    summary["qa_ms1_exists"] = True
                    max_int  = eic_df["intensity"].max()
                    mean_int = eic_df["intensity"].mean()
                     # --- prominence-filtered peak detection (mirrors CompoundPlot.jsx findTopPeaks) ---
                    intensities = eic_df["intensity"].to_numpy(dtype=float)
                    rts         = eic_df["rt"].to_numpy(dtype=float)

                    # 1) smooth with a 5-point moving average
                    kernel = np.ones(5) / 5
                    sm = np.convolve(intensities, kernel, mode='same')

                    # 2) find local maxima with minimum width of 3 points
                    from scipy.signal import find_peaks
                    peak_idxs, props = find_peaks(sm, width=3)
                    rt_peak  = None
                    if len(peak_idxs) > 0:
                        # 3) filter by prominence: peak must be > 5% of global smoothed max
                        min_prom = sm.max() * 0.05
                        prominent = [i for i in peak_idxs if (sm[i] - max(sm[max(0,i-10):i].min() if i>0 else 0,
                                    sm[i+1:min(len(sm),i+10)].min() if i<len(sm)-1 else 0, 1e-12)) >= min_prom]
                        if not prominent:
                            prominent = list(peak_idxs)  # fallback: use all peaks if none pass prominence
                        # 4) pick the most intense among prominent peaks
                        best = max(prominent, key=lambda i: intensities[i])
                        rt_peak = float(rts[best])
                    else:
                        # fallback to raw max if no peaks detected at all
                        rt_peak = float(eic_df.loc[eic_df["intensity"].idxmax(), "rt"])
                    summary["ms1_rt"]   = rt_peak
                    summary["alignment"]= True
                    if max_int > ms1_thresh: summary["qa_ms1_good_int"] = True
                    if max_int > mean_int * s2n: summary["qa_ms1_above_noise"] = True

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
        pd.DataFrame(summary_rows).to_csv(out, index=False)
        return {"status": "success", "summary_path": out}
    except Exception as e:
        return {"status": "error", "message": str(e)}



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

def _run_pipeline_background(job_id, working_dir, base_url="http://localhost:5000"):
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
            update_job(working_dir, job_id, state="error", progress=95,
                       message="Prescreen finished but summary_table.csv not found.",
                       finished_at=pd.Timestamp.utcnow().isoformat())
            return

        update_job(working_dir, job_id, state="done", progress=100, message="✅ Completed",
                   finished_at=pd.Timestamp.utcnow().isoformat())

    except Exception as e:
        update_job(working_dir, job_id, state="error",
                   message=f"Unhandled error in background pipeline: {e}",
                   finished_at=pd.Timestamp.utcnow().isoformat())


# ==========================================================
# FAST PARALLEL MSP GENERATION
# ==========================================================

def _build_msp_entry(args):

    row, compound_lookup = args

    ID = row["ID"]
    tag = row["tag"]
    adduct = row["adduct"]
    rt = row.get("ms1_rt", "")
    peak_list = row.get("peak_list", "")

    if pd.isna(peak_list) or peak_list == "":
      return None

    comp = compound_lookup.get((ID,tag))

    if comp is None:
        return None

    name = comp.get("Name", "Unknown")
    smiles = comp.get("SMILES", "")
    precursor = comp.get("mz", "")
    formula = comp.get("Formula","")
    inchikey = comp.get("InChIKey","")
   
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
    

    if rt:
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
    comp = (
        pd.read_csv(comp_path)
        .set_index(["ID", "tag"])
        .to_dict("index")
    )
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

def _run_pipeline_background(job_id, working_dir, base_url="http://localhost:5000"):
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

        update_job(working_dir, job_id, state="running", progress=85, message="Prescreen complete. Generating MSP library…",
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



