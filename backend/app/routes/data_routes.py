import os
import json
import urllib.parse

import pandas as pd
import numpy as np

from flask import Blueprint, request, jsonify, send_file, current_app

from app.config import BASE_WORKING_DIR

data_bp = Blueprint("data", __name__)

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
        working_dir = os.path.expanduser(request.args.get("working_directory"))
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
        #working_directory = os.path.expanduser(request.args.get("working_directory", "."))
        table_path = os.path.join(BASE_WORKING_DIR, "comprehensive_table.csv")
        print("Requested path:", request.args.get("working_directory"))
        print(" Resolved path:", table_path)
        print("Looking for:", table_path)


        if not os.path.isdir(BASE_WORKING_DIR):
            return jsonify({
                "error": f"Base directory not found: {BASE_WORKING_DIR}"
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
        #working_directory = os.path.expanduser(request.args.get("working_directory", "."))
        table_path = os.path.join(BASE_WORKING_DIR, "summary_table.csv")

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
        import pandas as pd
        data = request.get_json()
        flags = data.get("flags", {})
        working_directory = os.path.expanduser(data.get("working_directory", "."))

        table_path = os.path.join(working_directory, "summary_table.csv")
        if not os.path.exists(table_path):
            return jsonify({"error": "summary_table.csv not found"}), 404

        df = pd.read_csv(table_path)

        for compound_key, update in flags.items():
            try:
                compound_id, adduct, tag = compound_key.split("_", 2)
            except ValueError:
                return jsonify({"error": f"Invalid compound key format: {compound_key}"}), 400

            mask = (df["ID"].astype(str) == str(compound_id)) & \
                   (df["adduct"] == adduct) & (df["tag"] == tag)

            print(f"Updating row for ID={compound_id}, adduct={adduct}, tag={tag}")
            print(" Incoming flags:", update)

            for display_key, summary_key in {
                "MS1_Exists": "qa_ms1_exists",
                "MS2_Exists": "qa_ms2_exists",
                "MS1_Intensity": "qa_ms1_good_int",
                "RT_Alignment": "alignment",
                "S2N_ratio": "qa_ms1_above_noise"
            }.items():
                if display_key in update:
                    value = bool(update[display_key])
                    for idx in df[mask].index:
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
            "qa_pass", "alignment", "ms2_sel"
        ]:
            if col in df.columns:
                df[col] = df[col].astype(bool)

        print(f"Writing updated summary table to: {table_path}")
        df.to_csv(table_path, index=False)
        print(" Save completed.")

        return jsonify({"message": f"QA flags updated in {table_path}"})

    except Exception as e:
        print(f"Error saving flags: {e}")
        return jsonify({"error": str(e)}), 500


@data_bp.route('/get_compound_plots', methods=['GET'])
def get_compound_plots():
    """
    Return plot-ready data structures for a compound (currently dummy data).

    Query Parameters
    ----------------
    compound_id : str
        Compound identifier (currently unused in the dummy implementation).
    working_directory : str, optional
        Working directory (currently unused in the dummy implementation).

    Returns
    -------
    flask.Response
        JSON with three plot objects:
        - eic: {"x": [...], "y": [...]}
        - ms2: {"x": [...], "y": [...]}
        - fragment: {"x": [...], "y": [...]}

    Notes
    -----
    This endpoint currently returns synthetic curves and fragment peaks for
    UI prototyping. Replace with real extracted data as needed.
    """
    try:
        import numpy as np
        compound_id = request.args.get("compound_id")
        working_directory = os.path.expanduser(request.args.get("working_directory", "."))

        eic_x = np.linspace(0, 10, 100)
        eic_y = np.exp(-((eic_x - 5) ** 2) / 0.8) * 1e5

        ms2_x = np.linspace(2, 8, 50)
        ms2_y = np.exp(-((ms2_x - 5) ** 2) / 1.5) * 6e4

        frag_x = [120.1, 135.2, 150.3, 165.5, 180.7]
        frag_y = [7000, 12000, 15000, 10000, 8000]

        return jsonify({
            "eic": {"x": eic_x.tolist(), "y": eic_y.tolist()},
            "ms2": {"x": ms2_x.tolist(), "y": ms2_y.tolist()},
            "fragment": {"x": frag_x, "y": frag_y}
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@data_bp.route('/export_fragments', methods=['POST'])
def export_fragments():
    """
    Export fragment peaks for a compound to a CSV file (currently dummy content).

    Request JSON
    ------------
    compound_id : str
        Compound identifier used to name the output file.
    working_directory : str
        Working directory where `figures/` will be created if missing.

    Returns
    -------
    flask.Response
        JSON response:
        - 200: {"message": "Exported fragment peaks to <.../figures/{compound_id}_fragments.csv>"}
        - 500: {"error": "..."} on unexpected errors

    Side Effects
    ------------
    Creates `<working_directory>/figures/` and writes `{compound_id}_fragments.csv`.

    Notes
    -----
    The current implementation writes placeholder peaks. Replace with MS2-derived
    fragment export logic for publication use.
    """
    try:
        data = request.get_json()
        compound_id = data["compound_id"]
        working_directory = os.path.expanduser(data["working_directory"])

        output_path = os.path.join(working_directory, "figures", f"{compound_id}_fragments.csv")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Dummy content for now
        df = pd.DataFrame({
            "mz": [100.1, 150.2, 200.3],
            "intensity": [5000, 7000, 6500]
        })
        df.to_csv(output_path, index=False)

        return jsonify({"message": f"Exported fragment peaks to {output_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@data_bp.route('/save_plots', methods=['POST'])
def save_plots():
    """
    Save a compound summary plot PDF to disk (currently a dummy file).

    Request JSON
    ------------
    compound_id : str
        Compound identifier used to name the output file.
    working_directory : str
        Working directory where `figures/` will be created if missing.

    Returns
    -------
    flask.Response
        JSON response:
        - 200: {"message": "Saved summary plot PDF to <.../figures/{compound_id}_summary.pdf>"}
        - 500: {"error": "..."} on unexpected errors

    Side Effects
    ------------
    Creates `<working_directory>/figures/` and writes `{compound_id}_summary.pdf`.

    Notes
    -----
    The current implementation writes a plain text file with a `.pdf` extension
    for scaffolding. Replace with actual PDF plotting/export code (e.g., matplotlib)
    for publication-ready figures.
    """

    try:
        data = request.get_json()
        compound_id = data["compound_id"]
        working_directory = os.path.expanduser(data["working_directory"])

        output_path = os.path.join(working_directory, "figures", f"{compound_id}_summary.pdf")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Dummy file creation
        with open(output_path, "w") as f:
            f.write("Summary plot for " + compound_id)

        return jsonify({"message": f"Saved summary plot PDF to {output_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
