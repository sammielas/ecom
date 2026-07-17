from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "user-service"


def test_create_and_get_user():
    create_resp = client.post(
        "/users",
        json={"username": "testuser_ci", "email": "testuser_ci@example.com"},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["username"] == "testuser_ci"
    assert "id" in created

    get_resp = client.get(f"/users/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == "testuser_ci@example.com"


def test_get_nonexistent_user_returns_404():
    response = client.get("/users/999999")
    assert response.status_code == 404
