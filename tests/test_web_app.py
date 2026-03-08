import chess
import pytest

import web_app


@pytest.fixture(autouse=True)
def clean_sessions(monkeypatch):
    with web_app.STORE_LOCK:
        web_app.SESSIONS.clear()

    def deterministic_bridge_move(state, _depth):
        move = next(iter(state.board.legal_moves), None)
        if move is None:
            return None, None, False
        return move, "test-fallback", True

    monkeypatch.setattr(web_app, "bridge_move", deterministic_bridge_move)
    yield

    with web_app.STORE_LOCK:
        web_app.SESSIONS.clear()


@pytest.fixture
def app_client():
    web_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with web_app.app.test_client() as client:
        yield client


def test_healthz(app_client):
    response = app_client.get("/healthz")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "active_sessions" in data


def test_session_isolation():
    web_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")

    with web_app.app.test_client() as c1, web_app.app.test_client() as c2:
        start = c1.post("/api/new", json={"player_color": "white", "depth": 3})
        assert start.status_code == 200
        assert start.get_json()["ok"] is True

        move = c1.post("/api/move", json={"from": "e2", "to": "e4"})
        assert move.status_code == 200
        assert move.get_json()["ok"] is True

        s1 = c1.get("/api/state").get_json()
        s2 = c2.get("/api/state").get_json()

        assert s1["ply_count"] == 2
        assert s1["status"] in {"ongoing", "check"}
        assert s2["status"] == "not_started"
        assert s2["ply_count"] == 0


def test_undo_full_move(app_client):
    start = app_client.post("/api/new", json={"player_color": "white", "depth": 2})
    assert start.status_code == 200

    move = app_client.post("/api/move", json={"from": "e2", "to": "e4"})
    assert move.status_code == 200
    assert move.get_json()["state"]["ply_count"] == 2

    undo = app_client.post("/api/undo", json={})
    assert undo.status_code == 200
    data = undo.get_json()["state"]
    assert data["ply_count"] == 0
    assert data["turn"] == "white"


def test_reject_cross_origin(app_client):
    response = app_client.post(
        "/api/new",
        json={"player_color": "white", "depth": 2},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    body = response.get_json()
    assert body["ok"] is False


def test_requires_json_body(app_client):
    response = app_client.post("/api/new", data="not-json", headers={"Content-Type": "text/plain"})
    assert response.status_code == 415
    body = response.get_json()
    assert body["ok"] is False
