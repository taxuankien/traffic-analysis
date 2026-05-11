from __future__ import annotations


def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_models_list_empty_when_no_models(client, monkeypatch, tmp_path):
    monkeypatch.setenv("TRAFFIC_MODELS_DIR", str(tmp_path / "no_models"))

    import importlib

    from src.bootstrap import paths as paths_module

    importlib.reload(paths_module)

    # Need to also reload routers.system since it imports DEFAULT_MODELS_DIR at module level.
    from src.adapters.input.web.routers import system as system_router

    importlib.reload(system_router)

    # Re-create app so the reloaded router is mounted.
    from fastapi.testclient import TestClient

    from src.adapters.input.web.app import create_app

    new_app = create_app(container=client.app.state.container)
    new_client = TestClient(new_app)

    r = new_client.get("/api/system/models")
    assert r.status_code == 200
    assert r.json() == []

    importlib.reload(paths_module)  # restore
