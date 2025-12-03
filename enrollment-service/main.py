import concurrent.futures as futures
import logging
import enum
import os
import sys
import threading
import time
from pathlib import Path
from typing import List
from uuid import uuid4

import grpc
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, String, Integer, text, func, create_engine
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
    connect_args={"options": "-c search_path=enrollment,course_catalog,auth,public"},
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
    __table_args__ = {"schema": "course_catalog"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    capacity = Column(Integer, nullable=False)


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
    rows = db.query(Enrollment).filter(Enrollment.student_id == student_id).all()
    return [
        {
            "id": str(e.id),
            "student_id": str(e.student_id),
            "course_id": str(e.course_id),
            "status": e.status,
        }
        for e in rows
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
            rows = db.query(Enrollment).filter(Enrollment.student_id == request.student_id).all()
            items = [
                enrollment_pb2.Enrollment(
                    id=str(e.id),
                    student_id=str(e.student_id),
                    course_id=str(e.course_id),
                    status=self._status_to_proto(e.status),
                )
                for e in rows
            ]
            return enrollment_pb2.ListStudentEnrollmentsResponse(enrollments=items)
        finally:
            db.close()

    def DropEnrollment(self, request, context):
        db = SessionLocal()
        try:
            enr = db.query(Enrollment).filter(Enrollment.id == request.enrollment_id).first()
            if not enr:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Enrollment not found")
                return enrollment_pb2.DropEnrollmentResponse()
            enr.status = EnrollmentStatus.DROPPED.value
            db.commit()
            db.refresh(enr)
            return enrollment_pb2.DropEnrollmentResponse(
                enrollment=enrollment_pb2.Enrollment(
                    id=str(enr.id),
                    student_id=str(enr.student_id),
                    course_id=str(enr.course_id),
                    status=enrollment_pb2.DROPPED,
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
    thread = threading.Thread(target=serve_grpc, daemon=True)
    thread.start()
