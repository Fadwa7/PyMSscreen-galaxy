import os
import json
import urllib.parse

import pandas as pd
import numpy as np
import yaml

from flask import Blueprint, request, jsonify, send_file, current_app

from app.utils import get_working_dir
from app.spectral_similarity import near_scan_consistency
from app.qc_score import add_qc_score
from app.routes.extract_prescreen_mspgen import (
    build_feature_base, generate_msp_library, find_top_peaks, add_cross_checks, _ppm_from_config)

data_bp = Blueprint("data", __name__)


def _load_prescreen_settings(working_directory):
    """
    Prescreen settings from extract_config.yaml: RT tolerance (min, default 0.5),
    MS1 intensity threshold and S/N factor (None if unavailable).
    """
    settings = {"rt_tol": 0.5, "ms1_thresh": None, "s2n": None}
    try:
        with open(os.path.join(working_directory, "extract_config.yaml"), "r") as f:
            prescreen = (yaml.safe_load(f) or {}).get("prescreen") or {}
    except Exception:
        return settings
    try:
        settings["rt_tol"] = float(str(prescreen["ret_time_shift_tol"]).replace("min", "").strip())
    except Exception:
        pass
    try:
        settings["ms1_thresh"] = float(prescreen["ms1_int_thresh"])
        settings["s2n"] = float(prescreen["s2n"])
    except Exception:
        pass
    return settings


def _measure_ms1_peak(eic_path, ms1_rt):
    """
    Apex intensity of the MS1 peak at ms1_rt and the trace mean, measured the
    same way as the prescreen (find_top_peaks apex, mean of the whole trace).
    Returns (apex, mean) or (None, None) if the trace cannot be read.
    """
    if not os.path.exists(eic_path):
        return None, None
    eic = pd.read_csv(eic_path)
    if eic.empty:
        return None, None
    rts = eic["rt"].to_numpy(dtype=float)
    ints = eic["intensity"].to_numpy(dtype=float)
    peaks = find_top_peaks(rts, ints, n=10)
    match = [p for p in peaks if abs(p["rt"] - ms1_rt) < 0.005]
    if match:
        apex = match[0]["apex_intensity"]
    else:
        # RT not among the detected peaks: highest point within +/-0.05 min
        window = np.abs(rts - ms1_rt) <= 0.05
        apex = float(ints[window].max()) if window.any() else 0.0
    return apex, float(ints.mean())


def _apply_selected_peak(df, idx, ms1_rt, working_directory, settings):
    """
    Use the MS1 peak selected by the user for this summary row and recalculate
    the measured flags for it, with the same rules as the prescreen:
    - MS2: closest MS2 scan with |ms2_rt - ms1_rt| < RT tolerance
      -> ms2_rt, peak_list, ms2_sel, qa_ms2_near (= RT Align)
    - MS1: apex intensity vs. MS1 threshold, apex vs. mean * S/N
      -> qa_ms1_good_int, qa_ms1_above_noise
    Returns True if an MS2 scan was found near the peak.
    """
    rt_tol = settings["rt_tol"]
    df.at[idx, "ms1_rt"] = ms1_rt
    df.at[idx, "manual_peak"] = True
    df.at[idx, "qa_ms1_exists"] = True

    base = build_feature_base(df.at[idx, "ID"], df.at[idx, "adduct"], df.at[idx, "tag"])

    apex, mean = _measure_ms1_peak(
        os.path.join(working_directory, "ms2_spectra", f"{base}_EIC.csv"), ms1_rt)
    if apex is not None:
        # measured values for the new peak (only if the table has these columns)
        if "ms1_apex_intensity" in df.columns:
            df.at[idx, "ms1_apex_intensity"] = apex
        if "ms1_sn" in df.columns:
            df.at[idx, "ms1_sn"] = apex / mean if mean > 0 else np.nan
    if apex is not None and settings["ms1_thresh"] is not None:
        df.at[idx, "qa_ms1_good_int"] = bool(apex > settings["ms1_thresh"])
        df.at[idx, "qa_ms1_above_noise"] = bool(apex > mean * settings["s2n"])

    ms2_path = os.path.join(working_directory, "ms2_spectra", f"{base}_MS2.csv")
    best = None
    n_near = 0
    if "ms2_consistency" in df.columns:  # reset; recalculated below if MS2 scans exist
        df.at[idx, "ms2_consistency"] = np.nan
        df.at[idx, "ms2_n_compared"] = 0
    if os.path.exists(ms2_path):
        ms2_df = pd.read_csv(ms2_path)
        if not ms2_df.empty and "ms2_rt" in ms2_df.columns:
            diffs = (ms2_df["ms2_rt"] - ms1_rt).abs()
            n_near = int((diffs < rt_tol).sum())
            if (diffs < rt_tol).any():
                best = ms2_df.loc[diffs.idxmin()]
            if "ms2_consistency" in df.columns:
                cons, n_pairs = near_scan_consistency(ms2_df, ms1_rt, rt_tol)
                df.at[idx, "ms2_consistency"] = np.nan if cons is None else cons
                df.at[idx, "ms2_n_compared"] = n_pairs
    if "ms2_n_near" in df.columns:
        df.at[idx, "ms2_n_near"] = n_near

    if best is not None:
        df.at[idx, "qa_ms2_near"] = True
        df.at[idx, "alignment"] = True
        df.at[idx, "ms2_sel"] = True
        df.at[idx, "ms2_rt"] = float(best["ms2_rt"])
        if "ms2_rt_delta" in df.columns:
            df.at[idx, "ms2_rt_delta"] = float(best["ms2_rt"]) - ms1_rt
        df.at[idx, "peak_list"] = best["peak_list"]
    else:
        df.at[idx, "qa_ms2_near"] = False
        df.at[idx, "alignment"] = False
        df.at[idx, "ms2_sel"] = False
        df.at[idx, "ms2_rt"] = np.nan
        df.at[idx, "peak_list"] = np.nan
        if "ms2_rt_delta" in df.columns:
            df.at[idx, "ms2_rt_delta"] = np.nan
    return best is not None

