import os
import json
import yaml
from flask import Blueprint, request, jsonify

from app.utils import get_working_dir

state_bp = Blueprint("state", __name__)


@state_bp.route('/save_state', methods=['POST'])
def save_state():
    """
    Persist application state (input files, tags, adducts) to a JSON file.

    Expects a JSON body containing a `working_directory`, a `compound_csv`
    filename/path (relative to the working directory), and a list of `mzml_files`
    entries with file/tag/adduct metadata. The route writes `state.json` into
    the working directory.

    Request JSON
    ------------
    working_directory : str, optional
        Base directory for resolving relative file paths. Defaults to `"."`.
    compound_csv : str
        Path or filename of the compound CSV (typically relative to working_directory).
    mzml_files : list of dict, optional
        Each dict may include:
        - file : str
            mzML filename/path (typically relative to working_directory).
        - tag : str, optional
            A grouping label used later for matching rows.
        - adduct : str, optional
            Adduct string key (e.g., "[M+H]+") used to compute m/z.

    Returns
    -------
    flask.Response
        JSON response:
        - 200: {"message": "..."} on success
        - 400: {"error": "..."} if working_directory is invalid
        - 500: {"error": "..."} for unexpected errors

    Side Effects
    ------------
    Writes a file `state.json` under `working_directory`.

    Notes
    -----
    Paths are normalized by joining each provided relative path with the
    expanded `working_directory`.
    """
    try:
        data = request.get_json(force=True) or {}
        print("Save request data:", data)

        # -- 1) Working directory
        working_directory = get_working_dir(data.get("working_directory"))
        if not os.path.isdir(working_directory):
            return jsonify({"error": "Invalid working directory"}), 400
        working_directory = os.path.normpath(working_directory)

        # -- 2) Compound CSV (absolute or relative to working_directory)
        compound_csv_in = (data.get("compound_csv") or "").strip()
        if compound_csv_in:
            compound_csv = (compound_csv_in if os.path.isabs(compound_csv_in)
                            else os.path.join(working_directory, compound_csv_in))
            compound_csv = os.path.normpath(os.path.expanduser(compound_csv))
        else:
            compound_csv = ""

        # -- 3) mzML files (each entry can be absolute or relative)
        mzml_files = []
        for f in (data.get("mzml_files") or []):
            raw_path = (f.get("file") or "").strip()
            if not raw_path:
                continue
            resolved = raw_path if os.path.isabs(raw_path) else os.path.join(working_directory, raw_path)
            mzml_files.append({
                "file": os.path.normpath(os.path.expanduser(resolved)),
                "tag": f.get("tag", "")
            })

        # -- 4) Global adduct selections (clean + dedupe, order-preserving)
        def clean_list(vals):
            if not isinstance(vals, list):
                return []
            seen, out = set(), []
            for v in vals:
                if isinstance(v, str):
                    s = v.strip()
                    if s and s not in seen:
                        seen.add(s)
                        out.append(s)
            return out

        adducts = {
            "positive": clean_list(data.get("positive_adducts", [])),
            "negative": clean_list(data.get("negative_adducts", []))
        }

        # -- 5) Assemble final state
        state = {
            "working_directory": working_directory,
            "compound_csv": compound_csv,
            "mzml_files": mzml_files,
            "adducts": adducts
        }

        # -- 6) Persist state.json
        state_path = os.path.join(working_directory, "state.json")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        return jsonify({
            "status": "ok",
            "message": "State saved successfully!",
            "state_path": state_path,
            "mzml_count": len(mzml_files)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@state_bp.route('/load_state', methods=['POST'])
def load_state():
    """
    Load previously saved application state from `state.json`.

    Expects a JSON body containing `working_directory`. The route reads
    `<working_directory>/state.json` and returns it as JSON.

    Request JSON
    ------------
    working_directory : str, optional
        Directory containing `state.json`. Defaults to `"."`.

    Returns
    -------
    flask.Response
        JSON response:
        - 200: The parsed contents of `state.json`
        - 404: {"error": "No saved state found."} if missing
        - 500: {"error": "..."} for unexpected errors

    Side Effects
    ------------
    None.
    """
    try:
        data = request.get_json()
        working_directory = get_working_dir(data.get("working_directory"))
        state_path = os.path.join(working_directory, "state.json")

        if not os.path.exists(state_path):
            return jsonify({"error": "No saved state found."}), 404

        with open(state_path, "r") as f:
            state = json.load(f)

        return jsonify(state)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@state_bp.route('/save_extract_config', methods=['POST'])
def save_extract_config():
    """
    Save extraction and prescreen parameters to `extract_config.yaml`.

    Expects numeric thresholds/windows in the request JSON. The endpoint writes
    a structured YAML configuration under the working directory.

    Request JSON
    ------------
    working_directory : str, optional
        Directory to write `extract_config.yaml`. Defaults to `"."`.
    ms1_coarse_error : str or number
        Coarse MS1 tolerance in Da (stored as "<value> Da").
    ms1_fine_error : str or number
        Fine MS1 tolerance in ppm (stored as "<value> ppm").
    ms1_eic_window : str or number
        EIC window in Da (stored as "<value> Da").
    retention_time_window : str or number
        RT window in minutes (stored as "<value> min").
    ms1_intensity_threshold : str or number
        Minimum MS1 intensity threshold.
    ms2_intensity_threshold : str or number
        Minimum MS2 intensity threshold.
    ms1_sn_ratio : str or number
        Signal-to-noise ratio threshold used for MS1.
    retention_time_delay : str or number
        Allowed RT shift (stored as "<value> min").

    Returns
    -------
    flask.Response
        JSON response:
        - 200: {"message": "Saved to <.../extract_config.yaml>"}
        - 400: {"error": "..."} if working_directory does not exist
        - 500: {"error": "..."} for unexpected errors

    Side Effects
    ------------
    Writes `extract_config.yaml` under `working_directory`.
    """
    try:
        data = request.get_json()
        working_directory = get_working_dir(data.get("working_directory"))
        print("Saving extraction config to:", working_directory)

        if not os.path.isdir(working_directory):
            return jsonify({"error": f"Working directory not found: {working_directory}"}), 400

        # Build structured config
        config_data = {
            "tolerance": {
                "ms1 coarse": f"{data['ms1_coarse_error']} Da",
                "ms1 fine": f"{data['ms1_fine_error']} ppm",
                "eic": f"{data['ms1_eic_window']} Da",
                "rt": f"{data['retention_time_window']} min"
            },
            "prescreen": {
                "ms1_int_thresh": float(data["ms1_intensity_threshold"]),
                "ms2_int_thresh": float(data["ms2_intensity_threshold"]),
                "s2n": float(data["ms1_sn_ratio"]),
                "ret_time_shift_tol": f"{data['retention_time_delay']} min"
            }
        }

        config_path = os.path.join(working_directory, "extract_config.yaml")
        with open(config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        return jsonify({"message": f"Saved to {config_path}"})

    except Exception as e:
        print(f" Error saving extract_config.yaml: {e}")
        return jsonify({"error": str(e)}), 500
    
@state_bp.route('/load_extraction_config', methods=['GET'])
def load_extraction_config():
    # Same project folder as all other routes
    working_dir = get_working_dir(request.args.get('working_directory'))
    config_path = os.path.join(working_dir, 'extract_config.yaml')

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        # save_extract_config stores this under "prescreen" as e.g. "0.5 min"
        raw = config['prescreen']['ret_time_shift_tol']
        ret_time_shift_tol = float(str(raw).replace('min', '').strip())
        return jsonify({'ret_time_shift_tol': ret_time_shift_tol})
    
    except Exception as e:
        print(f"Error loading extract_config.yaml: {e}")
        return jsonify({'ret_time_shift_tol': 0.5})