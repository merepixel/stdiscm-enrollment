## Smoke test (gateway → CourseService → gRPC)

1. `cd infra && docker compose up --build`
2. Hit `http://localhost/api/smoke/courses` (Traefik routes to gateway, gateway calls CourseService over gRPC).
3. Expected JSON: `{"status":"ok","via":"grpc","courses":[...]}`.

Path: Browser → Traefik (router `/api`) → Gateway (REST) → CourseService (gRPC) → returns courses.
