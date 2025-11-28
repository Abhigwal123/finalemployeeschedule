/**
 * Backend Health Check Utility
 * Tests backend connectivity before login attempts
 */

import api from '../services/api';

export const checkBackendHealth = async () => {
  try {
    // Try to reach the health endpoint
    const response = await api.get('/health');
    return {
      reachable: true,
      status: response.data?.status || 'ok',
      message: 'Backend is reachable',
    };
  } catch (error) {
    console.error('Backend health check failed:', error);
    
    // Determine error type
    if (error.code === 'ECONNREFUSED' || error.message?.includes('Network Error')) {
      return {
        reachable: false,
        status: 'error',
        message: '無法連接到伺服器，請確認後端服務是否正在運行',
        error: 'Connection refused',
      };
    }
    
    if (error.response) {
      // Backend responded but with error
      return {
        reachable: true,
        status: 'error',
        message: `Backend responded with error: ${error.response.status}`,
        error: error.response.statusText,
      };
    }
    
    return {
      reachable: false,
      status: 'error',
      message: '無法連接到伺服器，請確認後端服務是否正在運行',
      error: error.message,
    };
  }
};

export const testBackendConnection = async () => {
  // Use environment variable - MUST be set
  const baseURL = import.meta.env.VITE_API_BASE_URL;
  console.log('Testing backend connection at:', baseURL);
  
  try {
    // Direct fetch to avoid axios interceptors
    // Add CORS mode to handle cross-origin requests
    const response = await fetch(`${baseURL}/health`, {
      method: 'GET',
      mode: 'cors', // Explicitly set CORS mode
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    if (response.ok) {
      const data = await response.json();
      return {
        success: true,
        reachable: true,
        data,
        message: 'Backend is reachable',
      };
    } else {
      return {
        success: false,
        reachable: true, // Backend is reachable but returned error
        status: response.status,
        message: `Backend returned ${response.status}`,
      };
    }
  } catch (error) {
    console.error('Backend connection test failed:', error);
    return {
      success: false,
      reachable: false,
      error: error.message,
      message: '無法連接到伺服器，請確認後端服務是否正在運行',
    };
  }
};

