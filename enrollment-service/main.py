import concurrent.futures as futures
import enum
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import grpc
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine, func, text
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
    from common.protos import enrollment_pb2, enrollment_pb2_grpc
except ImportError as exc:  # pragma: no cover
    raise ImportError("Protos not generated or not on PYTHONPATH. Run `make protos`.") from exc

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/enrollment")
GRPC_PORT = int(os.getenv("ENROLLMENT_GRPC_PORT", "50053"))
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"options": "-c search_path=enrollment,public"},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class EnrollmentStatus(str, enum.Enum):
    ENROLLED = "ENROLLED"
    WAITLISTED = "WAITLISTED"
    DROPPED = "DROPPED"


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = {"schema": "enrollment"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    student_id = Column(UUID(as_uuid=True), nullable=False)
    course_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String, nullable=False)


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = {"schema": "enrollment"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    code = Column(String, nullable=False)
    title = Column(String, nullable=False, default="")
    capacity = Column(Integer, nullable=False, default=0)
    term = Column(String(32))
    academic_year = Column(String(32))
    section = Column(String(16))
    assigned_faculty_id = Column(UUID(as_uuid=True))


class Student(Base):
    __tablename__ = "students"
    __table_args__ = {"schema": "enrollment"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String, nullable=False, default="")
    user_number = Column(String(32))


app = FastAPI(title="Enrollment Service", version="0.1.0")
SERVICE_NAME = "enrollment-service"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logger = logging.getLogger(SERVICE_NAME)


class EnrollRequestBody(BaseModel):
    student_id: str
    course_id: str


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


def ensure_schema():
    """Ensure enrollment-owned tables and constraints exist, with optional backfill from shared schemas."""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS enrollment.courses (
                        id UUID PRIMARY KEY,
                        code VARCHAR(64) NOT NULL,
                        title TEXT NOT NULL DEFAULT '',
                        capacity INTEGER NOT NULL DEFAULT 0,
                        term VARCHAR(32),
                        academic_year VARCHAR(32),
                        section VARCHAR(16),
                        assigned_faculty_id UUID,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS enrollment.students (
                        id UUID PRIMARY KEY,
                        name TEXT NOT NULL DEFAULT '',
                        user_number VARCHAR(32)
                    )
                    """
                )
            )
            conn.execute(text("ALTER TABLE enrollment.enrollments DROP CONSTRAINT IF EXISTS enrollments_student_id_fkey;"))
            conn.execute(text("ALTER TABLE enrollment.enrollments DROP CONSTRAINT IF EXISTS enrollments_course_id_fkey;"))

            # Opportunistic backfill from shared schemas if available.
            try:
                conn.execute(
                    text(
                        """
                        INSERT INTO enrollment.courses (id, code, title, capacity, term, academic_year, section, assigned_faculty_id)
                        SELECT id, COALESCE(code, ''), COALESCE(title, ''), COALESCE(capacity, 0),
                               term, academic_year, section, assigned_faculty_id
                        FROM course_catalog.courses c
                        WHERE NOT EXISTS (
                            SELECT 1 FROM enrollment.courses ec WHERE ec.id = c.id
                        )
                        """
                    )
                )
            except Exception:
                logger.warning("Course backfill skipped (course_catalog.courses unavailable)")

            try:
                conn.execute(
                    text(
                        """
                        INSERT INTO enrollment.students (id, name, user_number)
                        SELECT id, COALESCE(name, ''), user_number
                        FROM auth.users u
                        WHERE NOT EXISTS (
                            SELECT 1 FROM enrollment.students es WHERE es.id = u.id
                        )
                        """
                    )
                )
            except Exception:
                logger.warning("Student backfill skipped (auth.users unavailable)")

            # Ensure placeholder records exist for any referenced IDs.
            conn.execute(
                text(
                    """
                    INSERT INTO enrollment.courses (id, code, title, capacity)
                    SELECT DISTINCT e.course_id, '', '', 0
                    FROM enrollment.enrollments e
                    WHERE NOT EXISTS (
                        SELECT 1 FROM enrollment.courses c WHERE c.id = e.course_id
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO enrollment.students (id, name, user_number)
                    SELECT DISTINCT e.student_id, '', NULL
                    FROM enrollment.enrollments e
                    WHERE NOT EXISTS (
                        SELECT 1 FROM enrollment.students s WHERE s.id = e.student_id
                    )
                    """
                )
            )

            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'enrollments_student_fk'
                              AND conrelid = 'enrollment.enrollments'::regclass
                        ) THEN
                            ALTER TABLE enrollment.enrollments
                            ADD CONSTRAINT enrollments_student_fk FOREIGN KEY (student_id) REFERENCES enrollment.students (id) ON DELETE CASCADE;
                        END IF;
                    END$$;
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'enrollments_course_fk'
                              AND conrelid = 'enrollment.enrollments'::regclass
                        ) THEN
                            ALTER TABLE enrollment.enrollments
                            ADD CONSTRAINT enrollments_course_fk FOREIGN KEY (course_id) REFERENCES enrollment.courses (id) ON DELETE CASCADE;
                        END IF;
                    END$$;
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollment.enrollments (student_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollment.enrollments (course_id);"))
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_enrollments_student_course ON enrollment.enrollments (student_id, course_id);"
                )
            )
    except Exception:
        logger.exception("Failed to ensure enrollment schema is up to date")
        raise


def ensure_student(db: Session, *, student_id: str, name: str = "", user_number: str = "") -> None:
    """Make sure a student row exists for roster lookups."""
    exists = db.query(Student.id).filter(Student.id == student_id).first()
    if exists:
        return
    db.add(Student(id=student_id, name=name or "", user_number=user_number or None))
    db.commit()


@app.get("/health")
def health():
    return {"status": "ok", "service": "enrollment-service"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "service": "enrollment-service", "db": "connected"}
    except Exception as exc:  # pragma: no cover - simple probe
        return {"status": "error", "service": "enrollment-service", "db": "unreachable", "detail": str(exc)}


# ---------- REST endpoints ----------
@app.post("/enrollments")
def enroll(body: EnrollRequestBody, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == body.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    ensure_student(db, student_id=body.student_id)

    # Prevent enrolling in multiple sections of the same course code.
    existing_same_course = (
        db.query(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .filter(
            Enrollment.student_id == body.student_id,
            Course.code == course.code,
            Enrollment.status != EnrollmentStatus.DROPPED.value,
        )
        .first()
    )
    if existing_same_course:
        raise HTTPException(status_code=409, detail="Already enrolled in another section of this course")

    existing_same_section = (
        db.query(Enrollment)
        .filter(Enrollment.student_id == body.student_id, Enrollment.course_id == body.course_id)
        .first()
    )
    if existing_same_section:
        if existing_same_section.status != EnrollmentStatus.DROPPED.value:
            raise HTTPException(status_code=409, detail="Already enrolled in this course section")
        existing_same_section.status = status
        db.commit()
        db.refresh(existing_same_section)
        return {
            "id": str(existing_same_section.id),
            "student_id": str(existing_same_section.student_id),
            "course_id": str(existing_same_section.course_id),
            "status": existing_same_section.status,
        }

    current = (
        db.query(func.count())
        .select_from(Enrollment)
        .filter(Enrollment.course_id == body.course_id, Enrollment.status == EnrollmentStatus.ENROLLED.value)
        .scalar()
    )
    status = EnrollmentStatus.ENROLLED.value if current < course.capacity else EnrollmentStatus.WAITLISTED.value

    enr = Enrollment(student_id=body.student_id, course_id=body.course_id, status=status)
    db.add(enr)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Already enrolled")
    db.refresh(enr)
    return {
        "id": str(enr.id),
        "student_id": str(enr.student_id),
        "course_id": str(enr.course_id),
        "status": enr.status,
    }


@app.get("/enrollments")
def list_enrollments(student_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(Enrollment, Course)
        .join(Course, Course.id == Enrollment.course_id)
        .filter(Enrollment.student_id == student_id)
        .all()
    )
    return [
        {
            "id": str(enr.id),
            "student_id": str(enr.student_id),
            "course_id": str(enr.course_id),
            "status": enr.status,
            "term": course.term,
            "academic_year": course.academic_year,
        }
        for enr, course in rows
    ]


@app.get("/enrollments/roster")
def course_roster(course_id: str, db: Session = Depends(get_db)):
    """Roster for a course_id (ENROLLED only) including student name and number."""
    rows = (
        db.query(Enrollment, Student)
        .join(Student, Student.id == Enrollment.student_id)
        .filter(Enrollment.course_id == course_id, Enrollment.status == EnrollmentStatus.ENROLLED.value)
        .all()
    )
    return [
        {
            "student_id": str(enr.student_id),
            "student_name": usr.name,
            "user_number": usr.user_number,
            "status": enr.status,
        }
        for enr, usr in rows
    ]


# ---------- gRPC service ----------
class EnrollmentService(enrollment_pb2_grpc.EnrollmentServiceServicer):
    @staticmethod
    def _status_to_proto(status: str) -> int:
        if status == EnrollmentStatus.ENROLLED.value:
            return enrollment_pb2.ENROLLED
        if status == EnrollmentStatus.WAITLISTED.value:
            return enrollment_pb2.WAITLISTED
        if status == EnrollmentStatus.DROPPED.value:
            return enrollment_pb2.DROPPED
        return enrollment_pb2.ENROLLMENT_STATUS_UNSPECIFIED

    def Enroll(self, request, context):
        db = SessionLocal()
        try:
            course = db.query(Course).filter(Course.id == request.course_id).first()
            if not course:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Course not found")
                return enrollment_pb2.EnrollResponse()

            current = (
                db.query(func.count())
                .select_from(Enrollment)
                .filter(Enrollment.course_id == request.course_id, Enrollment.status == EnrollmentStatus.ENROLLED.value)
                .scalar()
            )
            status = (
                EnrollmentStatus.ENROLLED.value if current < course.capacity else EnrollmentStatus.WAITLISTED.value
            )

            # Prevent enrolling in multiple sections of the same course code.
            existing_same_course = (
                db.query(Enrollment)
                .join(Course, Course.id == Enrollment.course_id)
                .filter(
                    Enrollment.student_id == request.student_id,
                    Course.code == course.code,
                    Enrollment.status != EnrollmentStatus.DROPPED.value,
                )
                .first()
            )
            if existing_same_course:
                context.set_code(grpc.StatusCode.ALREADY_EXISTS)
                context.set_details("Already enrolled in another section of this course")
                return enrollment_pb2.EnrollResponse()

            existing_same_section = (
                db.query(Enrollment)
                .filter(Enrollment.student_id == request.student_id, Enrollment.course_id == request.course_id)
                .first()
            )
            if existing_same_section:
                if existing_same_section.status != EnrollmentStatus.DROPPED.value:
                    context.set_code(grpc.StatusCode.ALREADY_EXISTS)
                    context.set_details("Already enrolled in this course section")
                    return enrollment_pb2.EnrollResponse()
                # Reuse the dropped record to allow re-enrollment in the same section.
                existing_same_section.status = status
                db.commit()
                db.refresh(existing_same_section)
                proto_status = self._status_to_proto(existing_same_section.status)
                return enrollment_pb2.EnrollResponse(
                    enrollment=enrollment_pb2.Enrollment(
                        id=str(existing_same_section.id),
                        student_id=str(existing_same_section.student_id),
                        course_id=str(existing_same_section.course_id),
                        status=proto_status,
                        term=course.term or "",
                        academic_year=course.academic_year or "",
                    )
                )

            ensure_student(db, student_id=request.student_id)
            enr = Enrollment(student_id=request.student_id, course_id=request.course_id, status=status)
            db.add(enr)
            db.commit()
            db.refresh(enr)
            proto_status = self._status_to_proto(status)
            return enrollment_pb2.EnrollResponse(
                enrollment=enrollment_pb2.Enrollment(
                    id=str(enr.id),
                    student_id=str(enr.student_id),
                    course_id=str(enr.course_id),
                    status=proto_status,
                    term=course.term or "",
                    academic_year=course.academic_year or "",
                )
            )
        except IntegrityError:
            db.rollback()
            context.set_code(grpc.StatusCode.ALREADY_EXISTS)
            context.set_details("Already enrolled")
            return enrollment_pb2.EnrollResponse()
        finally:
            db.close()

    def ListStudentEnrollments(self, request, context):
        db = SessionLocal()
        try:
            rows = (
                db.query(Enrollment, Course)
                .join(Course, Course.id == Enrollment.course_id)
                .filter(Enrollment.student_id == request.student_id)
                .all()
            )
            items = [
                enrollment_pb2.Enrollment(
                    id=str(enr.id),
                    student_id=str(enr.student_id),
                    course_id=str(enr.course_id),
                    status=self._status_to_proto(enr.status),
                    term=course.term or "",
                    academic_year=course.academic_year or "",
                )
                for enr, course in rows
            ]
            return enrollment_pb2.ListStudentEnrollmentsResponse(enrollments=items)
        finally:
            db.close()

    def ListCourseRoster(self, request, context):
        db = SessionLocal()
        try:
            rows = (
                db.query(Enrollment, Student)
                .join(Student, Student.id == Enrollment.student_id)
                .filter(Enrollment.course_id == request.course_id, Enrollment.status == EnrollmentStatus.ENROLLED.value)
                .all()
            )
            roster_items = [
                enrollment_pb2.RosterEntry(
                    student_id=str(enr.student_id),
                    student_name=usr.name or "",
                    user_number=usr.user_number or "",
                    status=self._status_to_proto(enr.status),
                )
                for enr, usr in rows
            ]
            return enrollment_pb2.ListCourseRosterResponse(roster=roster_items)
        finally:
            db.close()

    def DropEnrollment(self, request, context):
        db = SessionLocal()
        try:
            enr = (
                db.query(Enrollment, Course)
                .join(Course, Course.id == Enrollment.course_id)
                .filter(Enrollment.id == request.enrollment_id)
                .first()
            )
            if not enr:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Enrollment not found")
                return enrollment_pb2.DropEnrollmentResponse()
            enrollment_row, course = enr
            enrollment_row.status = EnrollmentStatus.DROPPED.value
            db.commit()
            db.refresh(enrollment_row)
            return enrollment_pb2.DropEnrollmentResponse(
                enrollment=enrollment_pb2.Enrollment(
                    id=str(enrollment_row.id),
                    student_id=str(enrollment_row.student_id),
                    course_id=str(enrollment_row.course_id),
                    status=enrollment_pb2.DROPPED,
                    term=course.term or "",
                    academic_year=course.academic_year or "",
                )
            )
        finally:
            db.close()


def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    enrollment_pb2_grpc.add_EnrollmentServiceServicer_to_server(EnrollmentService(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    server.wait_for_termination()


@app.on_event("startup")
def start_grpc_server():
    ensure_schema()
    thread = threading.Thread(target=serve_grpc, daemon=True)
    thread.start()
