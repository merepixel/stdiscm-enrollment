## Smoke test (gateway → CourseService → gRPC)

1. `cd infra && docker compose up --build`
2. Hit `http://localhost:8000/api/smoke/courses` (Gateway calls CourseService over gRPC).
3. Expected JSON: `{"status":"ok","via":"grpc","courses":[...]}`.

Path: Browser → Gateway (REST) → CourseService (gRPC) → returns courses.
