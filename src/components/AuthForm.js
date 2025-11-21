import React, { useState } from 'react';
import './AuthForm.css';

export default function AuthForm({ onLogin }) {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    email: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
    setError(''); // Clear error when user types
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const endpoint = isLogin ? '/api/auth/login' : '/api/auth/register';
      const payload = isLogin 
        ? { username: formData.username, password: formData.password }
        : { username: formData.username, email: formData.email, password: formData.password };

      const response = await fetch(`http://localhost:8000${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (response.ok) {
        if (isLogin) {
          // Store session ID and user info
          onLogin(data.user, data.session_id);
        } else {
          // Registration successful, switch to login
          setIsLogin(true);
          setFormData({ username: '', password: '', email: '' });
          setError('Registration successful! Please login.');
        }
      } else {
        // Handle different error types based on the endpoint
        if (isLogin) {
          setError(data.detail || 'Invalid username or password');
        } else {
          // For signup, show more specific error messages
          if (data.detail && data.detail.includes('already exists')) {
            setError('Username or email already exists. Please choose different ones.');
          } else {
            setError(data.detail || 'Registration failed. Please try again.');
          }
        }
      }
    } catch (err) {
      console.error('Network error:', err);
      if (isLogin) {
        setError('Network error. Please check if the server is running.');
      } else {
        setError('Network error during registration. Please check if the server is running.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="AuthForm">
      <div className="AuthForm__container">
        <div className="AuthForm__header">
          <h1 className="AuthForm__logo">DocFox</h1>
          <p className="AuthForm__subtitle">Your AI-powered document assistant</p>
        </div>

        <form onSubmit={handleSubmit} className="AuthForm__form">
          <div className="AuthForm__tabs">
            <button
              type="button"
              className={`AuthForm__tab ${isLogin ? 'active' : ''}`}
              onClick={() => {
                setIsLogin(true);
                setError('');
                setFormData({ username: '', password: '', email: '' });
              }}
            >
              Login
            </button>
            <button
              type="button"
              className={`AuthForm__tab ${!isLogin ? 'active' : ''}`}
              onClick={() => {
                setIsLogin(false);
                setError('');
                setFormData({ username: '', password: '', email: '' });
              }}
            >
              Sign Up
            </button>
          </div>

          {error && (
            <div className={`AuthForm__message ${error.includes('successful') ? 'success' : 'error'}`}>
              {error}
            </div>
          )}

          <div className="AuthForm__fields">
            <div className="AuthForm__field">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                name="username"
                type="text"
                value={formData.username}
                onChange={handleChange}
                required
                placeholder="Enter your username"
              />
            </div>

            {!isLogin && (
              <div className="AuthForm__field">
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleChange}
                  required
                  placeholder="Enter your email"
                />
              </div>
            )}

            <div className="AuthForm__field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                value={formData.password}
                onChange={handleChange}
                required
                placeholder="Enter your password"
              />
            </div>
          </div>

          <button
            type="submit"
            className="AuthForm__submit"
            disabled={loading}
          >
            {loading ? (
              <div className="AuthForm__spinner">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" fill="none" strokeDasharray="31.416" strokeDashoffset="31.416">
                    <animate attributeName="stroke-dasharray" dur="2s" values="0 31.416;15.708 15.708;0 31.416" repeatCount="indefinite"/>
                    <animate attributeName="stroke-dashoffset" dur="2s" values="0;-15.708;-31.416" repeatCount="indefinite"/>
                  </circle>
                </svg>
              </div>
            ) : (
              isLogin ? 'Login' : 'Sign Up'
            )}
          </button>
        </form>

        <div className="AuthForm__footer">
          <p>
            {isLogin ? "Don't have an account? " : "Already have an account? "}
            <button
              type="button"
              className="AuthForm__link"
              onClick={() => {
                setIsLogin(!isLogin);
                setError('');
                setFormData({ username: '', password: '', email: '' });
              }}
            >
              {isLogin ? 'Sign up' : 'Login'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
