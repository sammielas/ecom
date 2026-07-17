from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def _mock_response(status_code, json_data):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    return mock


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "order-service"


@patch("app.httpx.get")
def test_create_order_success(mock_get):
    # First call checks the user, second call checks the product
    mock_get.side_effect = [
        _mock_response(200, {"id": 1, "username": "alice", "email": "a@x.com"}),
        _mock_response(200, {"id": 1, "name": "Widget", "price": 10.0, "stock": 5}),
    ]

    response = client.post(
        "/orders", json={"user_id": 1, "product_id": 1, "quantity": 3}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["total_price"] == 30.0
    assert body["status"] == "CONFIRMED"


@patch("app.httpx.get")
def test_create_order_invalid_user_returns_400(mock_get):
    mock_get.return_value = _mock_response(404, {"detail": "User does not exist"})

    response = client.post(
        "/orders", json={"user_id": 999, "product_id": 1, "quantity": 1}
    )
    assert response.status_code == 400


@patch("app.httpx.get")
def test_create_order_user_service_down_returns_503(mock_get):
    import httpx

    mock_get.side_effect = httpx.RequestError("connection refused")

    response = client.post(
        "/orders", json={"user_id": 1, "product_id": 1, "quantity": 1}
    )
    assert response.status_code == 503
