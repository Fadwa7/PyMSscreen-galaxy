"""Step 1: /load_extraction_config must return the saved RT tolerance."""
import yaml
from flask import Flask

from app.routes.state_routes import state_bp

SAVE_BODY = {
    "ms1_coarse_error": 0.5, "ms1_fine_error": 10, "ms1_eic_window": 0.01,
    "retention_time_window": 0.5, "ms1_intensity_threshold": 10000,
    "ms2_intensity_threshold": 1000, "ms1_sn_ratio": 3,
}


def _client():
    app = Flask(__name__)
    app.register_blueprint(state_bp)
    return app.test_client()


def _load(client, wd):
    r = client.get("/load_extraction_config", query_string={"working_directory": str(wd)})
    assert r.status_code == 200
    return r.get_json()["ret_time_shift_tol"]


def test_returns_value_saved_by_ui(tmp_path):
    c = _client()
    r = c.post("/save_extract_config",
               json={**SAVE_BODY, "working_directory": str(tmp_path), "retention_time_delay": 0.3})
    assert r.status_code == 200
    assert _load(c, tmp_path) == 0.3


def test_plain_number_in_yaml(tmp_path):
    (tmp_path / "extract_config.yaml").write_text(yaml.safe_dump({"prescreen": {"ret_time_shift_tol": 0.2}}))
    assert _load(_client(), tmp_path) == 0.2


def test_falls_back_to_default(tmp_path):
    c = _client()
    assert _load(c, tmp_path) == 0.5                                   # no config file
    (tmp_path / "extract_config.yaml").write_text("tolerance: {}\n")    # no prescreen section
    assert _load(c, tmp_path) == 0.5
    (tmp_path / "extract_config.yaml").write_text(
        yaml.safe_dump({"prescreen": {"ret_time_shift_tol": "abc min"}}))  # unparsable
    assert _load(c, tmp_path) == 0.5
