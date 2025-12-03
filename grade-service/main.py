import concurrent.futures as futures
import os
import sys
import threading
from pathlib import Path
from typing import List
from uuid import uuid4

import grpc
from fastapi import Depends, FastAPI, HTTPException
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
    course_id = Column(UUID(as_uuid=True), nullable=False)
    term = Column(String(32), nullable=False)
    grade = Column(Text, nullable=False)


app = FastAPI(title="Grade Service", version="0.1.0")


class GradeIn(BaseModel):
    student_id: str
    course_id: str
    term: str
    grade: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
@app.post("/grades")
def submit_grade(body: GradeIn, db: Session = Depends(get_db)):
    rec = Grade(
        student_id=body.student_id,
        course_id=body.course_id,
        term=body.term,
        grade=body.grade,
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Grade already exists for student/course/term")
    db.refresh(rec)
    return {
        "id": str(rec.id),
        "student_id": str(rec.student_id),
        "course_id": str(rec.course_id),
        "term": rec.term,
        "grade": rec.grade,
    }


@app.get("/grades")
def list_grades(student_id: str, db: Session = Depends(get_db)):
    rows = db.query(Grade).filter(Grade.student_id == student_id).all()
    return [
        {
            "id": str(g.id),
            "student_id": str(g.student_id),
            "course_id": str(g.course_id),
            "term": g.term,
            "grade": g.grade,
        }
        for g in rows
    ]


# ---------- gRPC service ----------
class GradeService(grade_pb2_grpc.GradeServiceServicer):
    def SubmitGrade(self, request, context):
        db = SessionLocal()
        try:
            rec = Grade(
                student_id=request.student_id,
                course_id=request.course_id,
                term=request.term,
                grade=request.grade,
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            return grade_pb2.SubmitGradeResponse(
                record=grade_pb2.GradeRecord(
                    id=str(rec.id),
                    student_id=str(rec.student_id),
                    course_id=str(rec.course_id),
                    term=rec.term,
                    grade=rec.grade,
                )
            )
        except IntegrityError:
            db.rollback()
            context.set_code(grpc.StatusCode.ALREADY_EXISTS)
            context.set_details("Grade already exists for student/course/term")
            return grade_pb2.SubmitGradeResponse()
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
                    grade=g.grade,
                )
                for g in rows
            ]
            return grade_pb2.ListGradesResponse(grades=items)
        finally:
            db.close()


def serve_grpc():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    grade_pb2_grpc.add_GradeServiceServicer_to_server(GradeService(), server)
    server.add_insecure_port("[::]:50054")
    server.start()
    server.wait_for_termination()


@app.on_event("startup")
def start_grpc_server():
    thread = threading.Thread(target=serve_grpc, daemon=True)
    thread.start()
