# Distributed Enrollment System

A microservices-based distributed enrollment system with FastAPI backends and gRPC inter-service calls, fronted by a React gateway-facing UI. The system separates auth, course catalog, enrollment, and grades into isolated nodes so individual failures are contained while still supporting end-to-end workflows.

## Tech Stack
- React (frontend)
- FastAPI (gateway + services)
- gRPC (service-to-service)
- Docker Compose + Traefik/Consul (infra, routing)
- PostgreSQL (primary + optional replica)

## Env setup + deps
cd stdiscm-enrollment
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install fastapi uvicorn pydantic sqlalchemy psycopg2-binary python-jose grpcio grpcio-tools httpx
