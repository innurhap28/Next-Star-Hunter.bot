from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "next-star-hunter"}


def test_health_content_type_is_json():
    response = client.get("/health")

    assert response.headers["content-type"].startswith("application/json")
