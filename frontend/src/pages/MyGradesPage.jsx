import React, { useEffect, useState } from 'react';
import { getMyGrades } from '../api/client';

export default function MyGradesPage() {
  const [grades, setGrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    getMyGrades() // GET /api/grades/my
      .then((data) => mounted && setGrades(data.grades || []))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load grades'))
      .finally(() => setLoading(false));
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <p style={{ padding: '1rem' }}>Loading grades...</p>;
  }

  return (
    <section style={{ padding: '1rem' }}>
      <h1>My Grades</h1>
      <p>// uses GET /api/grades/my</p>
      {error && <p style={{ color: 'red' }}>{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Course</th>
            <th>Term</th>
            <th>Grade</th>
          </tr>
        </thead>
        <tbody>
          {grades.map((g) => (
            <tr key={g.id}>
              <td>{g.course_id}</td>
              <td>{g.term}</td>
              <td>{g.grade}</td>
            </tr>
          ))}
          {grades.length === 0 && (
            <tr>
              <td colSpan={3}>No grades yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
