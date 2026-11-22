import { useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../hooks/useAuth';

export default function LoginPage() {
  const { login, register, isLoading, error } = useAuth();
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    console.log('[LOGIN] Form submitted'); // DEBUG

    // Validate phone number (10 digits)
    if (!phoneNumber || phoneNumber.length !== 10 || !/^\d{10}$/.test(phoneNumber)) {
      setFormError('Phone number must be 10 digits');
      console.warn('[LOGIN] Invalid phone number format'); // DEBUG
      return;
    }
    
    const firstDigit = parseInt(phoneNumber[0]);
    if (firstDigit < 6 || firstDigit > 9) {
      setFormError('Phone number must start with 6, 7, 8, or 9');
      console.warn('[LOGIN] Invalid phone number - must start with 6-9'); // DEBUG
      return;
    }

    if (!password || password.length < 6) {
      setFormError('Password is required');
      console.warn('[LOGIN] Password required'); // DEBUG
      return;
    }

    console.log('[LOGIN] Validation passed, calling login...'); // DEBUG

    try {
      await login(phoneNumber, password);
      console.log('[LOGIN] Login completed successfully'); // DEBUG
      // Redirect handled by useAuth
    } catch (err: any) {
      console.error('[LOGIN] Login failed:', err); // DEBUG
      // Extract error message properly from various error formats
      let errorMessage = 'Login failed';
      if (err.message) {
        errorMessage = err.message;
      } else if (err.response?.data?.detail) {
        // Handle Pydantic validation errors - detail might be an array
        const detail = err.response.data.detail;
        if (Array.isArray(detail) && detail.length > 0) {
          errorMessage = detail[0].msg || detail[0].detail || JSON.stringify(detail[0]);
        } else if (typeof detail === 'string') {
          errorMessage = detail;
        } else {
          errorMessage = JSON.stringify(detail);
        }
      } else if (err.response?.data) {
        errorMessage = JSON.stringify(err.response.data);
      }
      console.error('[LOGIN] Error message:', errorMessage); // DEBUG
      setFormError(errorMessage);
    }
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    // Validate phone number (10 digits starting with 6-9)
    if (!phoneNumber || phoneNumber.length !== 10 || !/^\d{10}$/.test(phoneNumber)) {
      setFormError('Phone number must be 10 digits');
      return;
    }
    
    const firstDigit = parseInt(phoneNumber[0]);
    if (firstDigit < 6 || firstDigit > 9) {
      setFormError('Phone number must start with 6, 7, 8, or 9');
      return;
    }

    // Validate password strength (minimum 12 characters with uppercase, lowercase, digit, and special char)
    if (!password || password.length < 12) {
      setFormError('Password must be at least 12 characters');
      return;
    }
    
    if (!/[A-Z]/.test(password)) {
      setFormError('Password must contain at least one uppercase letter');
      return;
    }
    
    if (!/[a-z]/.test(password)) {
      setFormError('Password must contain at least one lowercase letter');
      return;
    }
    
    if (!/\d/.test(password)) {
      setFormError('Password must contain at least one digit');
      return;
    }
    
    if (!/[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;/]/.test(password)) {
      setFormError('Password must contain at least one special character (!@#$%^&*(),.?":{}|<>_-+=[]\\;/)');
      return;
    }

    if (!name || name.trim().length === 0) {
      setFormError('Name is required');
      return;
    }

    try {
      setSuccessMessage('Registration successful! Logging you in...');
      await register(phoneNumber, password, name.trim());
      // Redirect handled by useAuth - success message will show briefly before redirect
    } catch (err: any) {
      setSuccessMessage(null); // Clear success message on error
      // Extract error message properly from various error formats
      let errorMessage = 'Registration failed';
      
      // Check for 409 Conflict (phone number already registered)
      if (err.response?.status === 409) {
        const detail = err.response.data?.detail;
        if (detail) {
          errorMessage = typeof detail === 'string' ? detail : String(detail);
          // Add helpful suggestion to try logging in if not already mentioned
          if (!errorMessage.toLowerCase().includes('login')) {
            errorMessage += ' Please try logging in instead.';
          }
        } else {
          errorMessage = 'Phone number already registered. Please try logging in instead.';
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
      setFormError(errorMessage);
    }
  };

  const displayError = formError || error;
  const displaySuccess = successMessage;

  return (
    <div className="min-h-screen flex flex-col lg:flex-row animate-fadeIn">
      {/* Hero Section - Left Side */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-primary-500 via-primary-600 to-primary-700 p-12 flex-col justify-center relative overflow-hidden">
        {/* Decorative background elements */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-primary-400 rounded-full opacity-20 -mr-48 -mt-48"></div>
        <div className="absolute bottom-0 left-0 w-72 h-72 bg-primary-800 rounded-full opacity-20 -ml-36 -mb-36"></div>
        
        <div className="relative z-10 text-white">
          <div className="mb-8">
            <svg className="w-16 h-16 mb-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <h1 className="text-5xl font-bold mb-4">DocChat</h1>
            <p className="text-2xl text-primary-100 mb-8">
              Transform Your Documents into Conversational AI
            </p>
          </div>
          
          <div className="space-y-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-white bg-opacity-20 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-lg mb-1">Upload Documents</h3>
                <p className="text-primary-100">Upload PDF documents and let AI process them for you</p>
              </div>
            </div>
            
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-white bg-opacity-20 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-lg mb-1">Create AI Agents</h3>
                <p className="text-primary-100">Build intelligent agents powered by GPT-4 and your documents</p>
              </div>
            </div>
            
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-white bg-opacity-20 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-lg mb-1">Chat Naturally</h3>
                <p className="text-primary-100">Ask questions and get accurate answers from your documents</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Form Section - Right Side */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-12 bg-gray-50">
        <div className="w-full max-w-md">
          {/* Mobile Logo */}
          <div className="lg:hidden text-center mb-8">
            <div className="inline-flex items-center justify-center mb-4">
              <svg className="w-12 h-12 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <h1 className="text-3xl font-bold text-gray-900">DocChat</h1>
            <p className="text-gray-600 mt-2">Transform your documents into AI</p>
          </div>

          <div className="bg-white rounded-2xl shadow-xl p-8 animate-slideUp">
            {/* Tab Switcher */}
            <div className="flex gap-2 mb-6 p-1 bg-gray-100 rounded-lg">
              <button
                type="button"
                onClick={() => {
                  setIsRegisterMode(false);
                  setFormError(null);
                  setSuccessMessage(null);
                  setPhoneNumber('');
                  setPassword('');
                  setName('');
                }}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-all duration-200 ${
                  !isRegisterMode
                    ? 'bg-white text-primary-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsRegisterMode(true);
                  setFormError(null);
                  setSuccessMessage(null);
                  setPhoneNumber('');
                  setPassword('');
                  setName('');
                }}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-all duration-200 ${
                  isRegisterMode
                    ? 'bg-white text-primary-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                Register
              </button>
            </div>

            {/* Header */}
            <div className="text-center mb-6">
              <h2 className="text-2xl font-bold text-gray-900">
                {isRegisterMode ? 'Create Account' : 'Welcome Back'}
              </h2>
              <p className="text-sm text-gray-600 mt-1">
                {isRegisterMode
                  ? 'Sign up to get started with DocChat'
                  : 'Sign in to continue to your account'}
              </p>
            </div>

            {/* Alerts */}
            {displaySuccess && (
              <div className="mb-4 bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg flex items-start gap-3 animate-slideUp">
                <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-sm">{displaySuccess}</span>
              </div>
            )}
            
            {displayError && (
              <div className="mb-4 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg flex items-start gap-3 animate-slideUp">
                <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-sm">{displayError}</span>
              </div>
            )}

            {/* Form */}
            <form
              onSubmit={isRegisterMode ? handleRegister : handleLogin}
              className="space-y-5"
            >
              {isRegisterMode && (
                <div>
                  <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                    Full Name
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <svg className="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    </div>
                    <input
                      id="name"
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                      placeholder="Enter your full name"
                      required
                    />
                  </div>
                </div>
              )}

              <div>
                <label htmlFor="phone" className="block text-sm font-medium text-gray-700 mb-2">
                  Phone Number
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <svg className="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                    </svg>
                  </div>
                  <input
                    id="phone"
                    type="tel"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value.replace(/\D/g, '').slice(0, 10))}
                    className="block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                    placeholder="10-digit phone number"
                    maxLength={10}
                    required
                  />
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  {isRegisterMode 
                    ? '10 digits starting with 6, 7, 8, or 9' 
                    : 'Enter your 10-digit phone number'}
                </p>
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                  Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <svg className="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                  </div>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="block w-full pl-10 pr-3 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                    placeholder={isRegisterMode ? "Minimum 12 characters" : "Enter your password"}
                    required
                  />
                </div>
                {isRegisterMode ? (
                  <p className="mt-1 text-xs text-gray-500">
                    Min 12 chars with uppercase, lowercase, digit, and special character
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-gray-500">Enter your password</p>
                )}
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 px-4 bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-white font-semibold rounded-lg shadow-md hover:shadow-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <span>{isRegisterMode ? 'Create Account' : 'Sign In'}</span>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Footer */}
          <p className="text-center text-sm text-gray-600 mt-6">
            {isRegisterMode ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button
              type="button"
              onClick={() => {
                setIsRegisterMode(!isRegisterMode);
                setFormError(null);
                setSuccessMessage(null);
                setPhoneNumber('');
                setPassword('');
                setName('');
              }}
              className="text-primary-600 hover:text-primary-700 font-semibold"
            >
              {isRegisterMode ? 'Sign in' : 'Register now'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
