import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import Button from '../components/Button';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('student@example.com');
  const [password, setPassword] = useState('password');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password); // POST /api/auth/login
    } catch (err) {
      setError(err?.response?.data?.detail || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="max-w-md mx-auto bg-white shadow-sm border border-gray-200 rounded-lg p-6">
      <h1 className="text-2xl font-semibold text-gray-900 mb-2">Login</h1>
      <p className="text-sm text-gray-600 mb-4">// uses POST /api/auth/login</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
          <input
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
          <input
            type="password"
            className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? 'Signing in...' : 'Login'}
        </Button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </form>
    </section>
  );
}
