import json
import os
import urllib.error
import urllib.request
from typing import Optional
from uuid import uuid4


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def _request(method: str, path: str, body: Optional[dict] = None, token: Optional[str] = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(payload)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8") or "{}"
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {"raw": payload}
        return exc.code, parsed


def _get(path: str, token: Optional[str] = None):
    return _request("GET", path, token=token)


def _post(path: str, body: dict, token: Optional[str] = None):
    return _request("POST", path, body=body, token=token)


def _login(email: str, password: str):
    return _post("/api/auth/login", {"email": email, "password": password})


def test_login_enroll_grade_flow():
    # Ensure gateway is reachable (indirectly verifies the stack is up).
    status, ping_payload = _get("/api/ping")
    assert status == 200, ping_payload

    # Student login to get JWT.
    status, student_payload = _login("student@example.com", "password")
    assert status == 200, student_payload
    student_token = student_payload["access_token"]
    student_id = student_payload["user_id"]

    # Fetch courses and pick one deterministically.
    status, courses_payload = _get("/api/courses")
    assert status == 200, courses_payload
    courses = courses_payload.get("courses", [])
    assert courses, "Expected seeded courses from init.sql"
    course_id = courses[0]["id"]

    # Check current enrollments; avoid duplicate enroll attempts across runs.
    status, enrollment_payload = _get("/api/enrollments/my", token=student_token)
    assert status == 200, enrollment_payload
    already_enrolled = any(e["course_id"] == course_id for e in enrollment_payload["enrollments"])
    if not already_enrolled:
        status, enroll_resp = _post("/api/enrollments/", {"course_id": course_id}, token=student_token)
        assert status == 200, enroll_resp

    # Faculty issues a grade for the student/course with a unique term to avoid conflicts.
    status, faculty_payload = _login("faculty@example.com", "password")
    assert status == 200, faculty_payload
    faculty_token = faculty_payload["access_token"]
    term = f"TestTerm-{uuid4().hex[:8]}"
    status, grade_payload = _post(
        "/api/grades/",
        {
            "student_id": student_id,
            "course_id": course_id,
            "term": term,
            "grade": "A",
        },
        token=faculty_token,
    )
    assert status == 200, grade_payload

    # Student fetches grades and sees the newly posted term.
    status, grades_payload = _get("/api/grades/my", token=student_token)
    assert status == 200, grades_payload
    grades = grades_payload.get("grades", [])
    assert any(g["term"] == term and g["course_id"] == course_id for g in grades), grades
