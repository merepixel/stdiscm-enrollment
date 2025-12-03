# Grade Service

- **Purpose:** Store and serve grade records; allow faculty to submit grades.
- **Ports:** REST `8004`, gRPC `50054`.
- **REST endpoints:** `POST /grades`, `GET /grades?student_id=...`, `GET /health`, `GET /health/db`.
- **gRPC methods:** `SubmitGrade`, `ListGrades`.
- **DS note:** This node isolates grading; if down, only grade submission/viewing fails while auth/catalog/enrollment keep serving.
