from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "product-service"


def test_create_and_get_product():
    create_resp = client.post(
        "/products",
        json={"name": "CI Test Widget", "price": 9.99, "stock": 50},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "CI Test Widget"
    assert created["price"] == 9.99

    get_resp = client.get(f"/products/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["stock"] == 50


def test_get_nonexistent_product_returns_404():
    response = client.get("/products/999999")
    assert response.status_code == 404


def test_list_products_returns_array():
    response = client.get("/products")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
