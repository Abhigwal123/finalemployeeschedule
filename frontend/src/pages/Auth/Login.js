import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState(null); // null = checking, true = reachable, false = unreachable
  const [connectionError, setConnectionError] = useState('');
  const { login, isAuthenticated, user } = useAuth();
  const navigate = useNavigate();

  // Check backend health on component mount
  useEffect(() => {
    let isMounted = true;
    
    const checkBackend = async () => {
      const apiBaseURL = import.meta.env.VITE_API_BASE_URL;
      console.log('[TRACE] Checking backend health at:', apiBaseURL);
      
      try {
        const response = await fetch(`${apiBaseURL}/health`, {
          method: 'GET',
          mode: 'cors',
          headers: {
            'Accept': 'application/json',
          },
        });
        
        if (response.ok || response.status < 500) {
          if (isMounted) {
            setBackendStatus(true);
            setError('');
            setConnectionError('');
            console.log('✅ Backend is reachable! Status:', response.status);
          }
          return;
        }
      } catch (error) {
        console.warn('Fetch health check failed:', error.name, error.message);
      }
      
      // Fallback: Try alternative check
      try {
        // Simple check - if we get any response (even 401/404), backend is reachable
        const testResponse = await fetch(`${apiBaseURL}/auth/me`, {
          method: 'GET',
          mode: 'cors',
        }).catch(() => null);
        
        if (isMounted) {
          if (testResponse !== null) {
            setBackendStatus(true);
            setConnectionError('');
            console.log('✅ Backend is reachable (via fallback)');
          } else {
            setBackendStatus(false);
            setConnectionError('無法連接到伺服器，請確認後端服務是否正在運行');
            console.log('❌ Backend appears unreachable');
          }
        }
      } catch (err) {
        console.error('All connection tests failed:', err);
        if (isMounted) {
          setBackendStatus(false);
          setConnectionError('無法連接到伺服器，請確認後端服務是否正在運行');
        }
      }
    };
    
    checkBackend();
    
    return () => {
      isMounted = false;
    };
  }, []);

  // Helper function to get default route based on role
  const getDefaultRoute = (role) => {
    const normalizedRole = role?.toLowerCase() || '';
    
    switch (normalizedRole) {
      case 'sysadmin':
        return '/sysadmin/dashboard';
      case 'clientadmin':
      case 'client_admin':
        return '/admin/dashboard';
      case 'schedulemanager':
      case 'schedule_manager':
        return '/schedule-manager/scheduling';
      case 'employee':
      case 'department_employee':
      case 'department employee':
        return '/employee/my';
      default:
        return '/login';
    }
  };

  // Redirect if already authenticated (but only after loading is complete)
  useEffect(() => {
    // Don't redirect during initial load or if login is in progress
    // Only redirect if we're actually authenticated AND have user data AND not loading
    if (isAuthenticated && user && !loading) {
      const defaultRoute = getDefaultRoute(user.role);
      console.log('User already authenticated, redirecting to:', defaultRoute);
      // Use replace to avoid adding to history
      navigate(defaultRoute, { replace: true });
    }
  }, [isAuthenticated, user, loading, navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setConnectionError('');
    setLoading(true);

    try {
      console.log('Login form submitted:', { username });
      const result = await login(username, password);
      
      console.log('Login result:', result);
      
      if (result.success) {
        const defaultRoute = getDefaultRoute(result.user?.role);
        console.log('Navigating to:', defaultRoute);
        navigate(defaultRoute);
      } else {
        console.warn('Login failed:', result.error);
        setError(result.error || '帳號或密碼錯誤，請重試');
      }
    } catch (err) {
      console.error('Login exception:', err);
      setError(err.message || '帳號或密碼錯誤，請重試');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-100 flex items-center justify-center min-h-screen p-4">
      <div className="w-full max-w-md p-8 space-y-8 bg-white shadow-xl rounded-2xl">
        {/* 標題 */}
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-900">
            登入您的系統
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            歡迎使用自動排班管理系統
          </p>
        </div>

        {/* 登入表單 */}
        <form id="login-form" className="mt-8 space-y-6" onSubmit={handleLogin}>
          <input type="hidden" name="remember" value="true" />
          
          {/* 帳號欄位 */}
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
              帳號
            </label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="appearance-none relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
              placeholder="帳號"
            />
          </div>

          {/* 密碼欄位 */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              密碼
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="appearance-none relative block w-full px-3 py-3 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 focus:z-10 sm:text-sm"
              placeholder="密碼"
            />
          </div>

          {/* 後端連接錯誤提示 */}
          {backendStatus === false && connectionError && (
            <div id="backend-status" className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <div className="flex items-center">
                <svg className="h-5 w-5 text-red-600 mr-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <span className="text-sm text-red-800 font-medium">無法連接到伺服器</span>
              </div>
              <p className="text-xs text-red-600 mt-1">請確認後端服務是否正在運行</p>
              <p className="text-xs text-gray-500 mt-1">提示: 檢查瀏覽器控制台 (F12) 以獲取詳細錯誤信息</p>
            </div>
          )}

          {/* 登入錯誤訊息提示 */}
          {error && backendStatus === true && (
            <div id="error-message" className="text-sm text-red-600 text-center">
              {typeof error === 'string' ? error : (error?.message || error?.error || String(error) || '發生錯誤')}
            </div>
          )}

          {/* 登入按鈕 */}
          <div>
            <button
              id="login-button"
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="absolute left-0 inset-y-0 flex items-center pl-3">
                {loading ? (
                  <svg
                    id="loading-spinner"
                    className="h-5 w-5 text-indigo-500 group-hover:text-indigo-400 animate-spin"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    ></path>
                  </svg>
                ) : (
                  <svg
                    id="lock-icon"
                    className="h-5 w-5 text-indigo-500 group-hover:text-indigo-400"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                )}
              </span>
              <span id="button-text">{loading ? '登入中...' : '登入'}</span>
            </button>
          </div>
        </form>
        
        {/* 後端連接狀態 */}
        {backendStatus === null && (
          <div className="mt-4 text-center text-xs text-gray-500">
            <span className="inline-block animate-spin mr-2">⏳</span>
            正在檢查後端連接...
          </div>
        )}
        {backendStatus === true && (
          <div className="mt-4 text-center text-xs text-green-600 font-medium">
            ✓ 後端服務連接正常
          </div>
        )}
      </div>
    </div>
  );
}