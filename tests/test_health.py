from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """Test that the /api/v1/health endpoint returns 200 and healthy status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "healthy"}


def test_root_endpoint(client: TestClient):
    """Test that the root endpoint returns metadata including health check path."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "app_name" in data
    assert "health_check" in data
    assert data["health_check"] == "/api/v1/health"
