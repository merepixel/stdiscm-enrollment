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
    setUser({
      email,
      role: data.role,
      id: data.id ?? data.user_number ?? data.user_id,
      user_uuid: data.user_id,
    });
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

export function ProtectedRoute({ children, requireRole, allowRoles }) {
  const { isAuthenticated, user } = useAuth();
  const role = user?.role;

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requireRole && role !== requireRole) {
    return <Navigate to="/courses" replace />;
  }

  if (Array.isArray(allowRoles) && !allowRoles.includes(role)) {
    return <Navigate to="/courses" replace />;
  }

  return children;
}
