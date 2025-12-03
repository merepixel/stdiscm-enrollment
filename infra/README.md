## Infrastructure Assets

- `db/init.sql`: Bootstraps the shared Postgres instance with per-service schemas (`auth`, `course_catalog`, `enrollment`, `grade`) and core tables (`users`, `courses`, `enrollments`, `grades`).
- `docker-compose.yml`: Spins up all nodes (frontend, gateway, auth, course, enrollment, grade, Postgres, Traefik) on user-defined bridge `ds-net` so services communicate via hostnames (`auth-service`, `course-service`, etc.).

### Quick start (via Traefik)

```
cd infra
docker compose up --build
```

- Traefik entrypoint: http://localhost
  - Frontend UI: `/`
  - Gateway API: `/api/*`
  - Gateway health: `/health/gateway` (rewrites to gateway `/health`)
  - Service health probes: `/health/auth`, `/health/course`, `/health/enrollment`, `/health/grade`
  - Direct course-service HTTP (for load-balancing demo): `/svc/course/courses`
- Direct host ports (if you need them): gateway 8000, auth 8001/50051, enrollment 8003/50053, grade 8004/50054, Postgres 5432 (course-service stays behind Traefik to allow scaling)

### Health checks & logs

```
curl http://localhost/health/gateway
curl http://localhost/health/auth
curl http://localhost/health/course
curl http://localhost/health/enrollment
curl http://localhost/health/grade
```

All FastAPI services now emit structured request logs to stdout. Watch them in real time:

```
docker compose logs -f gateway auth-service course-service enrollment-service grade-service
```

### Scaling course-service (Traefik load-balances replicas)

Start (or resize) the stack with multiple course-service containers; Traefik will round-robin HTTP traffic:

```
cd infra
docker compose up --build --scale course-service=2
# later adjustments without rebuild:
docker compose up -d --scale course-service=2
```

Hit the course API a few times and watch the per-container logs to see requests hop between replicas:

```
curl http://localhost/svc/course/courses
docker compose logs -f course-service
```
