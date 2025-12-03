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
    return <p className="p-4 text-gray-600">Loading grades...</p>;
  }

  return (
    <section className="space-y-3">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">My Grades</h1>
        <p className="text-sm text-gray-600">// uses GET /api/grades/my</p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50 text-left">
              <tr>
                <th className="px-4 py-2 font-semibold text-gray-700">Course</th>
                <th className="px-4 py-2 font-semibold text-gray-700">Term</th>
                <th className="px-4 py-2 font-semibold text-gray-700">Grade</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {grades.map((g) => (
                <tr key={g.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-gray-900">{g.course_id}</td>
                  <td className="px-4 py-2 text-gray-700">{g.term}</td>
                  <td className="px-4 py-2 text-gray-900 font-semibold">{g.grade}</td>
                </tr>
              ))}
              {grades.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-3 text-gray-600">No grades yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
