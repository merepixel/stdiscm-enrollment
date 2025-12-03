import json
import os
import urllib.request


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def _get(path: str):
    with urllib.request.urlopen(f"{BASE_URL}{path}") as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body)


def test_ping():
    status, payload = _get("/api/ping")
    assert status == 200
    assert payload.get("status") == "ok"


def test_smoke_courses():
    status, payload = _get("/api/smoke/courses")
    assert status == 200
    assert payload.get("status") == "ok"
    assert isinstance(payload.get("courses"), list)
