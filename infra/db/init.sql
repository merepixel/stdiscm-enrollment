-- Shared Postgres instance with per-service schemas to keep ownership boundaries.
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS course_catalog;
CREATE SCHEMA IF NOT EXISTS enrollment;
CREATE SCHEMA IF NOT EXISTS grade;

-- UUIDs for primary keys.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Auth service owned table.
CREATE TABLE IF NOT EXISTS auth.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('STUDENT', 'FACULTY')),
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth.users (role);

-- Course catalog service owned table.
CREATE TABLE IF NOT EXISTS course_catalog.courses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(32) NOT NULL UNIQUE,
    title TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enrollment service owned table.
CREATE TABLE IF NOT EXISTS enrollment.enrollments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES course_catalog.courses (id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('ENROLLED', 'WAITLISTED', 'DROPPED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, course_id)
);
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollment.enrollments (student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollment.enrollments (course_id);

-- Grade service owned table.
CREATE TABLE IF NOT EXISTS grade.grades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES course_catalog.courses (id) ON DELETE CASCADE,
    term VARCHAR(32) NOT NULL,
    grade TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, course_id, term)
);
CREATE INDEX IF NOT EXISTS idx_grades_student ON grade.grades (student_id);
CREATE INDEX IF NOT EXISTS idx_grades_course ON grade.grades (course_id);
