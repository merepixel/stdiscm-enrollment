import os

from fastapi import FastAPI
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/enrollment")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

app = FastAPI(title="Enrollment Service", version="0.1.0")


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
