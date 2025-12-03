import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import concurrent.futures as futures

import grpc
from fastapi import FastAPI, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
PROTO_PATH = BASE_DIR / "common" / "protos"
if str(PROTO_PATH) not in sys.path:
    sys.path.append(str(PROTO_PATH))

try:
    from common.protos import auth_pb2, auth_pb2_grpc
except ImportError as exc:  # pragma: no cover
    raise ImportError("Protos not generated or not on PYTHONPATH. Run `make protos`.") from exc

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/enrollment")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
GRPC_PORT = int(os.getenv("AUTH_GRPC_PORT", "50051"))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="Auth Service", version="0.1.0")

SERVICE_NAME = "auth-service"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logger = logging.getLogger(SERVICE_NAME)


class LoginRequest(BaseModel):
    email: str
    password: str


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


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # If hash is not bcrypt formatted, fallback to direct comparison for dev seeding
        return plain_password == hashed_password


def create_access_token(user_id: str, email: str, role: str, user_number: Optional[str] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "user_number": user_number,
        "exp": expire,
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


@app.post("/login")
def login(body: LoginRequest):
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, user_number, email, password_hash, role FROM auth.users WHERE email = :email"
                ),
                {"email": body.email},
            ).mappings().first()
    except SQLAlchemyError as exc:
        logger.error("DB error during login: %s", exc)
        raise HTTPException(status_code=500, detail=f"DB error: {exc}") from exc

    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_number = row.get("user_number") or str(row["id"])
    token = create_access_token(str(row["id"]), row["email"], row["role"], user_number)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": row["role"],
        "id": user_number,
        "user_id": str(row["id"]),
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth-service"}


@app.get("/health/db")
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "service": "auth-service", "db": "connected"}
    except Exception as exc:  # pragma: no cover - simple probe
        return {"status": "error", "service": "auth-service", "db": "unreachable", "detail": str(exc)}


class AuthService(auth_pb2_grpc.AuthServiceServicer):
    def ValidateToken(self, request, context):
        try:
            payload = jwt.decode(request.token, JWT_SECRET, algorithms=[JWT_ALG])
            role_value = payload.get("role", "")
            role_enum = (
                auth_pb2.Role.Value(role_value)
                if role_value in auth_pb2.Role.keys()
                else auth_pb2.Role.ROLE_UNSPECIFIED
            )
            return auth_pb2.TokenValidationResponse(
                valid=True,
                user_id=payload.get("sub", ""),
                email=payload.get("email", ""),
                role=role_enum,
                reason="",
            )
        except JWTError as exc:
            return auth_pb2.TokenValidationResponse(
                valid=False,
                user_id="",
                email="",
                role=auth_pb2.Role.ROLE_UNSPECIFIED,
                reason=str(exc),
            )

    def GetUser(self, request, context):
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT id, name, email, role FROM auth.users WHERE id = :id"),
                    {"id": request.user_id},
                ).mappings().first()
        except SQLAlchemyError as exc:
            context.set_details(f"DB error: {exc}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return auth_pb2.GetUserResponse()

        if not row:
            context.set_details("User not found")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            return auth_pb2.GetUserResponse()

        role_enum = (
            auth_pb2.Role.Value(row["role"])
            if row["role"] in auth_pb2.Role.keys()
            else auth_pb2.Role.ROLE_UNSPECIFIED
        )
        user = auth_pb2.User(id=str(row["id"]), name=row["name"], email=row["email"], role=role_enum)
        return auth_pb2.GetUserResponse(user=user)


def serve_grpc():
    #server = grpc.server(thread_pool=threading.ThreadPoolExecutor(max_workers=10))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthService(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    server.wait_for_termination()


@app.on_event("startup")
def start_grpc_server():
    thread = threading.Thread(target=serve_grpc, daemon=True)
    thread.start()
