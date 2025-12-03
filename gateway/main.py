import logging
import os
import sys
import time
from pathlib import Path

import grpc
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from sqlalchemy import create_engine, text
import httpx

BASE_DIR = Path(__file__).resolve().parent  # /app inside container
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
PROTO_PATH = BASE_DIR / "common" / "protos"
if str(PROTO_PATH) not in sys.path:
    sys.path.append(str(PROTO_PATH))

try:
    from common.protos import (
        auth_pb2,
        auth_pb2_grpc,
        course_pb2,
        course_pb2_grpc,
        enrollment_pb2,
        enrollment_pb2_grpc,
        grade_pb2,
        grade_pb2_grpc,
    )
except ImportError as exc:  # pragma: no cover - clarity for missing codegen
    raise ImportError(
        "Protos not generated or not on PYTHONPATH. Run `make protos` and rebuild the gateway."
    ) from exc

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/enrollment")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
AUTH_HTTP_TARGET = os.getenv("AUTH_HTTP_TARGET", "http://auth-service:8001")
CURRENT_TERM = os.getenv("CURRENT_TERM", "").strip()
CURRENT_ACADEMIC_YEAR = os.getenv("CURRENT_ACADEMIC_YEAR", "").strip()

AUTH_GRPC_TARGET = os.getenv("AUTH_GRPC_TARGET", "auth-service:50051")
COURSE_GRPC_TARGET = os.getenv("COURSE_GRPC_TARGET", "course-service:50052")
ENROLLMENT_GRPC_TARGET = os.getenv("ENROLLMENT_GRPC_TARGET", "enrollment-service:50053")
GRADE_GRPC_TARGET = os.getenv("GRADE_GRPC_TARGET", "grade-service:50054")

SERVICE_NAME = "gateway"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logger = logging.getLogger(SERVICE_NAME)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

auth_stub = auth_pb2_grpc.AuthServiceStub(grpc.insecure_channel(AUTH_GRPC_TARGET))
course_stub = course_pb2_grpc.CourseServiceStub(grpc.insecure_channel(COURSE_GRPC_TARGET))
enrollment_stub = enrollment_pb2_grpc.EnrollmentServiceStub(
    grpc.insecure_channel(ENROLLMENT_GRPC_TARGET)
)
grade_stub = grade_pb2_grpc.GradeServiceStub(grpc.insecure_channel(GRADE_GRPC_TARGET))

app = FastAPI(title="API Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BYPASS_PATHS = {"/api/auth/login", "/health", "/health/db", "/api/ping", "/api/smoke/courses", "/api/courses", "/api/courses/"}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except HTTPException as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        log_fn = logger.error if exc.status_code >= 500 else logger.warning
        log_fn(
            "%s %s -> %s (%.2f ms) detail=%s",
            request.method,
            request.url.path,
            exc.status_code,
            duration_ms,
            exc.detail,
        )
        raise
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception("%s %s -> unhandled error (%.2f ms)", request.method, request.url.path, duration_ms)
        raise
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s -> %s (%.2f ms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


def log_grpc_error(service: str, exc: grpc.RpcError):
    code = exc.code().name if hasattr(exc, "code") else "unknown"
    detail = exc.details() if hasattr(exc, "details") else str(exc)
    logger.error("%s gRPC call failed: code=%s detail=%s", service, code, detail)


def grpc_unavailable(service: str, exc: grpc.RpcError):
    log_grpc_error(service, exc)
    detail = exc.details() if hasattr(exc, "details") else str(exc)
    raise HTTPException(status_code=503, detail=f"{service} service temporarily unavailable: {detail}")


@app.middleware("http")
async def jwt_middleware(request: Request, call_next):
    request.state.user = None
    if request.url.path in BYPASS_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return await call_next(request)

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        request.state.user = {
            "user_id": payload.get("sub"),
            "user_number": payload.get("user_number"),
            "email": payload.get("email"),
            "role": payload.get("role"),
            "raw": payload,
        }
    except JWTError:
        # Invalid token; continue without user info. Protected endpoints will 401.
        request.state.user = None
    return await call_next(request)


def require_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@app.get("/health")
def health():
    return {"status": "ok", "service": "gateway"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "service": "gateway", "db": "connected"}
    except Exception as exc:  # pragma: no cover - simple probe
        return {"status": "error", "service": "gateway", "db": "unreachable", "detail": str(exc)}


@app.get("/api/ping")
def ping():
    return {"status": "ok", "service": "gateway", "host": os.getenv("HOSTNAME", "gateway")}


def enrollment_counts_by_course():
    """Return a mapping of course_id -> enrolled count for dynamic capacity display."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT course_id, COUNT(*) AS enrolled
                    FROM enrollment.enrollments
                    WHERE status = 'ENROLLED'
                    GROUP BY course_id
                    """
                )
            )
            return {str(row.course_id): row.enrolled for row in rows}
    except Exception:
        # If enrollment service DB is unreachable, fall back gracefully.
        return {}