@data_bp.route("/get_csv")
def get_csv():

    """
    Serve a per-compound extracted CSV file (EIC or MS2) from the spectra directory.

    Query Parameters
    ----------------
    working_directory : str
        Base working directory containing the `ms2_spectra/` folder.
    compound_id : str
        Compound identifier used in filenames.
    tag : str
        URL-encoded tag string used in filenames.
    adduct : str
        URL-encoded adduct string used in filenames.
    type : {"EIC", "MS2"}
        File type suffix identifying which extracted file to return.

    Returns
    -------
    flask.Response
        - 200: CSV file contents (text/csv)
        - 400: "Missing parameters" if any required args are absent
        - 404: if no matching file is found
        - 500: stringified exception on unexpected errors

    Notes
    -----
    The endpoint searches for files with prefix:
    `{compound_id}_{adduct}_{tag}_{type}` under `<working_directory>/ms2_spectra/`.
    """
    try:
        working_dir = get_working_dir(request.args.get("working_directory"))
        compound_id = request.args.get("compound_id")
        file_type = request.args.get("type")  # 'EIC' or 'MS2'
        
        # Decode URL-encoded values
        tag = urllib.parse.unquote(request.args.get("tag", ""))
        adduct = urllib.parse.unquote(request.args.get("adduct", ""))
        if adduct.strip().lower() in {"nan", "null", "none"}:
          adduct = ""

        if not all([working_dir, compound_id, tag, file_type]):
            return "Missing parameters", 400

        spectra_dir = os.path.join(working_dir, "ms2_spectra")
        if adduct.strip():
            prefix = f"{compound_id}_{adduct}_{tag}_{file_type}"
        else:
            prefix = f"{compound_id}_{tag}_{file_type}"
        
        # Debug print path
        print(f"Looking for files in: {spectra_dir}")
        print(f"Filename prefix: {prefix}")

        matches = [f for f in os.listdir(spectra_dir) if f.startswith(prefix)]
        if not matches:
            return f"No file found matching: {prefix}", 404

        return send_file(os.path.join(spectra_dir, matches[0]), mimetype="text/csv")

    except Exception as e:
        return str(e), 500

