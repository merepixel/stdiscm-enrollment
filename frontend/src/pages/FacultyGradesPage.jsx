import React, { useEffect, useMemo, useState } from 'react';
import { getAssignedCourses, getCourseRoster, submitGradesBulk } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Button from '../components/Button';

export default function FacultyGradesPage() {
  const { user } = useAuth();
  const [courses, setCourses] = useState([]);
  const [selectedCourseId, setSelectedCourseId] = useState('');
  const [roster, setRoster] = useState([]);
  const [grades, setGrades] = useState({});
  const [message, setMessage] = useState('');
  const [loadingCourses, setLoadingCourses] = useState(false);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const gradeOptions = useMemo(
    () => ['4.0', '3.5', '3.0', '2.5', '2.0', '1.5', '1.0', '0.0', '9.9'],
    []
  );

  useEffect(() => {
    const loadCourses = async () => {
      setLoadingCourses(true);
      setMessage('');
      try {
        const data = await getAssignedCourses();
        setCourses(data.courses || []);
        if ((data.courses || []).length > 0) {
          setSelectedCourseId(data.courses[0].id);
        }
      } catch (err) {
        setMessage(err?.response?.data?.detail || 'Failed to load courses');
      } finally {
        setLoadingCourses(false);
      }
    };
    if (user?.role === 'FACULTY') {
      loadCourses();
    }
  }, [user]);

  useEffect(() => {
    const loadRoster = async () => {
      if (!selectedCourseId) {
        setRoster([]);
        setGrades({});
        return;
      }
      setLoadingRoster(true);
      setMessage('');
      try {
        const data = await getCourseRoster(selectedCourseId);
        setRoster(data.roster || []);
        // Prefill grades from backend if present
        const prefilled = {};
        (data.roster || []).forEach((r) => {
          if (r.grade) {
            prefilled[r.student_id] = r.grade;
          }
        });
        setGrades(prefilled);
      } catch (err) {
        setMessage(err?.response?.data?.detail || 'Failed to load roster');
        setRoster([]);
        setGrades({});
      } finally {
        setLoadingRoster(false);
      }
    };
    loadRoster();
  }, [selectedCourseId]);

  const selectedCourse = courses.find((c) => c.id === selectedCourseId);

  const handleGradeChange = (studentId, value) => {
    setGrades((prev) => ({ ...prev, [studentId]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage('');
    if (!selectedCourse) {
      setMessage('Please select a course.');
      return;
    }
    const missing = roster.filter((r) => !grades[r.student_id]);
    if (missing.length > 0) {
      setMessage('Please select a grade for every student.');
      return;
    }
    setSubmitting(true);
    try {
      await submitGradesBulk({
        course_id: selectedCourse.id,
        term: selectedCourse.term || '',
        academic_year: selectedCourse.academic_year || '',
        records: roster.map((r) => ({ student_id: r.student_id, grade: grades[r.student_id] })),
      });
      setMessage('Grades submitted');
    } catch (err) {
      setMessage(err?.response?.data?.detail || 'Submit failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-3">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Faculty Grade Submission</h1>
        <p className="text-sm text-gray-600">// uses faculty courses + roster + bulk grade upsert</p>
      </div>
      {user?.role !== 'FACULTY' && (
        <p className="text-sm text-red-600">FACULTY role recommended for this page.</p>
      )}
      <div className="space-y-4">
        <div className="max-w-xl rounded-lg border border-gray-200 bg-white p-5 shadow-sm space-y-3">
          <label className="block text-sm font-medium text-gray-700">Select course / section</label>
          <select
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
            value={selectedCourseId}
            onChange={(e) => setSelectedCourseId(e.target.value)}
            disabled={loadingCourses}
          >
            <option value="">-- choose a course --</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} - {c.title} (Section {c.section || 'N/A'}, Term {c.term || '?'}, AY {c.academic_year || '?'})
              </option>
            ))}
          </select>
          {loadingCourses && <p className="text-sm text-gray-600">Loading courses...</p>}
          {selectedCourse && (
            <p className="text-xs text-gray-500">
              Course uses term "{selectedCourse.term || '-'}" and AY "{selectedCourse.academic_year || '-'}".
            </p>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Roster</h2>
              <p className="text-sm text-gray-600">Choose a grade for each enrolled student.</p>
            </div>
            {loadingRoster && <p className="text-sm text-gray-600">Loading roster...</p>}
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    Student
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    ID Number
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                    Grade
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {roster.map((r) => (
                  <tr key={r.student_id} className="bg-white">
                    <td className="px-4 py-2 text-sm text-gray-900">{r.student_name || 'Unknown'}</td>
                    <td className="px-4 py-2 text-sm text-gray-700">{r.user_number || '—'}</td>
                    <td className="px-4 py-2">
                      <select
                        className="w-full rounded-md border border-gray-300 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
                        value={grades[r.student_id] || ''}
                        onChange={(e) => handleGradeChange(r.student_id, e.target.value)}
                      >
                        <option value="">Select grade</option>
                        {gradeOptions.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
                {roster.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-4 text-sm text-gray-600">
                      {selectedCourseId
                        ? loadingRoster
                          ? 'Loading roster...'
                          : 'No enrolled students found.'
                        : 'Select a course to see the roster.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button type="button" disabled={submitting || roster.length === 0} onClick={handleSubmit}>
            {submitting ? 'Submitting...' : 'Submit Grades'}
          </Button>
          {selectedCourse && (
            <p className="text-xs text-gray-500">
              Grades will be upserted for term "{selectedCourse.term || '-'}" and AY "{selectedCourse.academic_year || '-'}".
            </p>
          )}
        </div>

        {message && (
          <p className="mt-2 text-sm text-blue-700 bg-blue-50 border border-blue-100 rounded-md px-3 py-2">
            {message}
          </p>
        )}
      </div>
    </section>
  );
}
