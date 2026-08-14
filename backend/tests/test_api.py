import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(mock_env):
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "adb_available" in body
    assert body["mock"] is True


def test_devices_lists_mock_device(client):
    r = client.get("/api/devices")
    assert r.status_code == 200
    serials = [d["serial"] for d in r.json()["devices"]]
    assert "abc123" in serials


def test_status_returns_components(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    components = r.json()["components"]
    assert any(c["id"] == "ksu" for c in components)


def test_components_enum_endpoint(client):
    r = client.get("/api/components")
    assert r.status_code == 200
    assert "ksu" in r.json()["components"]


def test_exec_runs_mock_command(client):
    r = client.post("/api/exec", json={"command": ["version"]})
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"


def test_websocket_streams_root(client):
    with client.websocket_connect("/ws/run?command=root") as ws:
        lines = []
        while True:
            msg = ws.receive_json()
            if msg.get("type") == "done":
                break
            lines.append(msg)
    assert any("HOLDER" in m.get("line", "") for m in lines if m.get("type") == "line")
