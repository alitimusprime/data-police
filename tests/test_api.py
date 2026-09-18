from fastapi.testclient import TestClient

from data_police.api import app
from data_police.config import settings


def client():
    c = TestClient(app)
    c.__enter__()
    c.headers.update({"X-DP-Request": "1"})
    response = c.post(
        "/api/auth/login", json={"email": settings.admin_email, "password": settings.admin_password}
    )
    assert response.status_code == 200
    return c


def test_auth_required():
    with TestClient(app) as c:
        assert c.get("/api/overview").status_code == 401
        assert c.get("/api/health").status_code == 200


def test_origin_and_request_header():
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"email": "x", "password": "x"}).status_code == 403
        assert (
            c.post(
                "/api/auth/login",
                headers={"X-DP-Request": "1", "Origin": "https://attacker.example"},
                json={"email": "x", "password": "x"},
            ).status_code
            == 403
        )


def test_rule_lifecycle_and_validation():
    with client() as c:
        r = c.post(
            "/api/rules",
            json={
                "dataset_id": "raw_orders",
                "name": "Custom positive amount",
                "kind": "range",
                "column": "amount",
                "params": {"min": 0},
            },
        )
        assert r.status_code == 201, r.text
        identifier = r.json()["id"]
        assert c.patch(f"/api/rules/{identifier}", json={"enabled": False}).status_code == 200
        updated = next(x for x in c.get("/api/rules").json() if x["id"] == identifier)
        assert not updated["enabled"] and updated["version"] == 2
        assert (
            c.post(
                "/api/rules",
                json={"dataset_id": "raw_orders", "name": "Unsafe code", "kind": "python", "column": "x"},
            ).status_code
            == 422
        )


def test_nonexistent_entities_and_no_secret_leak():
    with client() as c:
        assert c.get("/api/datasets/not_here").status_code == 404
        assert c.get("/api/incidents/99999").status_code == 404
        payload = c.get("/api/settings").text
        assert settings.admin_password not in payload and settings.session_secret not in payload
        assert c.get("/api/overview").status_code == 200
        assert c.get("/api/lineage").status_code == 200
