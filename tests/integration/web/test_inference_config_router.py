from __future__ import annotations


def test_get_inference_config_returns_full_dto(client):
    r = client.get("/api/config/inference")
    assert r.status_code == 200
    body = r.json()
    for section in ("model", "detection", "detection_roi", "tracking", "speed", "analysis", "queue", "vehicle_pce"):
        assert section in body


def test_put_inference_config_updates_yaml(client, container):
    body = client.get("/api/config/inference").json()
    body["detection"]["confidence"] = 0.42
    body["model"]["imgsz"] = 1280

    r = client.put("/api/config/inference", json=body)
    assert r.status_code == 200
    new_body = r.json()
    assert new_body["detection"]["confidence"] == 0.42
    assert new_body["model"]["imgsz"] == 1280

    # Container hot-reloaded.
    assert container.inference_config.detection.confidence == 0.42
    assert container.inference_config.model.imgsz == 1280
    # Detector cache reset (next call will rebuild).
    assert container._detector is None


def test_put_inference_config_400_on_invalid_imgsz(client):
    body = client.get("/api/config/inference").json()
    body["model"]["imgsz"] = 957  # not multiple of 32
    r = client.put("/api/config/inference", json=body)
    assert r.status_code == 422  # Pydantic field validator → 422


def test_put_inference_config_400_on_out_of_range_confidence(client):
    body = client.get("/api/config/inference").json()
    body["detection"]["confidence"] = 1.5
    r = client.put("/api/config/inference", json=body)
    assert r.status_code == 422


def test_reset_inference_config_returns_defaults(client, container):
    body = client.get("/api/config/inference").json()
    body["detection"]["confidence"] = 0.99
    client.put("/api/config/inference", json=body)
    assert container.inference_config.detection.confidence == 0.99

    r = client.post("/api/config/inference/reset")
    assert r.status_code == 200
    # Default confidence từ InferenceConfig.DetectionConfig() = 0.25
    assert r.json()["detection"]["confidence"] == 0.25
    assert container.inference_config.detection.confidence == 0.25


def test_get_schema_returns_metadata(client):
    r = client.get("/api/config/inference/schema")
    assert r.status_code == 200
    schema = r.json()
    assert "model.imgsz" in schema
    assert "detection.confidence" in schema
    assert schema["model.imgsz"]["type"] == "integer"
