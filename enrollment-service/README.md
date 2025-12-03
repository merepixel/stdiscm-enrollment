# Enrollment Service

- **Purpose:** Own enrollment business logic (enroll, list, drop) and coordinate with auth/course metadata.
- **Ports:** REST `8003`, gRPC `50053`.
- **REST endpoints:** `POST /enrollments`, `GET /enrollments?student_id=...`, `GET /health`, `GET /health/db`.
- **gRPC methods:** `Enroll`, `ListStudentEnrollments`, `DropEnrollment`.
- **DS note:** This node isolates enrollment; if down, only new enrollments/listing fail while auth/catalog/grades continue to run.
