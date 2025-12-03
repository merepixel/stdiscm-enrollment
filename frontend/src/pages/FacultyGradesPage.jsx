import React, { useState } from 'react';
import { submitGrade } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Button from '../components/Button';

export default function FacultyGradesPage() {
  const { user } = useAuth();
  const [form, setForm] = useState({
    student_id: '',
    course_id: '',
    term: '',
    grade: '',
  });
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage('');
    setLoading(true);
    try {
      await submitGrade(form); // POST /api/grades/
      setMessage('Grade submitted');
      setForm({ student_id: '', course_id: '', term: '', grade: '' });
    } catch (err) {
      setMessage(err?.response?.data?.detail || 'Submit failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="space-y-3">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Faculty Grade Submission</h1>
        <p className="text-sm text-gray-600">// uses POST /api/grades/ (faculty role required)</p>
      </div>
      {user?.role !== 'FACULTY' && (
        <p className="text-sm text-red-600">FACULTY role recommended for this page.</p>
      )}
      <div className="max-w-xl rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Student ID</label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
                value={form.student_id}
                onChange={(e) => handleChange('student_id', e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Course ID</label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
                value={form.course_id}
                onChange={(e) => handleChange('course_id', e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Term</label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
                value={form.term}
                onChange={(e) => handleChange('term', e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Grade</label>
              <input
                className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
                value={form.grade}
                onChange={(e) => handleChange('grade', e.target.value)}
                required
              />
            </div>
          </div>
          <Button type="submit" disabled={loading}>
            {loading ? 'Submitting...' : 'Submit Grade'}
          </Button>
        </form>
        {message && <p className="mt-3 text-sm text-blue-700 bg-blue-50 border border-blue-100 rounded-md px-3 py-2">{message}</p>}
      </div>
    </section>
  );
}
