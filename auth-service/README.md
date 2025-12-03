# Auth Service

- **Purpose:** Issue and validate JWTs, handle login/logout, and manage STUDENT/FACULTY roles.
- **Port:** 50051 (gRPC) / 8001 (REST) (adjust as needed).
- **Responsibilities:** Authenticate users, sign JWTs, verify tokens/roles for other services, and expose minimal user info over gRPC to callers like Enrollment and Grade.
- **DS Note:** This node provides authentication and JWT issuance for the distributed system; if it goes down, only auth-dependent flows fail while other nodes stay up.
