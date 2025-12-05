# Distributed Enrollment System

A microservices-based enrollment system with FastAPI backends, gRPC inter-service calls, a React UI, and a FastAPI gateway. Each node runs on its own hostname/port so partial failures are easy to demonstrate.

## Network topology (Docker Compose)

All services attach to the user-defined bridge `ds-net`; inside Docker they talk via service hostnames instead of `localhost`.

| Node / Service | Hostname | HTTP Port (host) | gRPC Port (host) | Notes |
| --- | --- | --- | --- | --- |
| Gateway | `gateway` | 8000 (`localhost:8000`) | — | Routes all frontend traffic |
| Auth Service | `auth-service` | 8001 (`localhost:8001`) | 50051 (`localhost:50051`) | Issues JWTs |
| Course Service | `course-service` | 8002 (`localhost:8002`) | 50052 (`localhost:50052`) | Catalog |
| Enrollment Service | `enrollment-service` | 8003 (`localhost:8003`) | 50053 (`localhost:50053`) | Student enrollments |
| Grade Service | `grade-service` | 8004 (`localhost:8004`) | 50054 (`localhost:50054`) | Grades |
| Frontend (Vite) | `frontend` | 3000 (`localhost:3000`) | — | Talks only to gateway |
| Postgres | `db` | 5432 (`localhost:5432`) | — | Shared DB with per-service schemas |
| Traefik | `traefik` | 80 (`localhost`) | — | Optional edge router |

## Run the stack

```
make protos
cd infra
docker compose up --build
```

- UI: http://localhost:3000
- Gateway health: http://localhost:8000/api/ping
- Gateway smoke (gRPC to Course Service): http://localhost:8000/api/smoke/courses

Quick probes:

```
curl -i http://localhost:8000/api/ping
curl -i http://localhost:8000/api/smoke/courses
```

`frontend` uses `VITE_API_BASE_URL=http://localhost:8000/api` so all browser calls go through the gateway. The gateway reaches downstream services via their hostnames (`auth-service:8001`, `course-service:8002`, etc.) and gRPC targets (`auth-service:50051`, ...).

## Demo partial failures

- Stop course service: `docker compose stop course-service`
  - `/api/courses` and `/api/smoke/courses` should 503 (e.g., `curl -i http://localhost:8000/api/courses`).
  - Gateway `/api/ping` and auth flows keep working.
- Stop grade service: `docker compose stop grade-service`
  - `/api/grades/*` should 503.
  - Auth/courses/enrollments remain functional.
- Stop auth service: `docker compose stop auth-service`
  - `/api/auth/login` fails; public endpoints like `/api/ping` still work.

Restart any node with `docker compose start <service>`.

## Local testing

- End-to-end tests default to the gateway at `BASE_URL=http://localhost:8000`.
- Quick smoke: `./scripts/smoke.sh` (waits for gateway, hits `/api/ping` + `/api/smoke/courses`).

## Authentication and logout (JWT)

- Auth service issues stateless JWTs signed with a shared key; expiry/refresh are handled by the token itself (no server-side sessions or revocation list).
- The frontend stores the access token in `localStorage` under `enrollment_jwt` (see `frontend/src/api/client.js`) and caches user metadata in `localStorage` as `enrollment_user`.
- The navbar exposes a `Logout` button for authenticated users; clicking it clears both local storage entries via `AuthContext.logout`, resets in-memory auth state, and redirects to the login page.
- Protected routes simply check for the presence of the JWT; if the token is expired or invalid the backend rejects requests and users can log back in to obtain a fresh token.