@data_bp.route('/load_comprehensive_table', methods=['GET'])
def load_comprehensive_table():
    """
    Load and return the generated comprehensive compound table as JSON records.

    Query Parameters
    ----------------
    working_directory : str, optional
        Directory containing `comprehensive_table.csv`. Defaults to `"."`.

    Returns
    -------
    flask.Response
        - 200: JSON list of row records (empty strings for NaNs)
        - 200: empty list `[]` if the CSV does not exist (current behavior)
        - 500: {"error": "..."} on unexpected errors

    Side Effects
    ------------
    None.
    """
    try:
        base_dir = get_working_dir(request.args.get("working_directory"))
        table_path = os.path.join(base_dir, "comprehensive_table.csv")
        print("Requested path:", request.args.get("working_directory"))
        print(" Resolved path:", table_path)
        print("Looking for:", table_path)


        if not os.path.isdir(base_dir):
            return jsonify({
                "error": f"Base directory not found: {base_dir}"
            }), 400
        if not os.path.isfile(table_path):
            return jsonify([]), 200

        df = pd.read_csv(table_path)
        df.replace(r'^\s*$', np.nan, regex=True, inplace=True)

        for col in df.select_dtypes(include=["float64", "int64"]):
          df[col] = df[col].fillna(np.nan)

        df = df.replace([np.nan, np.inf, -np.inf], None)

        compounds = df.to_dict(orient="records")
        return current_app.response_class(
            response=json.dumps(compounds, allow_nan=False),
            mimetype="application/json"
        )

    except Exception as e:
        print("load_comprehensive_table ERROR:", e)
        return jsonify({"error": str(e)}), 500

@data_bp.route('/load_summary_table', methods=['GET'])
def load_summary_table():
    try:
        table_path = os.path.join(get_working_dir(request.args.get("working_directory")), "summary_table.csv")

        print("Looking for:", table_path)

        if not os.path.exists(table_path):
            return jsonify([])

        df = pd.read_csv(table_path)
        df.replace(r'^\s*$', np.nan, regex=True, inplace=True)

        # Preserve numeric columns
        for col in df.select_dtypes(include=["float64", "int64"]):
            df[col] = df[col].fillna(np.nan)

        df = df.replace([np.nan, np.inf, -np.inf], None)

        records = df.to_dict(orient="records")
        return current_app.response_class(
            response=json.dumps(records, allow_nan=False),
            mimetype="application/json"
        )
            
     
    except Exception as e:
        print("load_summary_table ERROR:", e)
        return jsonify({"error": str(e)}), 500

