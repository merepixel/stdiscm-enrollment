import concurrent.futures as futures
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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
    from common.protos import grade_pb2, grade_pb2_grpc
except ImportError as exc:  # pragma: no cover
    raise ImportError("Protos not generated or not on PYTHONPATH. Run `make protos`.") from exc

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/enrollment")
GRPC_PORT = int(os.getenv("GRADE_GRPC_PORT", "50054"))
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"options": "-c search_path=grade,public"},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Grade(Base):
    __tablename__ = "grades"
    __table_args__ = {"schema": "grade"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    student_id = Column(UUID(as_uuid=True), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=True)
    course_code = Column(String(64), nullable=False)
    course_name = Column(Text, nullable=False)
    term = Column(String(32), nullable=False)
    academic_year = Column(String(32), nullable=False, default="")
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
    course_id: str | None = None
    course_code: str | None = None
    course_name: str | None = None
    term: str
    academic_year: str
    grade: str


class StudentGradeIn(BaseModel):
    student_id: str
    grade: str


class BulkGradeIn(BaseModel):
    course_id: str | None = None
    course_code: str | None = None
    course_name: str | None = None
    term: str
    academic_year: str
    records: List[StudentGradeIn]


class TermCourseGrade(BaseModel):
    course_id: str | None = None
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


def resolve_course_metadata(
    db: Session, *, course_id: Optional[str], course_code: Optional[str], course_name: Optional[str]
) -> Tuple[Optional[str], str, str]:
    """Return course metadata to persist, reusing prior records when possible."""
    code = (course_code or "").strip()
    name = (course_name or "").strip()
    if code and name:
        return course_id, code, name

    if course_id:
        existing = (
            db.execute(
                text(
                    """
                    SELECT course_code, course_name
                    FROM grade.grades
                    WHERE course_id = :course_id
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"course_id": course_id},
            )
            .mappings()
            .first()
        )
        if existing:
            return course_id, existing["course_code"], existing["course_name"]

    raise HTTPException(status_code=400, detail="course_code and course_name are required for grade submissions")


def grade_row_to_dict(row) -> Dict[str, str]:
    """Normalize a grade row mapping for JSON responses."""
    return {
        "id": str(row["id"]),
        "student_id": str(row["student_id"]),
        "course_id": str(row["course_id"]) if row.get("course_id") else None,
        "course_code": row["course_code"],
        "course_name": row["course_name"],
        "term": row["term"],
        "academic_year": row["academic_year"],
        "grade": row["grade"],
    }


def grade_row_to_proto(row) -> grade_pb2.GradeRecord:
    return grade_pb2.GradeRecord(
        id=str(row["id"]),
        student_id=str(row["student_id"]),
        course_id=str(row["course_id"]) if row.get("course_id") else "",
        course_code=row["course_code"],
        course_name=row["course_name"],
        term=row["term"],
        academic_year=row["academic_year"],
        grade=row["grade"],
    )


def ensure_schema():
    """Apply lightweight, idempotent DDL so course metadata columns exist."""
    statements = [
        "ALTER TABLE grade.grades ADD COLUMN IF NOT EXISTS course_code VARCHAR(64);",
        "ALTER TABLE grade.grades ADD COLUMN IF NOT EXISTS course_name TEXT;",
        "ALTER TABLE grade.grades ADD COLUMN IF NOT EXISTS academic_year VARCHAR(32);",
        "UPDATE grade.grades SET course_code = c.code, course_name = c.title FROM course_catalog.courses c WHERE grade.grades.course_id = c.id AND grade.grades.course_code IS NULL;",
        "UPDATE grade.grades SET course_code = '' WHERE course_code IS NULL;",
        "UPDATE grade.grades SET course_name = '' WHERE course_name IS NULL;",
        "UPDATE grade.grades SET academic_year = COALESCE(academic_year, '');",
        "ALTER TABLE grade.grades ALTER COLUMN course_id DROP NOT NULL;",
        "ALTER TABLE grade.grades ALTER COLUMN course_code SET NOT NULL;",
        "ALTER TABLE grade.grades ALTER COLUMN course_name SET NOT NULL;",
        "ALTER TABLE grade.grades ALTER COLUMN academic_year SET NOT NULL;",
        "ALTER TABLE grade.grades ALTER COLUMN academic_year SET DEFAULT '';",
        "ALTER TABLE grade.grades DROP CONSTRAINT IF EXISTS grades_student_id_course_id_term_key;",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_grades_student_course_term_year ON grade.grades (student_id, course_code, term, academic_year);",
        "CREATE INDEX IF NOT EXISTS idx_grades_course_code ON grade.grades (course_code);",
    ]
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except Exception:  # pragma: no cover - guard rails for startup
        logger.exception("Failed to ensure grade schema is up to date")
        raise


def parse_academic_year_start(academic_year: str) -> int:
    if not academic_year:
        return -1
    for part in academic_year.replace("–", "-").split("-"):
        if part.isdigit():
            return int(part)
    return -1


def get_student_term_grades(student_id: str, db: Session) -> List[TermGradesGroup]:
    """Return all grade records grouped by term/year, using only local DB state."""
    rows = db.execute(
        text(
            """
            SELECT id, student_id, course_id, course_code, course_name, term, academic_year, grade
            FROM grade.grades
            WHERE student_id = :student_id
            """
        ),
        {"student_id": student_id},
    ).mappings()

    grouped: Dict[Tuple[str, str], List[TermCourseGrade]] = {}
    for row in rows:
        ay = row["academic_year"] or ""
        term = row["term"] or ""
        grouped.setdefault((ay, term), []).append(
            TermCourseGrade(
                course_id=str(row["course_id"]) if row["course_id"] else None,
                course_code=row["course_code"] or "",
                course_name=row["course_name"] or "",
                grade=row["grade"],
            )
        )

    sorted_groups = []
    for (ay, term), courses in grouped.items():
        courses_sorted = sorted(courses, key=lambda c: (c.course_code, c.course_name))
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
    db: Session,
    *,
    student_id: str,
    course_id: Optional[str],
    course_code: Optional[str],
    course_name: Optional[str],
    term: str,
    academic_year: str,
    grade: str,
):
    """Insert or update a grade for a student/course/term."""
    course_id, resolved_code, resolved_name = resolve_course_metadata(
        db, course_id=course_id, course_code=course_code, course_name=course_name
    )
    term = term or ""
    academic_year = academic_year or ""
    try:
        row = (
            db.execute(
                text(
                    """
                    INSERT INTO grade.grades (
                        student_id,
                        course_id,
                        course_code,
                        course_name,
                        term,
                        academic_year,
                        grade
                    )
                    VALUES (:student_id, :course_id, :course_code, :course_name, :term, :academic_year, :grade)
                    ON CONFLICT (student_id, course_code, term, academic_year)
                    DO UPDATE SET grade = EXCLUDED.grade,
                                  course_name = EXCLUDED.course_name,
                                  course_id = COALESCE(EXCLUDED.course_id, grade.grades.course_id),
                                  updated_at = NOW()
                    RETURNING id, student_id, course_id, course_code, course_name, term, academic_year, grade
                    """
                ),
                {
                    "student_id": student_id,
                    "course_id": course_id,
                    "course_code": resolved_code,
                    "course_name": resolved_name,
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
            course_code=body.course_code,
            course_name=body.course_name,
            term=body.term,
            academic_year=body.academic_year,
            grade=body.grade,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Grade already exists for student/course/term")
    return grade_row_to_dict(rec)


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
                course_code=body.course_code,
                course_name=body.course_name,
                term=body.term,
                academic_year=body.academic_year,
                grade=record.grade,
            )
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Duplicate grade for student/course/term")
        results.append(grade_row_to_dict(rec))
    return {"grades": results}


@app.get("/grades")
def list_grades(student_id: str, db: Session = Depends(get_db)):
    rows = db.query(Grade).filter(Grade.student_id == student_id).all()
    return [
        {
            "id": str(g.id),
            "student_id": str(g.student_id),
            "course_id": str(g.course_id) if g.course_id else None,
            "course_code": g.course_code,
            "course_name": g.course_name,
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
                course_id=request.course_id or None,
                course_code=request.course_code or None,
                course_name=request.course_name or None,
                term=request.term,
                academic_year=request.academic_year,
                grade=request.grade,
            )
            return grade_pb2.SubmitGradeResponse(record=grade_row_to_proto(rec))
        except HTTPException as exc:
            db.rollback()
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(exc.detail))
            return grade_pb2.SubmitGradeResponse()
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
                    course_id=request.course_id or None,
                    course_code=request.course_code or None,
                    course_name=request.course_name or None,
                    term=request.term,
                    academic_year=request.academic_year,
                    grade=item.grade,
                )
                records.append(rec)
            return grade_pb2.SubmitGradesResponse(records=[grade_row_to_proto(rec) for rec in records])
        except HTTPException as exc:
            db.rollback()
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(exc.detail))
            return grade_pb2.SubmitGradesResponse()
        finally:
            db.close()

    def GetGradesByStudent(self, request, context):
        db = SessionLocal()
        try:
            rows = (
                db.execute(
                    text(
                        """
                        SELECT id, student_id, course_id, course_code, course_name, term, academic_year, grade
                        FROM grade.grades
                        WHERE student_id = :student_id
                        """
                    ),
                    {"student_id": request.student_id},
                )
                .mappings()
            )
            return grade_pb2.GradesResponse(grades=[grade_row_to_proto(row) for row in rows])
        finally:
            db.close()

    def ListGrades(self, request, context):
        db = SessionLocal()
        try:
            rows = (
                db.execute(
                    text(
                        """
                        SELECT id, student_id, course_id, course_code, course_name, term, academic_year, grade
                        FROM grade.grades
                        WHERE student_id = :student_id
                        """
                    ),
                    {"student_id": request.student_id},
                )
                .mappings()
            )
            return grade_pb2.ListGradesResponse(grades=[grade_row_to_proto(row) for row in rows])
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
                                course_id=c.course_id or "",
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
            filters = [
                Grade.course_id == request.course_id if request.course_id else None,
                Grade.course_code == request.course_code if request.course_code else None,
                Grade.term == request.term if request.term else None,
                Grade.academic_year == request.academic_year if request.academic_year else None,
            ]
            active_filters = [cond for cond in filters if cond is not None]
            if not active_filters:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("At least one filter (course_id, course_code, term, academic_year) is required")
                return grade_pb2.ListCourseGradesResponse()

            rows = db.query(Grade).filter(*active_filters).all()
            items = [
                grade_pb2.GradeRecord(
                    id=str(g.id),
                    student_id=str(g.student_id),
                    course_id=str(g.course_id) if g.course_id else "",
                    course_code=g.course_code,
                    course_name=g.course_name,
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
    # Ensure the DB schema has the self-contained course metadata columns before serving requests.
    ensure_schema()
    thread = threading.Thread(target=serve_grpc, daemon=True)
    thread.start()
