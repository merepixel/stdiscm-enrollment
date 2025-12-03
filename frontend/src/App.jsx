import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import NavBar from './components/NavBar';
import { ProtectedRoute } from './context/AuthContext';
import CoursesPage from './pages/CoursesPage';
import FacultyGradesPage from './pages/FacultyGradesPage';
import LoginPage from './pages/LoginPage';
import MyEnrollmentsPage from './pages/MyEnrollmentsPage';
import MyGradesPage from './pages/MyGradesPage';

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <NavBar />
      <main className="max-w-5xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<CoursesPage />} />
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/my-enrollments"
            element={
              <ProtectedRoute allowRoles={['STUDENT']}>
                <MyEnrollmentsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/my-grades"
            element={
              <ProtectedRoute allowRoles={['STUDENT']}>
                <MyGradesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/faculty/grades"
            element={
              <ProtectedRoute requireRole="FACULTY">
                <FacultyGradesPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/courses" replace />} />
        </Routes>
      </main>
    </div>
  );
}
