import concurrent.futures as futures
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple
from uuid import uuid4

import grpc
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Column, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PROTO_PATH = ROOT_DIR / "common" / "protos"
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if str(PROTO_PATH) not in sys.path:
    sys.path.append(str(PROTO_PATH))

try:
    from common.protos import grade_pb2, grade_pb2_grpc, enrollment_pb2, enrollment_pb2_grpc, course_pb2, course_pb2_grpc
except ImportError as exc:  # pragma: no cover
    raise ImportError("Protos not generated or not on PYTHONPATH. Run `make protos`.") from exc

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/enrollment")
GRPC_PORT = int(os.getenv("GRADE_GRPC_PORT", "50054"))
ENROLLMENT_GRPC_TARGET = os.getenv("ENROLLMENT_GRPC_TARGET", "enrollment-service:50053")
COURSE_GRPC_TARGET = os.getenv("COURSE_GRPC_TARGET", "course-service:50052")
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"options": "-c search_path=grade,public"},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

enrollment_stub = enrollment_pb2_grpc.EnrollmentServiceStub(grpc.insecure_channel(ENROLLMENT_GRPC_TARGET))
course_stub = course_pb2_grpc.CourseServiceStub(grpc.insecure_channel(COURSE_GRPC_TARGET))


class Grade(Base):
    __tablename__ = "grades"
    __table_args__ = {"schema": "grade"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    student_id = Column(UUID(as_uuid=True), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)
    term = Column(String(32), nullable=False)
    academic_year = Column(String(32))
    grade = Column(Text, nullable=False)


app = FastAPI(title="Grade Service", version="0.1.0")
SERVICE_NAME = "grade-service"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logger = logging.getLogger(SERVICE_NAME)


class GradeIn(BaseModel):
    student_id: str
    course_id: str
    term: str
    academic_year: str
    grade: str


class StudentGradeIn(BaseModel):
    student_id: str
    grade: str


class BulkGradeIn(BaseModel):
    course_id: str
    term: str
    academic_year: str
    records: List[StudentGradeIn]


class TermCourseGrade(BaseModel):
    course_id: str
    course_code: str
    course_name: str
    grade: str | None = None


class TermGradesGroup(BaseModel):
    academic_year: str
    term: str
    courses: List[TermCourseGrade]


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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_academic_year_start(academic_year: str) -> int:
    if not academic_year:
        return -1
    for part in academic_year.replace("–", "-").split("-"):
        if part.isdigit():
            return int(part)
    return -1


def get_student_term_grades(student_id: str, db: Session) -> List[TermGradesGroup]:
    """Return all courses (via enrollments) grouped by term/year with grades merged in."""
    # 1) Fetch enrollments via Enrollment service.
    enr_resp = enrollment_stub.ListStudentEnrollments(enrollment_pb2.ListStudentEnrollmentsRequest(student_id=student_id))
    enrollments = list(enr_resp.enrollments)

    # 2) Fetch grades for student from DB.
    rows = db.execute(
        text(
            """
            SELECT id, student_id, course_id, term, academic_year, grade
            FROM grade.grades
            WHERE student_id = :student_id
            """
        ),
        {"student_id": student_id},
    ).mappings()
    grades_map: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    for row in rows:
        key = (str(row["course_id"]), row["term"] or "", row["academic_year"] or "")
        grades_map[key] = {
            "id": str(row["id"]),
            "grade": row["grade"],
            "term": row["term"] or "",
            "academic_year": row["academic_year"] or "",
        }

    # 3) Fetch course metadata for all distinct course_ids.
    course_ids = {e.course_id for e in enrollments}
    course_map: Dict[str, course_pb2.Course] = {}
    for course_id in course_ids:
        try:
            c_resp = course_stub.GetCourse(course_pb2.GetCourseRequest(id=course_id))
            course_map[course_id] = c_resp.course
        except grpc.RpcError:
            course_map[course_id] = None

    # 4) Merge enrollments + grades.
    grouped: Dict[Tuple[str, str], List[TermCourseGrade]] = {}
    for enr in enrollments:
        course = course_map.get(enr.course_id)
        term = enr.term or (course.term if course else "")
        academic_year = enr.academic_year or (course.academic_year if course else "")
        g_key = (enr.course_id, term or "", academic_year or "")
        grade_rec = grades_map.get(g_key)
        grouped.setdefault((academic_year or "", term or ""), []).append(
            TermCourseGrade(
                course_id=enr.course_id,
                course_code=course.code if course else "",
                course_name=course.title if course else "",
                grade=grade_rec["grade"] if grade_rec else None,
            )
        )

    # 5) Sort groups latest -> oldest, courses alphabetically by code.
    sorted_groups = []
    for (ay, term), courses in grouped.items():
        courses_sorted = sorted(courses, key=lambda c: c.course_code)
        sorted_groups.append((ay, term, courses_sorted))
    sorted_groups.sort(
        key=lambda item: (parse_academic_year_start(item[0]), float(item[1] or 0.0)),
        reverse=True,
    )

    return [TermGradesGroup(academic_year=ay, term=term, courses=courses) for ay, term, courses in sorted_groups]


@app.get("/health")
def health():
    return {"status": "ok", "service": "grade-service"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "service": "grade-service", "db": "connected"}
    except Exception as exc:  # pragma: no cover - simple probe
        return {"status": "error", "service": "grade-service", "db": "unreachable", "detail": str(exc)}


# ---------- REST endpoints ----------
def upsert_grade(
    db: Session, *, student_id: str, course_id: str, term: str, academic_year: str, grade: str
):
    """Insert or update a grade for a student/course/term."""
    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO grade.grades (student_id, course_id, term, academic_year, grade)
                    VALUES (:student_id, :course_id, :term, :academic_year, :grade)
                    ON CONFLICT (student_id, course_id, term)
                    DO UPDATE SET grade = EXCLUDED.grade,
                                  academic_year = EXCLUDED.academic_year,
                                  updated_at = NOW()
                    RETURNING id, student_id, course_id, term, academic_year, grade
                    """
                ),
                {
                    "student_id": student_id,
                    "course_id": course_id,
                    "term": term,
                    "academic_year": academic_year,
                    "grade": grade,
                },
            )
            .mappings()
            .first()
        )
        db.commit()
        return row
    except IntegrityError:
        db.rollback()
        raise


@app.post("/grades")
def submit_grade(body: GradeIn, db: Session = Depends(get_db)):
    try:
        rec = upsert_grade(
            db,
            student_id=body.student_id,
            course_id=body.course_id,
            term=body.term,
            academic_year=body.academic_year,
            grade=body.grade,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Grade already exists for student/course/term")
    return {
        "id": str(rec["id"]),
        "student_id": str(rec["student_id"]),
        "course_id": str(rec["course_id"]),
        "term": rec["term"],
        "academic_year": rec["academic_year"],
        "grade": rec["grade"],
    }


@app.post("/grades/bulk")
def submit_grades(body: BulkGradeIn, db: Session = Depends(get_db)):
    """Bulk upsert grades for a course/term/academic_year."""
    results = []
    for record in body.records:
        try:
            rec = upsert_grade(
                db,
                student_id=record.student_id,
                course_id=body.course_id,
                term=body.term,
                academic_year=body.academic_year,
                grade=record.grade,
            )
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Duplicate grade for student/course/term")
        results.append(
            {
                "id": str(rec["id"]),
                "student_id": str(rec["student_id"]),
                "course_id": str(rec["course_id"]),
                "term": rec["term"],
                "academic_year": rec["academic_year"],
                "grade": rec["grade"],
            }
        )
    return {"grades": results}


@app.get("/grades")
def list_grades(student_id: str, db: Session = Depends(get_db)):
    rows = db.query(Grade).filter(Grade.student_id == student_id).all()
    return [
        {
            "id": str(g.id),
            "student_id": str(g.student_id),
            "course_id": str(g.course_id),
            "term": g.term,
            "academic_year": g.academic_year,
            "grade": g.grade,
        }
        for g in rows
    ]


@app.get("/grades/terms")
def list_grades_by_term(student_id: str, db: Session = Depends(get_db)):
    """Grouped grades/enrollments for a student across all terms."""
    groups = get_student_term_grades(student_id, db)
    return {"groups": [g.dict() for g in groups]}


# ---------- gRPC service ----------
class GradeService(grade_pb2_grpc.GradeServiceServicer):
    def SubmitGrade(self, request, context):
        db = SessionLocal()
        try:
            rec = upsert_grade(
                db,
                student_id=request.student_id,
                course_id=request.course_id,
                term=request.term,
                academic_year=request.academic_year,
                grade=request.grade,
            )
            return grade_pb2.SubmitGradeResponse(
                record=grade_pb2.GradeRecord(
                    id=str(rec["id"]),
                    student_id=str(rec["student_id"]),
                    course_id=str(rec["course_id"]),
                    term=rec["term"],
                    academic_year=rec["academic_year"] or "",
                    grade=rec["grade"],
                )
            )
        except IntegrityError:
            db.rollback()
            context.set_code(grpc.StatusCode.ALREADY_EXISTS)
            context.set_details("Grade already exists for student/course/term")
            return grade_pb2.SubmitGradeResponse()
        finally:
            db.close()

    def SubmitGrades(self, request, context):
        """Bulk upsert gRPC endpoint mirroring REST bulk submission."""
        db = SessionLocal()
        records = []
        try:
            for item in request.records:
                rec = upsert_grade(
                    db,
                    student_id=item.student_id,
                    course_id=request.course_id,
                    term=request.term,
                    academic_year=request.academic_year,
                    grade=item.grade,
                )
                records.append(rec)
            return grade_pb2.SubmitGradesResponse(
                records=[
                    grade_pb2.GradeRecord(
                        id=str(rec["id"]),
                        student_id=str(rec["student_id"]),
                        course_id=str(rec["course_id"]),
                        term=rec["term"],
                        academic_year=rec["academic_year"] or "",
                        grade=rec["grade"],
                    )
                    for rec in records
                ]
            )
        finally:
            db.close()

    def ListGrades(self, request, context):
        db = SessionLocal()
        try:
            rows = db.query(Grade).filter(Grade.student_id == request.student_id).all()
            items = [
                grade_pb2.GradeRecord(
                    id=str(g.id),
                    student_id=str(g.student_id),
                    course_id=str(g.course_id),
                    term=g.term,
                    academic_year=g.academic_year or "",
                    grade=g.grade,
                )
                for g in rows
            ]
            return grade_pb2.ListGradesResponse(grades=items)
        finally:
            db.close()

    def ListStudentTermGrades(self, request, context):
        db = SessionLocal()
        try:
            groups = get_student_term_grades(request.student_id, db)
            return grade_pb2.ListStudentTermGradesResponse(
                groups=[
                    grade_pb2.TermGradesGroup(
                        academic_year=g.academic_year,
                        term=g.term,
                        courses=[
                            grade_pb2.TermCourseGrade(
                                course_id=c.course_id,
                                course_code=c.course_code,
                                course_name=c.course_name,
                                grade=c.grade or "",
                            )
                            for c in g.courses
                        ],
                    )
                    for g in groups
                ]
            )
        finally:
            db.close()

    def ListCourseGrades(self, request, context):
        db = SessionLocal()
        try:
            rows = (
                db.query(Grade)
                .filter(
                    Grade.course_id == request.course_id,
                    Grade.term == request.term,
                    Grade.academic_year == request.academic_year,
                )
                .all()
            )
            items = [
                grade_pb2.GradeRecord(
                    id=str(g.id),
                    student_id=str(g.student_id),
                    course_id=str(g.course_id),
                    term=g.term,
                    academic_year=g.academic_year or "",
                    grade=g.grade,
                )
                for g in rows
            ]
            return grade_pb2.ListCourseGradesResponse(grades=items)
        finally:
            db.close()


def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    grade_pb2_grpc.add_GradeServiceServicer_to_server(GradeService(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    server.wait_for_termination()


@app.on_event("startup")
def start_grpc_server():
    thread = threading.Thread(target=serve_grpc, daemon=True)
    thread.start()
