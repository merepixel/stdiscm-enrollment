import React, { useEffect, useState } from 'react';
import { getMyEnrollments } from '../api/client';

export default function MyEnrollmentsPage() {
  const [enrollments, setEnrollments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    getMyEnrollments() // GET /api/enrollments/my
      .then((data) => mounted && setEnrollments(data.enrollments || []))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load enrollments'))
      .finally(() => setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <p style={{ padding: '1rem' }}>Loading enrollments...</p>;
  }

  return (
    <section style={{ padding: '1rem' }}>
      <h1>My Enrollments</h1>
      <p>// uses GET /api/enrollments/my</p>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <ul>
        {enrollments.map((e) => (
          <li key={e.id}>
            Course: {e.course_id} — Status: {e.status}
          </li>
        ))}
      </ul>
      {enrollments.length === 0 && <p>You have no enrollments yet.</p>}
    </section>
  );
}
