def test_app_imports():
    from web_app import app
    assert app is not None


def test_key_blueprints_registered():
    from web_app import app

    routes = [rule.rule for rule in app.url_map.iter_rules()]

    assert "/save_state" in routes
    assert "/load_state" in routes
    assert "/generate_table" in routes
    assert "/start_extract_prescreen" in routes
    assert "/job_status" in routes
    assert "/load_comprehensive_table" in routes