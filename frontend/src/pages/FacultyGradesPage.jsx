import React, { useState } from 'react';
import { submitGrade } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function FacultyGradesPage() {
  const { user } = useAuth();
  const [form, setForm] = useState({
    student_id: '',
    course_id: '',
    term: '',
    grade: '',
  });
  const [message, setMessage] = useState('');

  const handleChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage('');
    try {
      await submitGrade(form); // POST /api/grades/
      setMessage('Grade submitted');
    } catch (err) {
      setMessage(err?.response?.data?.detail || 'Submit failed');
    }
  };

  return (
    <section style={{ padding: '1rem' }}>
      <h1>Faculty Grade Submission</h1>
      <p>// uses POST /api/grades/ (faculty role required)</p>
      {user?.role !== 'FACULTY' && <p style={{ color: 'red' }}>FACULTY role recommended for this page.</p>}
      <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '0.5rem', maxWidth: '360px' }}>
        <label>
          Student ID
          <input value={form.student_id} onChange={(e) => handleChange('student_id', e.target.value)} required />
        </label>
        <label>
          Course ID
          <input value={form.course_id} onChange={(e) => handleChange('course_id', e.target.value)} required />
        </label>
        <label>
          Term
          <input value={form.term} onChange={(e) => handleChange('term', e.target.value)} required />
        </label>
        <label>
          Grade
          <input value={form.grade} onChange={(e) => handleChange('grade', e.target.value)} required />
        </label>
        <button type="submit">Submit Grade</button>
      </form>
      {message && <p>{message}</p>}
    </section>
  );
}