@app.get("/api/smoke/courses")
def smoke_courses():
    """End-to-end smoke: gateway -> CourseService over gRPC."""
    try:
        resp = course_stub.ListCourses(course_pb2.ListCoursesRequest())
        courses = [
            {"id": c.id, "code": c.code, "title": c.title, "description": c.description, "capacity": c.capacity}
            for c in resp.courses
        ]
        return {"status": "ok", "via": "grpc", "courses": courses}
    except grpc.RpcError as exc:
        grpc_unavailable("course", exc)


# Auth routes
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.post("/login")
async def login_proxy(body: dict):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{AUTH_HTTP_TARGET}/login", json=body)
        except httpx.HTTPError as exc:
            logger.error("Auth HTTP proxy failed: %s", exc)
            raise HTTPException(status_code=503, detail="Auth service temporarily unavailable") from exc

    if resp.status_code != 200:
        logger.warning("Auth login returned %s: %s", resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@auth_router.get("/me")
def me(user=Depends(require_user)):
    return {"status": "ok", "user": user}


# Course routes
course_router = APIRouter(prefix="/api/courses", tags=["courses"])


@course_router.get("/")
def list_courses():
    try:
        resp = course_stub.ListCourses(course_pb2.ListCoursesRequest())
        counts = enrollment_counts_by_course()
        courses = []
        for c in resp.courses:
            term = getattr(c, "term", "")
            ay = getattr(c, "academic_year", "")
            if CURRENT_TERM and term != CURRENT_TERM:
                continue
            if CURRENT_ACADEMIC_YEAR and ay != CURRENT_ACADEMIC_YEAR:
                continue
            courses.append(
                {
                    "id": c.id,
                    "code": c.code,
                    "title": c.title,
                    "description": c.description,
                    "capacity": c.capacity,
                    "term": term,
                    "academic_year": ay,
                    "section": getattr(c, "section", ""),
                    "assigned_faculty_id": getattr(c, "assigned_faculty_id", ""),
                    "enrolled": counts.get(c.id, 0),
                    "available": max(c.capacity - counts.get(c.id, 0), 0),
                }
            )
        return {"courses": courses}
    except grpc.RpcError as exc:
        grpc_unavailable("course", exc)


@course_router.get("/assigned")
def list_my_courses(user=Depends(require_user)):
    """Return courses assigned to the authenticated faculty member."""
    if user.get("role") != "FACULTY":
        raise HTTPException(status_code=403, detail="FACULTY role required")
    try:
        resp = course_stub.ListFacultyCourses(
            course_pb2.ListFacultyCoursesRequest(faculty_id=user["user_id"])
        )
        counts = enrollment_counts_by_course()
        courses = [
            {
                "id": c.id,
                "code": c.code,
                "title": c.title,
                "description": c.description,
                "capacity": c.capacity,
                "term": getattr(c, "term", ""),
                "academic_year": getattr(c, "academic_year", ""),
                "section": getattr(c, "section", ""),
                "assigned_faculty_id": getattr(c, "assigned_faculty_id", ""),
                "enrolled": counts.get(c.id, 0),
                "available": max(c.capacity - counts.get(c.id, 0), 0),
            }
            for c in resp.courses
        ]
        return {"courses": courses}
    except grpc.RpcError as exc:
        grpc_unavailable("course", exc)


@course_router.get("/{course_id}")
def get_course(course_id: str):
    try:
        resp = course_stub.GetCourse(course_pb2.GetCourseRequest(id=course_id))
        c = resp.course
        counts = enrollment_counts_by_course()
        enrolled = counts.get(course_id, 0)
        return {
            "id": c.id,
            "code": c.code,
            "title": c.title,
            "description": c.description,
            "capacity": c.capacity,
            "term": getattr(c, "term", ""),
            "academic_year": getattr(c, "academic_year", ""),
            "section": getattr(c, "section", ""),
            "assigned_faculty_id": getattr(c, "assigned_faculty_id", ""),
            "enrolled": enrolled,
            "available": max(c.capacity - enrolled, 0),
        }
    except grpc.RpcError as exc:
        grpc_unavailable("course", exc)


# Enrollment routes
enrollment_router = APIRouter(prefix="/api/enrollments", tags=["enrollments"])


@enrollment_router.post("/")
def enroll(body: dict, user=Depends(require_user)):
    if user.get("role") == "FACULTY":
        raise HTTPException(status_code=403, detail="Faculty cannot enroll in courses")
    try:
        resp = enrollment_stub.Enroll(
            enrollment_pb2.EnrollRequest(
                student_id=user["user_id"],
                course_id=body.get("course_id", ""),
            )
        )
        enr = resp.enrollment
        return {
            "enrollment": {
                "id": enr.id,
                "student_id": enr.student_id,
                "course_id": enr.course_id,
                "status": enr.status,
            }
        }
    except grpc.RpcError as exc:
        grpc_unavailable("enrollment", exc)


@enrollment_router.get("/my")
def list_my_enrollments(user=Depends(require_user)):
    try:
        resp = enrollment_stub.ListStudentEnrollments(
            enrollment_pb2.ListStudentEnrollmentsRequest(student_id=user["user_id"])
        )
        enrollments = []
        for e in resp.enrollments:
            term = getattr(e, "term", "")
            ay = getattr(e, "academic_year", "")
            if CURRENT_TERM and term != CURRENT_TERM:
                continue
            if CURRENT_ACADEMIC_YEAR and ay != CURRENT_ACADEMIC_YEAR:
                continue
            enrollments.append(
                {
                    "id": e.id,
                    "student_id": e.student_id,
                    "course_id": e.course_id,
                    "status": e.status,
                    "term": term,
                    "academic_year": ay,
                }
            )
        return {"enrollments": enrollments}
    except grpc.RpcError as exc:
        grpc_unavailable("enrollment", exc)


@enrollment_router.get("/course/{course_id}/roster")
def course_roster(course_id: str, user=Depends(require_user)):
    """Return enrolled students (UUID + number + name) for a course; faculty only."""
    if user.get("role") != "FACULTY":
        raise HTTPException(status_code=403, detail="FACULTY role required")
    try:
        roster_resp = enrollment_stub.ListCourseRoster(enrollment_pb2.ListCourseRosterRequest(course_id=course_id))

        # Fetch course metadata to derive term/academic_year for grade lookup
        course_resp = course_stub.GetCourse(course_pb2.GetCourseRequest(id=course_id))
        course = course_resp.course
        term = getattr(course, "term", "")
        academic_year = getattr(course, "academic_year", "")

        # Fetch existing grades for this course/term/AY
        grades_resp = grade_stub.ListCourseGrades(
            grade_pb2.ListCourseGradesRequest(course_id=course_id, term=term, academic_year=academic_year)
        )
        grade_map = {g.student_id: g.grade for g in grades_resp.grades}

        roster = [
            {
                "student_id": r.student_id,
                "student_name": r.student_name,
                "user_number": r.user_number,
                "status": r.status,
                "grade": grade_map.get(r.student_id),
            }
            for r in roster_resp.roster
        ]
        return {"roster": roster, "term": term, "academic_year": academic_year}
    except grpc.RpcError as exc:
        grpc_unavailable("enrollment", exc)


# Grade routes
grade_router = APIRouter(prefix="/api/grades", tags=["grades"])


@grade_router.get("/my")
def list_my_grades(user=Depends(require_user)):
    try:
        resp = grade_stub.ListStudentTermGrades(grade_pb2.ListStudentTermGradesRequest(student_id=user["user_id"]))
        groups = [
            {
                "academic_year": grp.academic_year,
                "term": grp.term,
                "courses": [
                    {
                        "course_id": c.course_id,
                        "course_code": c.course_code,
                        "course_name": c.course_name,
                        "grade": c.grade or None,
                    }
                    for c in grp.courses
                ],
            }
            for grp in resp.groups
        ]
        return {"groups": groups}
    except grpc.RpcError as exc:
        grpc_unavailable("grade", exc)


@grade_router.post("/")
def submit_grade(body: dict, user=Depends(require_user)):
    """Single-grade submission (legacy); expects UUIDs and academic year."""
    if user.get("role") != "FACULTY":
        raise HTTPException(status_code=403, detail="FACULTY role required")
    try:
        resp = grade_stub.SubmitGrade(
            grade_pb2.SubmitGradeRequest(
                student_id=body.get("student_id", ""),
                course_id=body.get("course_id", ""),
                term=body.get("term", ""),
                academic_year=body.get("academic_year", ""),
                grade=body.get("grade", ""),
            )
        )
        g = resp.record
        return {
            "grade": {
                "id": g.id,
                "student_id": g.student_id,
                "course_id": g.course_id,
                "term": g.term,
                "academic_year": getattr(g, "academic_year", ""),
                "grade": g.grade,
            }
        }
    except grpc.RpcError as exc:
        grpc_unavailable("grade", exc)


@grade_router.post("/bulk")
def submit_grades(body: dict, user=Depends(require_user)):
    """Bulk upsert of grades for a course/term/academic year using UUIDs."""
    if user.get("role") != "FACULTY":
        raise HTTPException(status_code=403, detail="FACULTY role required")
    course_id = body.get("course_id", "")
    term = body.get("term", "")
    academic_year = body.get("academic_year", "")
    records = body.get("records", [])
    try:
        resp = grade_stub.SubmitGrades(
            grade_pb2.SubmitGradesRequest(
                course_id=course_id,
                term=term,
                academic_year=academic_year,
                records=[
                    grade_pb2.StudentGradeInput(student_id=rec.get("student_id", ""), grade=rec.get("grade", ""))
                    for rec in records
                ],
            )
        )
        grades = [
            {
                "id": g.id,
                "student_id": g.student_id,
                "course_id": g.course_id,
                "term": g.term,
                "academic_year": getattr(g, "academic_year", ""),
                "grade": g.grade,
            }
            for g in resp.records
        ]
        return {"grades": grades}
    except grpc.RpcError as exc:
        grpc_unavailable("grade", exc)


app.include_router(auth_router)
app.include_router(course_router)
app.include_router(enrollment_router)
app.include_router(grade_router)
