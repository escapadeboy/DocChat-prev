import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth } from '../services/api';
import type { User } from '../types/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
  register: (phone: string, password: string, name: string) => Promise<void>;
  login: (phone: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadUser = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const token = localStorage.getItem('access_token');
      if (!token) {
        setIsLoading(false);
        return;
      }
      const userData = await auth.getMe();
      setUser(userData);
    } catch (err: any) {
      // Only set error if we're not on login page
      if (window.location.pathname !== '/login') {
        setError(err.response?.data?.detail || 'Failed to load user');
      }
      setToken(null);
      setUser(null);
      localStorage.removeItem('access_token');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Auto-load user on mount if token exists
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    if (storedToken) {
      setToken(storedToken);
      loadUser();
    } else {
      setIsLoading(false);
    }
  }, [loadUser]);

  // Set token in API headers when token changes
  useEffect(() => {
    if (token) {
      localStorage.setItem('access_token', token);
    } else {
      localStorage.removeItem('access_token');
    }
  }, [token]);

  const register = async (phone: string, password: string, name: string) => {
    try {
      setIsLoading(true);
      setError(null);
      // Clear any existing auth data before registration
      localStorage.removeItem('access_token');
      setToken(null);
      setUser(null);
      
      await auth.register(phone, password, name);
      
      // After registration, automatically login
      const loginResponse = await auth.login(phone, password);
      // Save token directly to localStorage first to ensure it's available
      localStorage.setItem('access_token', loginResponse.access_token);
      setToken(loginResponse.access_token);
      setUser(loginResponse.user);
      setError(null); // Clear any errors
      setIsLoading(false);
      // Redirect after ensuring token is saved - no need to call loadUser since we have user data
      navigate('/dashboard');
    } catch (err: any) {
      // Extract error message properly from various error formats
      let errorMessage = 'Registration failed';
      
      // Check for 409 Conflict (phone number already registered)
      if (err.response?.status === 409) {
        const detail = err.response.data?.detail;
        if (detail) {
          errorMessage = typeof detail === 'string' ? detail : String(detail);
        } else {
          errorMessage = 'Phone number already registered';
        }
      } else if (err.message && typeof err.message === 'string') {
        errorMessage = err.message;
      } else if (err.response?.data?.detail) {
        // Handle Pydantic validation errors - detail might be an array
        const detail = err.response.data.detail;
        if (Array.isArray(detail) && detail.length > 0) {
          errorMessage = detail[0].msg || detail[0].detail || String(detail[0]);
        } else if (typeof detail === 'string') {
          errorMessage = detail;
        } else {
          errorMessage = String(detail);
        }
      } else if (err.response?.data) {
        errorMessage = String(err.response.data);
      }
      setError(errorMessage);
      setIsLoading(false);
      throw new Error(errorMessage);
    }
  };

  const login = async (phone: string, password: string) => {
    // Use try-finally to ALWAYS reset loading state
    try {
      setIsLoading(true);
      setError(null);
      console.log('[AUTH] Login attempt started for phone:', phone.slice(-4)); // DEBUG
      
      // Clear any existing auth data before login
      localStorage.removeItem('access_token');
      setToken(null);
      setUser(null);
      
      const response = await auth.login(phone, password);
      console.log('[AUTH] Login API call successful'); // DEBUG
      
      // Save token directly to localStorage first to ensure it's available
      localStorage.setItem('access_token', response.access_token);
      setToken(response.access_token);
      setUser(response.user);
      setError(null); // Clear any errors
      
      console.log('[AUTH] Redirecting to dashboard...'); // DEBUG
      // Redirect after ensuring token is saved - no need to call loadUser since we have user data
      navigate('/dashboard');
    } catch (err: any) {
      // Extract error message properly from various error formats
      let errorMessage = 'Login failed';
      
      console.error('[AUTH] Login error:', err); // DEBUG
      console.error('[AUTH] Error response:', err.response); // DEBUG
      
      // Check for rate limit (429)
      if (err.response?.status === 429) {
        errorMessage = 'Too many login attempts. Please wait a minute and try again.';
        console.warn('[AUTH] Rate limit exceeded'); // DEBUG
      }
      // Check for 401 Unauthorized (wrong credentials)
      else if (err.response?.status === 401) {
        const detail = err.response.data?.detail;
        if (detail) {
          errorMessage = typeof detail === 'string' ? detail : String(detail);
        } else {
          errorMessage = 'Incorrect phone number or password';
        }
        console.error('[AUTH] Authentication failed - wrong credentials'); // DEBUG
      }
      // Check for timeout
      else if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMessage = 'Login request timed out. Please check your connection and try again.';
        console.error('[AUTH] Request timeout'); // DEBUG
      }
      // Check for network error
      else if (err.code === 'ERR_NETWORK' || !err.response) {
        errorMessage = 'Cannot connect to server. Please check if the backend is running.';
        console.error('[AUTH] Network error - backend may be down'); // DEBUG
      }
      else if (err.message && typeof err.message === 'string') {
        errorMessage = err.message;
      } else if (err.response?.data?.detail) {
        // Handle Pydantic validation errors - detail might be an array
        const detail = err.response.data.detail;
        if (Array.isArray(detail) && detail.length > 0) {
          errorMessage = detail[0].msg || detail[0].detail || String(detail[0]);
        } else if (typeof detail === 'string') {
          errorMessage = detail;
        } else {
          errorMessage = String(detail);
        }
      } else if (err.response?.data) {
        errorMessage = String(err.response.data);
      } else if (err.response) {
        errorMessage = `Login failed with status code ${err.response.status}`;
      }
      
      console.error('[AUTH] Final error message:', errorMessage); // DEBUG
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      // CRITICAL: Always reset loading state, even if there's an error
      // This ensures the button never gets stuck on "Processing..."
      setIsLoading(false);
      console.log('[AUTH] Loading state reset to false'); // DEBUG
    }
  };

  const logout = () => {
    auth.logout();
    setToken(null);
    setUser(null);
    setError(null);
    window.location.href = '/login';
  };

  const value: AuthContextType = {
    user,
    token,
    isLoading,
    error,
    register,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

