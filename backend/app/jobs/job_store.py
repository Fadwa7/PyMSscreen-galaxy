# app/jobs/job_store.py
import json, os, tempfile

def _status_path(working_dir): return os.path.join(working_dir, "status.json")

def load_status(working_dir):
    path = _status_path(working_dir)
    if not os.path.exists(path): return {"jobs": {}}
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {"jobs": {}}

def save_status(working_dir, data):
    os.makedirs(working_dir, exist_ok=True)
    path = _status_path(working_dir)
    fd, tmp = tempfile.mkstemp(dir=working_dir, prefix=".status_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try: os.remove(tmp)
        except FileNotFoundError: pass

def create_job(working_dir, job_id, kind="extract_prescreen"):
    data = load_status(working_dir)
    data.setdefault("jobs", {})[job_id] = {
        "id": job_id, "kind": kind, "state": "queued",
        "progress": 0, "message": "Queued", "started_at": None, "finished_at": None,
    }
    save_status(working_dir, data)

def update_job(working_dir, job_id, **patch):
    data = load_status(working_dir)
    job = data.get("jobs", {}).get(job_id)
    if not job: return
    job.update(patch)
    save_status(working_dir, data)
