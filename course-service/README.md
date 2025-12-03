# Course Service

- **Purpose:** Manage and serve course catalog data (list and detail) for students/enrollment.
- **Ports:** REST `8002`, gRPC `50052`.
- **REST endpoints:** `GET /courses`, `GET /courses/{course_id}`, `GET /health`, `GET /health/db`.
- **gRPC methods:** `ListCourses`, `GetCourse`.
- **DS note:** This node encapsulates the catalog domain; if it goes down, only course viewing (and enrollments needing course metadata) fail while other nodes remain available.
