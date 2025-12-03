## Infrastructure Assets

- `db/init.sql`: Bootstraps the shared Postgres instance with per-service schemas (`auth`, `course_catalog`, `enrollment`, `grade`) and core tables (`users`, `courses`, `enrollments`, `grades`).
- `docker-compose.yml`: Spins up all nodes (frontend, gateway, auth, course, enrollment, grade, Postgres, Traefik) on `backend_net`.

### Quick start

```
cd infra
docker compose up --build
```

- Traefik: http://localhost (routes `/api` to gateway).
- Gateway direct: http://localhost:8000/health
- Services: `auth-service` (8001), `course-service` (8002), `enrollment-service` (8003), `grade-service` (8004) via container network.
- Frontend dev server: http://localhost:3000
