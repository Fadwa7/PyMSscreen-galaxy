import os
import uuid
from multiprocessing import Process

from flask import Blueprint, request, jsonify

from app.utils import get_working_dir
from app.jobs.job_store import create_job, load_status
from app.routes.extract_prescreen_mspgen import _run_pipeline_background

extraction_bp = Blueprint("extraction", __name__)

@extraction_bp.route("/start_extract_prescreen", methods=["POST"])
def start_extract_prescreen():
    body = request.get_json(force=True)
    working_dir = get_working_dir(body.get("working_directory"))

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
    working_dir = get_working_dir(request.args.get("working_directory"))
    job_id = request.args.get("job_id", "")
    if not working_dir or not job_id:
        return jsonify({"error": "Missing working_directory or job_id", "state": "invalid"}), 400

    data = load_status(working_dir)
    job = data.get("jobs", {}).get(job_id)
    if not job:
        return jsonify({"id": job_id, "state": "unknown", "progress": 0,
                        "message": "Job not found"}), 200
    return jsonify(job)

    
