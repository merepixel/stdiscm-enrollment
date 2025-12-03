import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { getToken, login as apiLogin, setToken } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [token, setAuthToken] = useState(() => getToken());
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem('enrollment_user');
    return stored ? JSON.parse(stored) : null;
  });

  useEffect(() => {
    if (user) {
      localStorage.setItem('enrollment_user', JSON.stringify(user));
    } else {
      localStorage.removeItem('enrollment_user');
    }
  }, [user]);

  const login = async (email, password) => {
    const data = await apiLogin(email, password);
    setToken(data.access_token);
    setAuthToken(data.access_token);
    setUser({ email, role: data.role, user_id: data.user_id });
    navigate('/courses');
  };

  const logout = () => {
    setToken(null);
    setAuthToken(null);
    setUser(null);
    navigate('/login');
  };

  const value = useMemo(
    () => ({
      token,
      user,
      isAuthenticated: Boolean(token),
      login,
      logout,
    }),
    [token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}

export function ProtectedRoute({ children, requireRole }) {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requireRole && user?.role !== requireRole) {
    return <p style={{ padding: '1rem' }}>Access denied: {requireRole} role required.</p>;
  }

  return children;
}
