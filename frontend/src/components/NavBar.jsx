import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Button from './Button';

export default function NavBar() {
  const { isAuthenticated, user, logout } = useAuth();
  const location = useLocation();

  const links = [
    { to: '/courses', label: 'Courses' },
    { to: '/my-enrollments', label: 'My Enrollments' },
    { to: '/my-grades', label: 'My Grades' },
    { to: '/faculty/grades', label: 'Faculty Grades' },
  ];

  return (
    <header className="bg-white shadow-sm">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
        <Link to="/courses" className="text-lg font-semibold text-gray-900">Enrollment Portal</Link>
        {isAuthenticated && (
          <nav className="flex items-center gap-3 text-sm">
            {links.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`px-2 py-1 rounded hover:bg-gray-100 ${
                  location.pathname.startsWith(link.to) ? 'text-accent font-medium' : 'text-gray-700'
                }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-3">
          {isAuthenticated ? (
            <>
              <span className="text-sm text-gray-600 hidden sm:inline">
                {user?.email} ({user?.role})
              </span>
              <Button variant="ghost" onClick={logout}>Logout</Button>
            </>
          ) : (
            <Button as={Link} to="/login">
              Login
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
