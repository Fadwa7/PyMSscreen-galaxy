"""Step 10: every route uses the project folder, whatever folder the page sends."""
import yaml
from flask import Flask

from app.routes.state_routes import state_bp
from app.utils import get_working_dir


def test_get_working_dir_ignores_requested(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(tmp_path))
    assert get_working_dir("/etc") == str(tmp_path)
    assert get_working_dir("../../somewhere") == str(tmp_path)
    assert get_working_dir(None) == str(tmp_path)


def test_route_cannot_read_other_folder(tmp_path, monkeypatch):
    project = tmp_path / "project"
    other = tmp_path / "other"
    project.mkdir()
    other.mkdir()
    (project / "extract_config.yaml").write_text(yaml.safe_dump({"prescreen": {"ret_time_shift_tol": "0.3 min"}}))
    (other / "extract_config.yaml").write_text(yaml.safe_dump({"prescreen": {"ret_time_shift_tol": "0.9 min"}}))
    monkeypatch.setattr("app.config.BASE_WORKING_DIR", str(project))

    app = Flask(__name__)
    app.register_blueprint(state_bp)
    with app.test_client() as c:
        r = c.get("/load_extraction_config", query_string={"working_directory": str(other)})
    assert r.get_json() == {"ret_time_shift_tol": 0.3}      # project folder, not "other"
