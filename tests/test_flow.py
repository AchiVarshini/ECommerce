import os

os.environ["DATABASE_URL"] = f"sqlite:////tmp/smartcart-pytest-{os.getpid()}.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_customer_journey(client):
    registered = client.post("/register", json={
        "name": "Taylor Test", "email": "taylor.pytest@example.com",
        "password": "TestPass123!", "age": 29, "city": "Austin",
    })
    assert registered.status_code == 201
    customer_id = registered.json()["customer_id"]

    login = client.post("/login", json={"email": "taylor.pytest@example.com", "password": "TestPass123!"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    products = client.get("/products").json()
    assert len(products) >= 50
    product_id = next(product["product_id"] for product in products if product["stock"] > 0)
    assert len(client.get(f"/recommendations/{customer_id}", headers=headers).json()["recommendations"]) == 5
    assert 0 <= client.post("/predict-purchase", json={"customer_id": customer_id, "product_id": product_id}, headers=headers).json()["purchase_probability"] <= 1
    assert client.get(f"/customer-segment/{customer_id}", headers=headers).status_code == 200
    assert client.post("/orders", json={}, headers=headers).status_code == 400
    assert client.post("/cart", json={"customer_id": customer_id, "product_id": product_id, "quantity": 1}, headers=headers).status_code == 200
    order = client.post("/orders", json={"payment_method": "Card"}, headers=headers)
    assert order.status_code == 201
    assert order.json()["total"] > 0
    dashboard = client.get(f"/customer-dashboard/{customer_id}", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["total_orders"] == 1
    assert dashboard.json()["recommendations"]


def test_auth_validation_and_admin_access(client):
    assert client.get("/cart/1").status_code == 401
    assert client.post("/register", json={
        "name": "Invalid Age", "email": "invalid-age@example.com",
        "password": "TestPass123!", "age": 12, "city": "Austin",
    }).status_code == 422

    shopper = client.post("/login", json={"email": "customer1@smartcart.com", "password": "SmartCart123!"})
    shopper_headers = {"Authorization": f"Bearer {shopper.json()['access_token']}"}
    assert client.get("/admin/sales-summary", headers=shopper_headers).status_code == 403

    admin = client.post("/login", json={"email": "admin@smartcart.com", "password": "Admin123!"})
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    for endpoint in ["sales-summary", "top-products", "top-customers", "category-sales", "customer-segments", "low-stock-products", "eda", "data-quality"]:
        assert client.get(f"/admin/{endpoint}", headers=admin_headers).status_code == 200


def test_duplicate_email_and_stock_validation(client):
    duplicate = client.post("/register", json={
        "name": "Duplicate Shopper", "email": "customer1@smartcart.com",
        "password": "TestPass123!", "age": 31, "city": "Denver",
    })
    assert duplicate.status_code == 409

    login = client.post("/login", json={"email": "customer1@smartcart.com", "password": "SmartCart123!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    product_id = client.get("/products").json()[0]["product_id"]
    response = client.post("/cart", json={"customer_id": 1, "product_id": product_id, "quantity": 100}, headers=headers)
    assert response.status_code in (409, 422)


def test_customer_product_cart_and_order_crud(client):
    admin = client.post("/login", json={"email": "admin@smartcart.com", "password": "Admin123!"})
    admin_headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}
    customer_response = client.post("/register", json={
        "name": "Journey Shopper", "email": "journey.shopper@example.com",
        "password": "TestPass123!", "age": 34, "city": "Portland",
    })
    customer_id = customer_response.json()["customer_id"]
    token = client.post("/login", json={"email": "journey.shopper@example.com", "password": "TestPass123!"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/customers", headers=admin_headers).status_code == 200
    assert client.get(f"/customers/{customer_id}", headers=headers).status_code == 200
    assert client.put(f"/customers/{customer_id}", json={"city": "Seattle"}, headers=headers).json()["city"] == "Seattle"
    assert client.get("/customers/888888", headers=admin_headers).status_code == 404

    product = client.post("/products", json={
        "product_name": "Journey Desk Lamp", "category": "Home", "price": 45.5,
        "rating": 4.7, "stock": 5, "discount": 10,
    }, headers=admin_headers)
    assert product.status_code == 201
    product_id = product.json()["product_id"]
    assert client.post("/products", json={"product_name": "Forbidden", "category": "Home", "price": 10}, headers=headers).status_code == 403
    assert client.get(f"/products/{product_id}").status_code == 200
    assert len(client.get("/products", params={"search": "Journey Desk"}).json()) == 1
    assert client.put(f"/products/{product_id}", json={"price": 49}, headers=admin_headers).json()["price"] == 49
    assert client.post(f"/products/{product_id}/view", headers=headers).status_code == 200
    assert client.post(f"/wishlist/{product_id}", headers=headers).status_code == 200
    assert client.post("/cart", json={"customer_id": customer_id, "product_id": product_id, "quantity": 2}, headers=headers).status_code == 200
    cart = client.get(f"/cart/{customer_id}", headers=headers).json()
    cart_id = cart["items"][0]["cart_id"]
    assert client.put(f"/cart/{cart_id}", json={"quantity": 1}, headers=headers).status_code == 200
    assert client.delete(f"/cart/{cart_id}", headers=headers).status_code == 204
    assert client.post("/cart", json={"customer_id": customer_id, "product_id": product_id, "quantity": 1}, headers=headers).status_code == 200

    order = client.post("/orders", json={"payment_method": "Card"}, headers=headers)
    order_id = order.json()["order_id"]
    assert client.get("/orders", headers=headers).status_code == 200
    assert client.get(f"/orders/{order_id}", headers=headers).status_code == 200
    assert client.get(f"/customers/{customer_id}/orders", headers=headers).status_code == 200
    assert client.get("/products/888888").status_code == 404

    unused_product = client.post("/products", json={
        "product_name": "Unused Sample", "category": "Home", "price": 15,
    }, headers=admin_headers).json()
    assert client.delete(f"/products/{product_id}", headers=admin_headers).status_code == 409
    assert client.delete(f"/customers/{customer_id}", headers=admin_headers).status_code == 204
    assert client.delete(f"/products/{unused_product['product_id']}", headers=admin_headers).status_code == 204