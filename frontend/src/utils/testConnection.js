/**
 * Direct connection test - bypasses all interceptors
 * Helps diagnose connection issues
 */

export const testDirectConnection = async () => {
  // Use environment variable - MUST be set
  const baseURL = import.meta.env.VITE_API_BASE_URL;
  const healthURL = `${baseURL}/health`;
  
  console.log('🔍 Testing direct connection to:', healthURL);
  console.log('🔍 Frontend origin:', window.location.origin);
  
  try {
    // Use fetch with no-cors mode first to test basic connectivity
    // Then try CORS mode
    let response;
    let fetchError = null;
    
    try {
      // Try CORS mode first
      response = await fetch(healthURL, {
        method: 'GET',
        mode: 'cors',
        credentials: 'omit',
        headers: {
          'Accept': 'application/json',
        },
        // Add timeout
        signal: AbortSignal.timeout(5000), // 5 second timeout
      });

      console.log('📡 Response status:', response.status);
      console.log('📡 Response ok:', response.ok);
      
      // Check response headers
      const corsHeader = response.headers.get('Access-Control-Allow-Origin');
      console.log('📡 CORS header:', corsHeader);
      
      if (response.ok) {
        const data = await response.json();
        console.log('✅ Backend connection successful!', data);
        return {
          success: true,
          reachable: true,
          data,
          message: 'Backend is reachable',
        };
      } else {
        // If we got a response (even error), backend is reachable
        const text = await response.text();
        console.warn('⚠️ Backend returned error status:', response.status, text);
        return {
          success: true, // Backend IS reachable, just returned error
          reachable: true,
          status: response.status,
          message: 'Backend is reachable',
        };
      }
    } catch (fetchErr) {
      fetchError = fetchErr;
      console.warn('CORS mode failed, trying no-cors mode...', fetchErr.message);
      
      // If CORS fails, try no-cors to see if backend responds at all
      try {
        response = await fetch(healthURL, {
          method: 'GET',
          mode: 'no-cors', // This won't throw CORS errors
          credentials: 'omit',
        });
        
        // In no-cors mode, we can't read response, but if it doesn't throw, connection works
        console.log('📡 No-CORS request completed (backend reachable, CORS issue)');
        return {
          success: true,
          reachable: true,
          message: 'Backend is reachable (CORS may need configuration)',
          corsIssue: true,
        };
      } catch (noCorsErr) {
        console.error('No-CORS also failed:', noCorsErr);
        throw fetchErr; // Throw original error
      }
    }
  } catch (error) {
    console.error('❌ Connection test failed:', error);
    console.error('Error name:', error.name);
    console.error('Error message:', error.message);
    
    // Check for timeout
    if (error.name === 'AbortError' || error.message?.includes('timeout')) {
      return {
        success: false,
        reachable: false,
        error: 'Connection timeout',
        message: '無法連接到伺服器，請確認後端服務是否正在運行 (連線逾時)',
      };
    }
    
    // Check for CORS errors
    if (error.name === 'TypeError' && (error.message.includes('Failed to fetch') || error.message.includes('network'))) {
      // This could be CORS or actually unreachable
      return {
        success: false,
        reachable: false,
        error: 'CORS or network error',
        message: '無法連接到伺服器，請確認後端服務是否正在運行',
        details: '檢查後端是否正在運行，並確認 CORS 設定允許來自 localhost:5173 的請求',
      };
    }
    
    return {
      success: false,
      reachable: false,
      error: error.message || 'Unknown error',
      message: '無法連接到伺服器，請確認後端服務是否正在運行',
    };
  }
};

