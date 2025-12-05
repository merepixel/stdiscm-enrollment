import React, { useCallback, useEffect, useRef, useState } from 'react';
import { enrollInCourse, getCourses } from '../api/client';
import Button from '../components/Button';
import { useAuth } from '../context/AuthContext';

export default function CoursesPage() {
  const { user, isAuthenticated } = useAuth();
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [enrollingId, setEnrollingId] = useState('');
  const mountedRef = useRef(true);

  const loadCourses = useCallback(
    async (showLoading = false) => {
      if (showLoading) setLoading(true);
      try {
        const data = await getCourses(); // GET /api/courses
        if (!mountedRef.current) return;
        setCourses(data.courses || []);
      } catch (err) {
        if (!mountedRef.current) return;
        setMessage(err?.response?.data?.detail || 'Failed to load courses');
      } finally {
        if (showLoading && mountedRef.current) setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    mountedRef.current = true;
    loadCourses(true);
    const id = setInterval(() => loadCourses(false), 15000);
    const onFocus = () => loadCourses(false);
    const onVisibility = () => {
      if (!document.hidden) loadCourses(false);
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [loadCourses]);

  const handleEnroll = async (courseId) => {
    setMessage('');
    setEnrollingId(courseId);
    try {
      await enrollInCourse(courseId); // POST /api/enrollments/
      await loadCourses(false);
      setMessage('Enrollment request sent; availability refreshed.');
    } catch (err) {
      setMessage(err?.response?.data?.detail || 'Enrollment failed');
    } finally {
      setEnrollingId('');
    }
  };

  if (loading) {
    return <p className="p-4 text-gray-600">Loading courses...</p>;
  }

  return (
    <section className="space-y-3">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Courses</h1>
        <p className="text-sm text-gray-600">// uses GET /api/courses</p>
      </div>
      {message && <p className="text-sm text-blue-700 bg-blue-50 border border-blue-100 rounded-md px-3 py-2">{message}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {courses.map((c) => (
          <article key={c.id} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm flex flex-col gap-2">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">{c.code} — {c.title}</h3>
                <p className="text-sm text-gray-600">{c.description}</p>
                <p className="text-xs text-gray-500 mt-1">Section: {c.section || 'N/A'} | Term: {c.term || '—'} | AY: {c.academic_year || '—'}</p>
              </div>
              <span className="text-xs px-2 py-1 rounded-full bg-gray-100 text-gray-700">
                Cap {Math.max(c.available ?? c.capacity ?? 0, 0)}{c.capacity ? `/${c.capacity}` : ''}
              </span>
            </div>
            {isAuthenticated && user?.role === 'STUDENT' && (
              <Button
                className="self-start"
                onClick={() => handleEnroll(c.id)}
                disabled={enrollingId === c.id}
              >
                {enrollingId === c.id ? 'Enrolling...' : 'Enroll'}
              </Button>
            )}
          </article>
        ))}
        {courses.length === 0 && <p className="text-gray-600">No courses available.</p>}
      </div>
    </section>
  );
}
