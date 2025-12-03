# Auth Service

- **Purpose:** Issue/validate JWTs, expose login, and provide user/role info to other nodes.
- **Ports:** REST `8001`, gRPC `50051`.
- **REST endpoints:** `POST /login`, `GET /health`, `GET /health/db`.
- **gRPC methods:** `ValidateToken`, `GetUser`.
- **DS note:** This node encapsulates authentication; if it is down, logins and token validation fail, but other nodes keep serving cached-token flows until auth is required.
