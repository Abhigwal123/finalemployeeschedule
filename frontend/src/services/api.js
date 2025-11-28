import axios from "axios";

// Use environment variable - MUST be set in .env or build args
// For Docker with nginx proxy: VITE_API_BASE_URL=/api/v1
// For direct backend: VITE_API_BASE_URL=http://82.165.209.92:8081/api/v1
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Configure axios defaults
axios.defaults.withCredentials = true;
axios.defaults.baseURL = API_BASE_URL;

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
  withCredentials: true,
});

// Add detailed logging for API base URL
console.log('[TRACE] API base URL configured:', axios.defaults.baseURL);

// Set Content-Type header (simple header, doesn't trigger preflight)
api.defaults.headers.common["Content-Type"] = "application/json";

// Request interceptor - add auth token (needed for authenticated endpoints)
// CRITICAL: Only set Authorization header - do NOT set Origin, Accept, or any CORS headers
// Browser automatically sets Origin, Accept, and CORS headers - client must NOT set them
api.interceptors.request.use(
  (config) => {
    // Get token from localStorage - support multiple key formats
    const token = localStorage.getItem('jwt') || 
                  localStorage.getItem('token') || 
                  localStorage.getItem('access_token');
    
    if (token) {
      // Only set Authorization header - this is a simple header that doesn't trigger preflight
      config.headers.Authorization = `Bearer ${token}`;
      console.log(`[API] Added Authorization header for request to ${config.url}`);
    } else {
      // CRITICAL: Don't set "Bearer undefined" - this causes 401 on OPTIONS
      // If no token, don't set Authorization header at all
      console.warn(`[API] No token found in localStorage for request to ${config.url} - skipping Authorization header`);
      // Remove Authorization header if it exists (shouldn't, but be safe)
      delete config.headers.Authorization;
    }
    
    // CRITICAL: Do NOT set these headers (browser controls them):
    // - Origin (browser sets automatically)
    // - Accept (browser sets automatically, but we can set simple Accept)
    // - Access-Control-* (server sets these, NOT client)
    // - Content-Type (already set as default, only for non-simple requests)
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle 401 errors
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Handle 401 Unauthorized
    if (error.response?.status === 401) {
      const url = error.config?.url || '';
      const isAuthMe = url.includes('/auth/me');
      const isAuthLogin = url.includes('/auth/login');
      const isAuthLogout = url.includes('/auth/logout');
      const isLoginPage = window.location.pathname === '/login' || window.location.pathname === '/';
      
      // Don't clear tokens for auth endpoints or when on login page
      if (!isAuthMe && !isAuthLogin && !isAuthLogout && !isLoginPage) {
        // For protected routes - clear tokens and redirect
        localStorage.removeItem('token');
        localStorage.removeItem('access_token');
        localStorage.removeItem('auth');
        
        if (!isLoginPage) {
          setTimeout(() => {
            window.location.href = '/login';
          }, 100);
        }
      }
    }
    
    return Promise.reject(error);
  }
);

export const fetchMySchedule = async (month, token, options = {}) => {
  const { page, pageSize, signal } = options;
  const params = {};
  if (month) {
    params.month = month;
  }
  if (page) {
    params.page = page;
  }
  if (pageSize) {
    params.page_size = pageSize;
  }

  const config = { params };

  if (signal) {
    config.signal = signal;
  }

  if (token) {
    config.headers = {
      ...(config.headers || {}),
      Authorization: `Bearer ${token}`,
    };
  }

  const response = await api.get('/schedule/my', config);
  return response.data;
};

// Employee ID utilities - simplified
export const getAvailableEmployeeIDs = async () => {
  const res = await api.get("/employee/available-ids");
  return res.data;
};

export default api;
