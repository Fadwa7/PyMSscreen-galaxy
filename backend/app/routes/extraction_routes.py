import os
import uuid
from multiprocessing import Process

from flask import Blueprint, request, jsonify

from app.utils import resolve_path
from app.jobs.job_store import create_job, load_status
from app.routes.extract_prescreen_mspgen import (
    _extract_data_impl,
    _prescreen_impl,
    _run_pipeline_background,
)

extraction_bp = Blueprint("extraction", __name__)

@extraction_bp.route("/start_extract_prescreen", methods=["POST"])
def start_extract_prescreen():
    body = request.get_json(force=True)
    working_dir = resolve_path(body.get("working_directory", ""))

    if not os.path.isdir(working_dir):
        return jsonify({"error": f"Invalid working directory: {working_dir}"}), 400

    job_id = uuid.uuid4().hex[:12]
    create_job(working_dir, job_id)

    # spawn background process
    p = Process(target=_run_pipeline_background, args=(job_id, working_dir))
    p.daemon = True
    p.start()

    return jsonify({"job_id": job_id})


@extraction_bp.route("/job_status", methods=["GET"])
def job_status():
    working_dir = resolve_path(request.args.get("working_directory", ""))
    job_id = request.args.get("job_id", "")
    if not working_dir or not job_id:
        return jsonify({"error": "Missing working_directory or job_id", "state": "invalid"}), 400

    data = load_status(working_dir)
    job = data.get("jobs", {}).get(job_id)
    if not job:
        return jsonify({"id": job_id, "state": "unknown", "progress": 0,
                        "message": "Job not found"}), 200
    return jsonify(job)

    
@extraction_bp.route("/extract_data", methods=["POST"])
def extract_data():
    """
    Extract MS1 EIC traces and MS2 spectra matched to compound m/z targets.

    This endpoint loads:
    - `state.json` (mzML files, tags, adducts)
    - `extract_config.yaml` (tolerances and thresholds)
    - `comprehensive_table.csv` (targets created by `/generate_table`)

    For each mzML file:
    - Loads spectra (pyOpenMS)
    - Builds MS1 EIC by summing intensities within a fine ppm window
    - Matches MS2 spectra whose precursor m/z is within a coarse Da window
    - Writes per-compound CSV outputs into `<working_directory>/ms2_spectra/`

    Request JSON
    ------------
    working_directory : str
        Working directory containing state/config/table files.

    Returns
    -------
    flask.Response
        JSON response:
        - 200: {"status": "success", "message": "Extraction complete"}
        - 500: {"status": "error", "message": "<exception>"} on failure

    Side Effects
    ------------
    Creates (if needed) the directory `<working_directory>/ms2_spectra/` and writes:
    - `{ID}_{adduct}_{tag}_EIC.csv`
        Columns: rt (min), intensity
    - `{ID}_{adduct}_{tag}_MS2.csv` (when matches exist)
        Columns: scan_id, ms2_rt (min), ms2_intensity, peak_list

    Notes
    -----
    - RTs are converted from seconds to minutes.
    - `peak_list` is stored as a semicolon-separated "m/z:intensity" string.
    - Compound rows are filtered to match both `tag` and `adduct` for each mzML file.
    """
    req = request.get_json(force=True)
    wd  = resolve_path(req.get("working_directory"))
    job = req.get("job_id")
    res = _extract_data_impl(wd, job_id=job)
    code = 200 if res.get("status") == "success" else 500
    return jsonify(res), code

@extraction_bp.route("/prescreen_data", methods=["POST"])
def prescreen_data():
    """
    Prescreen extracted MS1/MS2 outputs and write a QA summary table.

    Reads the YAML config for thresholds and evaluates per-compound flags based on:
    - Existence of MS1 EIC and MS2 files
    - MS1 maximum intensity > MS1 threshold
    - MS1 maximum intensity above noise (mean * S/N ratio)
    - Presence of MS2 peaks above MS2 threshold
    - Alignment: MS2 RT near MS1 peak RT within tolerance

    Request JSON
    ------------
    working_directory : str
        Working directory containing `extract_config.yaml`, `comprehensive_table.csv`,
        and the `ms2_spectra/` directory produced by `/extract_data`.

    Returns
    -------
    flask.Response
        JSON response:
        - 200: {"status": "success", "message": "Prescreening complete."}
        - 500: {"status": "error", "message": "<exception>"} on failure

    Side Effects
    ------------
    Writes `summary_table.csv` into `working_directory` with QA and alignment flags.

    Output Columns
    --------------
    ID, adduct, tag,
    qa_ms1_exists, qa_ms1_good_int, qa_ms1_above_noise,
    qa_ms2_exists, qa_ms2_good_int, qa_ms2_near,
    qa_pass, alignment, ms2_sel,
    ms1_rt, ms2_rt

    Notes
    -----
    - `qa_pass` is True only if all six QA flags are True.
    - Alignment is set False when MS2 is missing or RT proximity fails.
    """

    req = request.get_json(force=True)
    wd  = resolve_path(req.get("working_directory"))
    job = req.get("job_id")
    res = _prescreen_impl(wd, job_id=job)
    code = 200 if res.get("status") == "success" else 500
    return jsonify(res), code
