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
    user_number VARCHAR(32),
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('STUDENT', 'FACULTY')),
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS user_number VARCHAR(32);
CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth.users (role);
CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_number ON auth.users (user_number);

-- Course catalog service owned table.
CREATE TABLE IF NOT EXISTS course_catalog.courses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(32) NOT NULL,
    title TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Allow multiple sections per course code; remove legacy unique constraint on code.
ALTER TABLE course_catalog.courses DROP CONSTRAINT IF EXISTS courses_code_key;
ALTER TABLE course_catalog.courses ADD COLUMN IF NOT EXISTS term VARCHAR(32);
ALTER TABLE course_catalog.courses ADD COLUMN IF NOT EXISTS academic_year VARCHAR(32);
ALTER TABLE course_catalog.courses ADD COLUMN IF NOT EXISTS section VARCHAR(16);
ALTER TABLE course_catalog.courses ADD COLUMN IF NOT EXISTS assigned_faculty_id UUID REFERENCES auth.users (id);
CREATE INDEX IF NOT EXISTS idx_courses_assigned_faculty_id ON course_catalog.courses (assigned_faculty_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_courses_code_term_year_section
    ON course_catalog.courses (code, term, academic_year, section);

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
ALTER TABLE grade.grades ADD COLUMN IF NOT EXISTS academic_year VARCHAR(32);

-- Seed demo users (plain text passwords allowed by auth-service fallback).
INSERT INTO auth.users (id, user_number, name, email, role, password_hash)
VALUES
  ('00000000-0000-0000-0000-000000000001', '12110007', 'Alice Student', 'student@example.com', 'STUDENT', '$2b$12$Vjl0bSjCP5OMqJl9nOYHH.d8ZyjuqsCuCFgUSYicL8GnAAih2QqOG'),
  ('00000000-0000-0000-0000-000000000002', '10212345', 'Bob Faculty', 'faculty@example.com', 'FACULTY', '$2b$12$Vjl0bSjCP5OMqJl9nOYHH.d8ZyjuqsCuCFgUSYicL8GnAAih2QqOG')
ON CONFLICT (email) DO UPDATE SET user_number = EXCLUDED.user_number;

-- Seed demo courses.
INSERT INTO course_catalog.courses (id, code, title, description, capacity, term, academic_year, section, assigned_faculty_id)
VALUES
  ('10000000-0000-0000-0000-000000000001', 'CS101', 'Intro to CS', 'Basics of computer science', 50, '1', '2025-2026', 'A', '00000000-0000-0000-0000-000000000002'),
  ('20000000-0000-0000-0000-000000000002', 'DS201', 'Distributed Systems', 'Consensus, replication, microservices', 40, '2', '2025-2026', 'A', '00000000-0000-0000-0000-000000000002'),
  ('20000000-0000-0000-0000-000000000003', 'DS201', 'Distributed Systems', 'Consensus, replication, microservices', 40, '2', '2025-2026', 'B', '00000000-0000-0000-0000-000000000002')
ON CONFLICT (code, term, academic_year, section) DO UPDATE
SET title = EXCLUDED.title,
    description = EXCLUDED.description,
    capacity = EXCLUDED.capacity,
    term = EXCLUDED.term,
    academic_year = EXCLUDED.academic_year,
    section = EXCLUDED.section,
    assigned_faculty_id = EXCLUDED.assigned_faculty_id;

-- Seed past grade.

INSERT INTO grade.grades (student_id, course_id, term, academic_year,grade)
VALUES (
    '00000000-0000-0000-0000-000000000001', 
    '10000000-0000-0000-0000-000000000001', 
    '1',                                    
    '2025-2026',                            
    '4.0'                                  
);

