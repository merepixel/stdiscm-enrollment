import React, { useEffect, useMemo, useState } from 'react';
import { getCourses, getMyEnrollments } from '../api/client';
import Button from '../components/Button';

const STATUS_LABELS = {
  1: 'Enrolled',
  2: 'Waitlisted',
  3: 'Dropped',
  ENROLLED: 'Enrolled',
  WAITLISTED: 'Waitlisted',
  DROPPED: 'Dropped',
};

function enrollmentStatusLabel(status) {
  return STATUS_LABELS[status] || STATUS_LABELS[String(status)] || 'Enrolled';
}

function statusBadgeClass(status) {
  const label = enrollmentStatusLabel(status).toUpperCase();
  if (label === 'WAITLISTED') return 'bg-amber-50 text-amber-700';
  if (label === 'DROPPED') return 'bg-gray-100 text-gray-700';
  return 'bg-green-50 text-green-700';
}

export default function MyEnrollmentsPage() {
  const [enrollments, setEnrollments] = useState([]);
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    Promise.all([getMyEnrollments(), getCourses()]) // GET /api/enrollments/my + GET /api/courses
      .then(([enrollmentData, courseData]) => {
        if (!mounted) return;
        setEnrollments(enrollmentData.enrollments || []);
        setCourses(courseData.courses || []);
      })
      .catch((err) => mounted && setError(err?.response?.data?.detail || 'Failed to load enrollments'))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  const courseLookup = useMemo(() => {
    const map = {};
    courses.forEach((c) => {
      map[c.id] = c;
    });
    return map;
  }, [courses]);

  if (loading) {
    return <p className="p-4 text-gray-600">Loading enrollments...</p>;
  }

  return (
    <section className="space-y-3">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">My Enrollments</h1>
        <p className="text-sm text-gray-600">// uses GET /api/enrollments/my</p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {enrollments.map((e) => {
          const course = courseLookup[e.course_id];
          const label = enrollmentStatusLabel(e.status);
          return (
            <article key={e.id} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm flex flex-col gap-2">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    {course ? `${course.code} — ${course.title}` : `Course ${e.course_id}`}
                  </h3>
                  <p className="text-sm text-gray-600">
                    {course?.description || 'Course details not available.'}
                  </p>
                </div>
                {course && (
                  <span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700 whitespace-nowrap">
                    Cap {Math.max(course.available ?? course.capacity ?? 0, 0)}{course.capacity ? `/${course.capacity}` : ''}
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className={`text-xs px-3 py-1 rounded-full uppercase tracking-wide font-semibold ${statusBadgeClass(e.status)}`}>
                  {label}
                </span>
                <Button
                  as="span"
                  variant="ghost"
                  className="self-start bg-gray-100 text-gray-500 border border-gray-200 cursor-default pointer-events-none"
                  aria-disabled="true"
                >
                  Enrolled
                </Button>
              </div>
            </article>
          );
        })}
        {enrollments.length === 0 && <p className="text-gray-600">You have no enrollments yet.</p>}
      </div>
    </section>
  );
}
