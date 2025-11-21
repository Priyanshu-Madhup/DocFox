import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check for stored auth data on app load
    const storedSessionId = localStorage.getItem('sessionId');
    const storedUser = localStorage.getItem('user');

    if (storedSessionId && storedUser) {
      try {
        setSessionId(storedSessionId);
        setUser(JSON.parse(storedUser));
      } catch (error) {
        console.error('Error parsing stored user data:', error);
        localStorage.removeItem('sessionId');
        localStorage.removeItem('user');
      }
    }
    setLoading(false);
  }, []);

  const login = (userData, sessionIdValue) => {
    setUser(userData);
    setSessionId(sessionIdValue);
    localStorage.setItem('sessionId', sessionIdValue);
    localStorage.setItem('user', JSON.stringify(userData));
  };

  const logout = async () => {
    if (sessionId) {
      try {
        // Call logout endpoint to invalidate session
        await fetch('http://localhost:8000/api/auth/logout', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ session_id: sessionId }),
        });
      } catch (error) {
        console.error('Error during logout:', error);
      }
    }
    
    setUser(null);
    setSessionId(null);
    localStorage.removeItem('sessionId');
    localStorage.removeItem('user');
  };

  const isAuthenticated = () => {
    return !!(user && sessionId);
  };

  // API helper function
  const apiCall = async (url, options = {}) => {
    if (!sessionId) {
      throw new Error('No session available');
    }

    const defaultOptions = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    };

    // Add session_id as query parameter for GET requests or in body for POST/PUT
    let finalUrl = `http://localhost:8000/api${url}`;
    let finalOptions = { ...options, headers: defaultOptions.headers };

    if (options.method === 'GET' || !options.method) {
      // Add session_id as query parameter
      const separator = url.includes('?') ? '&' : '?';
      finalUrl += `${separator}session_id=${sessionId}`;
    } else {
      // Add session_id to request body
      const body = options.body ? JSON.parse(options.body) : {};
      body.session_id = sessionId;
      finalOptions.body = JSON.stringify(body);
    }

    const response = await fetch(finalUrl, finalOptions);

    if (response.status === 401) {
      // Session expired or invalid
      logout();
      throw new Error('Authentication required');
    }

    return response;
  };

  const value = {
    user,
    sessionId,
    loading,
    login,
    logout,
    isAuthenticated,
    apiCall,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
