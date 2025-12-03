import concurrent.futures as futures
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
from sqlalchemy import Column, Integer, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session, declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PROTO_PATH = ROOT_DIR / "common" / "protos"

if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if str(PROTO_PATH) not in sys.path:
    sys.path.append(str(PROTO_PATH))

try:
    from common.protos import course_pb2, course_pb2_grpc
except ImportError as exc:  # pragma: no cover
    raise ImportError("Protos not generated or not on PYTHONPATH. Run `make protos`.") from exc

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/enrollment")
GRPC_PORT = int(os.getenv("COURSE_GRPC_PORT", "50052"))
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"options": "-c search_path=course_catalog,public"},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = {"schema": "course_catalog"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code = Column(String(32), unique=True, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    capacity = Column(Integer, nullable=False)
    term = Column(String(32))
    academic_year = Column(String(32))
    section = Column(String(16))
    assigned_faculty_id = Column(UUID(as_uuid=True), nullable=True)


app = FastAPI(title="Course Service", version="0.1.0")
SERVICE_NAME = "course-service"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logger = logging.getLogger(SERVICE_NAME)


class CourseOut(BaseModel):
    id: str
    code: str
    title: str
    description: Optional[str] = None
    capacity: int
    term: Optional[str] = None
    academic_year: Optional[str] = None
    section: Optional[str] = None
    assigned_faculty_id: Optional[str] = None


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
    return {"status": "ok", "service": "course-service"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "service": "course-service", "db": "connected"}
    except Exception as exc:  # pragma: no cover - simple probe
        return {"status": "error", "service": "course-service", "db": "unreachable", "detail": str(exc)}


# ---------- REST endpoints ----------
@app.get("/courses", response_model=List[CourseOut])
def list_courses(assigned_faculty_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Course)
    if assigned_faculty_id:
        query = query.filter(Course.assigned_faculty_id == assigned_faculty_id)
    rows = query.all()
    return [
        CourseOut(
            id=str(r.id),
            code=r.code,
            title=r.title,
            description=r.description,
            capacity=r.capacity,
            term=r.term,
            academic_year=r.academic_year,
            section=r.section,
            assigned_faculty_id=str(r.assigned_faculty_id) if r.assigned_faculty_id else None,
        )
        for r in rows
    ]


@app.get("/courses/{course_id}", response_model=CourseOut)
def get_course(course_id: str, db: Session = Depends(get_db)):
    row = db.query(Course).filter(Course.id == course_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    return CourseOut(
        id=str(row.id),
        code=row.code,
        title=row.title,
        description=row.description,
        capacity=row.capacity,
        term=row.term,
        academic_year=row.academic_year,
        section=row.section,
        assigned_faculty_id=str(row.assigned_faculty_id) if row.assigned_faculty_id else None,
    )


# ---------- gRPC service ----------
class CourseService(course_pb2_grpc.CourseServiceServicer):
    def ListCourses(self, request, context):
        db = SessionLocal()
        try:
            rows = db.query(Course).all()
            courses = [
                course_pb2.Course(
                    id=str(r.id),
                    code=r.code,
                    title=r.title,
                    description=r.description or "",
                    capacity=r.capacity or 0,
                    term=r.term or "",
                    academic_year=r.academic_year or "",
                    section=r.section or "",
                    assigned_faculty_id=str(r.assigned_faculty_id) if r.assigned_faculty_id else "",
                )
                for r in rows
            ]
            return course_pb2.ListCoursesResponse(courses=courses)
        finally:
            db.close()

    def GetCourse(self, request, context):
        db = SessionLocal()
        try:
            if request.id:
                row = db.query(Course).filter(Course.id == request.id).first()
            else:
                row = db.query(Course).filter(Course.code == request.code).first()
            if not row:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Course not found")
                return course_pb2.GetCourseResponse()
            return course_pb2.GetCourseResponse(
                course=course_pb2.Course(
                    id=str(row.id),
                    code=row.code,
                    title=row.title,
                    description=row.description or "",
                    capacity=row.capacity or 0,
                    term=row.term or "",
                    academic_year=row.academic_year or "",
                    section=row.section or "",
                    assigned_faculty_id=str(row.assigned_faculty_id) if row.assigned_faculty_id else "",
                )
            )
        finally:
            db.close()

    def ListFacultyCourses(self, request, context):
        """Return courses assigned to the given faculty UUID."""
        db = SessionLocal()
        try:
            rows = db.query(Course).filter(Course.assigned_faculty_id == request.faculty_id).all()
            courses = [
                course_pb2.Course(
                    id=str(r.id),
                    code=r.code,
                    title=r.title,
                    description=r.description or "",
                    capacity=r.capacity or 0,
                    term=r.term or "",
                    academic_year=r.academic_year or "",
                    section=r.section or "",
                    assigned_faculty_id=str(r.assigned_faculty_id) if r.assigned_faculty_id else "",
                )
                for r in rows
            ]
            return course_pb2.ListCoursesResponse(courses=courses)
        finally:
            db.close()


def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    course_pb2_grpc.add_CourseServiceServicer_to_server(CourseService(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    server.wait_for_termination()


@app.on_event("startup")
def start_grpc_server():
    thread = threading.Thread(target=serve_grpc, daemon=True)
    thread.start()
