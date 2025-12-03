import React, { useEffect, useState } from 'react';
import { getMyGrades } from '../api/client';

export default function MyGradesPage() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openKey, setOpenKey] = useState('');

  useEffect(() => {
    let mounted = true;
    getMyGrades() // GET /api/grades/my -> grouped response
      .then((data) => {
        if (!mounted) return;
        const list = data.groups || [];
        setGroups(list);
        if (list.length > 0) {
          setOpenKey(`${list[0].academic_year || ''}__${list[0].term || ''}`);
        }
      })
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
        <p className="text-sm text-gray-600">Grouped by term & academic year</p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {groups.length === 0 && <p className="text-gray-700">No grades yet.</p>}

      <div className="space-y-2">
        {groups.map((group) => {
          const key = `${group.academic_year || ''}__${group.term || ''}`;
          const headerLabel = `AY ${group.academic_year || '—'} • Term ${group.term || '—'}`;
          const isOpen = openKey === key;
          return (
            <div key={key} className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
              <button
                type="button"
                className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100"
                onClick={() => setOpenKey(isOpen ? '' : key)}
              >
                <span className="text-sm font-semibold text-gray-900">{headerLabel}</span>
                <span className="text-xs text-gray-600">{isOpen ? 'Hide' : 'Show'}</span>
              </button>
              {isOpen && (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200 text-sm">
                    <thead className="bg-gray-50 text-left">
                      <tr>
                        <th className="px-4 py-2 font-semibold text-gray-700">Course ID</th>
                        <th className="px-4 py-2 font-semibold text-gray-700">Course Name</th>
                        <th className="px-4 py-2 font-semibold text-gray-700">Grade</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {(group.courses || []).map((c) => (
                        <tr key={c.course_id} className="hover:bg-gray-50">
                          <td className="px-4 py-2 text-gray-900">{c.course_code || '—'}</td>
                          <td className="px-4 py-2 text-gray-700">{c.course_name || '—'}</td>
                          <td className="px-4 py-2 text-gray-900 font-semibold">{c.grade || 'In Progress'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