@data_bp.route('/save_qa_flags', methods=['POST'])
def save_qa_flags():
    try:
        data = request.get_json()
        flags = data.get("flags", {})
        working_directory = get_working_dir(data.get("working_directory"))

        table_path = os.path.join(working_directory, "summary_table.csv")
        if not os.path.exists(table_path):
            return jsonify({"error": "summary_table.csv not found"}), 404

        df = pd.read_csv(table_path)

        def _clean(value):
            # missing adduct (precursor m/z rows) -> ""
            text = "" if value is None else str(value).strip()
            return "" if text.lower() in {"nan", "null", "none"} else text

        df_adduct = df["adduct"].map(_clean)
        df_tag = df["tag"].astype(str).str.strip()
        updated_rows = 0
        not_found = []
        no_ms2_near_peak = []
        recalculated = []

        # Selected MS1 peaks (sent as MS1_RT only when the user changed the peak)
        if any("MS1_RT" in update for update in flags.values()):
            settings = _load_prescreen_settings(working_directory)
            if "manual_peak" not in df.columns:
                df["manual_peak"] = False
            df["ms1_rt"] = pd.to_numeric(df["ms1_rt"], errors="coerce")
            df["ms2_rt"] = pd.to_numeric(df["ms2_rt"], errors="coerce")
            df["peak_list"] = df["peak_list"].astype(object)

        for compound_key, update in flags.items():
            if "ID" in update and "tag" in update:
                # new format: ID, adduct and tag sent as separate values
                compound_id, adduct, tag = update["ID"], update.get("adduct"), update["tag"]
            else:
                # old format: "ID_adduct_tag" joined in the key
                try:
                    compound_id, adduct, tag = compound_key.split("_", 2)
                except ValueError:
                    return jsonify({"error": f"Invalid compound key format: {compound_key}"}), 400

            mask = (df["ID"].astype(str) == str(compound_id)) & \
                   (df_adduct == _clean(adduct)) & (df_tag == str(tag).strip())

            if not mask.any():
                not_found.append(compound_key)
                print(f" No summary row found for {compound_key}")
                continue
            updated_rows += int(mask.sum())

            print(f"Updating row for ID={compound_id}, adduct={adduct}, tag={tag}")
            print(" Incoming flags:", update)

            changed_rows = set()
            if update.get("MS1_RT") is not None:
                try:
                    new_rt = float(update["MS1_RT"])
                except (TypeError, ValueError):
                    return jsonify({"error": f"Invalid MS1_RT for {compound_key}: {update['MS1_RT']}"}), 400
                for idx in df[mask].index:
                    current = df.at[idx, "ms1_rt"]
                    if pd.notna(current) and abs(current - new_rt) < 1e-6:
                        continue  # same peak as before, nothing to change
                    has_ms2 = _apply_selected_peak(df, idx, new_rt, working_directory, settings)
                    changed_rows.add(idx)
                    print(f" Selected MS1 peak RT={new_rt} at row {idx}, MS2 near peak: {has_ms2}")
                    if not has_ms2:
                        no_ms2_near_peak.append(compound_key)
                if changed_rows:
                    recalculated.append(compound_key)

            # Tick boxes. "RT Align" controls qa_ms2_near, which counts for qa_pass
            # ("alignment" is kept equal to it for older readers).
            # For a row whose peak was just changed, the measured flags were
            # recalculated above; the ticks sent with this save still describe the
            # old peak, so they are not applied. The reviewer can override afterwards.
            recalculated_flags = {"MS1_Exists", "MS1_Intensity", "S2N_ratio", "RT_Alignment"}

            for display_key, summary_keys in {
                "MS1_Exists": ["qa_ms1_exists"],
                "MS2_Exists": ["qa_ms2_exists"],
                "MS1_Intensity": ["qa_ms1_good_int"],
                "RT_Alignment": ["qa_ms2_near", "alignment"],
                "S2N_ratio": ["qa_ms1_above_noise"]
            }.items():
                if display_key in update:
                    value = bool(update[display_key])
                    for idx in df[mask].index:
                        if idx in changed_rows and display_key in recalculated_flags:
                            continue
                        for summary_key in summary_keys:
                            df.at[idx, summary_key] = value
                            print(f" Set {summary_key} at row {idx} = {value}")

            for idx in df[mask].index:
                all_flags = [
                    df.at[idx, "qa_ms1_exists"],
                    df.at[idx, "qa_ms1_good_int"],
                    df.at[idx, "qa_ms1_above_noise"],
                    df.at[idx, "qa_ms2_exists"],
                    df.at[idx, "qa_ms2_good_int"],
                    df.at[idx, "qa_ms2_near"]
                ]
                result = all(all_flags)
                df.at[idx, "qa_pass"] = result
                print(f"qa_pass for row {idx} = {result}")

        # Ensure booleans are saved correctly
        for col in [
            "qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise",
            "qa_ms2_exists", "qa_ms2_good_int", "qa_ms2_near",
            "qa_pass", "alignment", "ms2_sel", "manual_peak"
        ]:
            if col in df.columns:
                df[col] = df[col].astype(bool)

        # cross-checks between rows (RT agreement between tags, shared peaks) can
        # change when a peak is changed; refresh them (only for tables that have them)
        comp_path = os.path.join(working_directory, "comprehensive_table.csv")
        if "qc_warnings" in df.columns and os.path.exists(comp_path):
            try:
                with open(os.path.join(working_directory, "extract_config.yaml"), "r") as f:
                    ppm_tol = _ppm_from_config(yaml.safe_load(f) or {})
            except Exception:
                ppm_tol = _ppm_from_config({})
            settings = _load_prescreen_settings(working_directory)
            df = add_cross_checks(df, pd.read_csv(comp_path), settings["rt_tol"], ppm_tol)

        # QC score follows the (possibly reviewed) flags; only for tables that have it
        if "qc_score" in df.columns:
            df = add_qc_score(df)

        print(f"Writing updated summary table to: {table_path}")
        df.to_csv(table_path, index=False)
        print(" Save completed.")

        # Keep library_all.msp in line with the updated summary table
        msp_entries, msp_error = None, None
        try:
            msp_entries = generate_msp_library(working_directory)["entries"]
        except Exception as e:
            msp_error = str(e)
            print(f"MSP library update failed: {e}")

        return jsonify({
            "message": f"QA flags updated in {table_path}",
            "updated_rows": updated_rows,
            "not_found": not_found,
            "no_ms2_near_peak": no_ms2_near_peak,
            "recalculated": recalculated,
            "msp_entries": msp_entries,
            "msp_error": msp_error
        })

    except Exception as e:
        print(f"Error saving flags: {e}")
        return jsonify({"error": str(e)}), 500

