def test_load_comprehensive_table_does_not_crash():
    from web_app import app

    client = app.test_client()
    response = client.get("/load_comprehensive_table")
    
    assert response.status_code != 500

def test_job_status_missing_params_returns_400():
    from web_app import app

    client = app.test_client()
    response = client.get("/job_status")

    assert response.status_code == 400