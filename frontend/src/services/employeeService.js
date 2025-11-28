
import api from './api';

export const employeeService = {
  getMySchedule: async (month = null) => {
    // CRITICAL: Check for token BEFORE making API call
    // This prevents OPTIONS requests with "Authorization: Bearer undefined"
    const token = localStorage.getItem('token') || 
                  localStorage.getItem('access_token') || 
                  localStorage.getItem('jwt');
    
    if (!token) {
      console.warn('[DEBUG] getMySchedule: No token found - returning error without API call');
      return {
        success: false,
        error: 'Not authenticated',
        schedule: []
      };
    }

    // CRITICAL: Always use params object - NEVER construct query string manually
    // Manual query strings (e.g., `/schedule/my?month=${month}`) trigger Chrome's strict-mode preflight
    // which can be cancelled before reaching the server, causing CORS errors
    const params = month ? { month } : {};
    console.log(`[TRACE] Frontend: Calling /schedule/my with month=${month}`);
    console.log(`[DEBUG] Token check: token exists=${!!token}, length=${token ? token.length : 0}`);
    try {
      const response = await api.get('/schedule/my', { params });
      console.log(`[DEBUG] Response from getMySchedule:`, {
        status: response.status,
        hasData: !!response.data,
        scheduleLength: response.data?.schedule?.length || 0,
        success: response.data?.success
      });
      return response.data;
    } catch (error) {
      console.error(`[ERROR] getMySchedule failed:`, error);
      throw error;
    }
  },

  getScheduleData: async (scheduleDefId = null) => {
    const params = scheduleDefId ? { schedule_def_id: scheduleDefId } : {};
    const response = await api.get('/employee/schedule-data', { params });
    return response.data;
  },

  // New endpoint for schedule data with trace logging
  // Uses cached endpoint /employee/schedule which is faster and more reliable
  getSchedule: async (month = null) => {
    // CRITICAL: Check for token BEFORE making API call
    // This prevents OPTIONS requests with "Authorization: Bearer undefined"
    const token = localStorage.getItem('token') || 
                  localStorage.getItem('access_token') || 
                  localStorage.getItem('jwt');
    
    if (!token) {
      console.warn('[DEBUG] getSchedule: No token found - returning error without API call');
      return {
        success: false,
        error: 'Not authenticated',
        schedule: []
      };
    }

    try {
      console.log(`[TRACE] Frontend: Fetching schedule for month=${month}`);
      // Use environment variable - MUST be set
      const apiBaseURL = import.meta.env.VITE_API_BASE_URL;
      console.log(`[TRACE] Frontend: API base URL: ${apiBaseURL}`);
      console.log(`[TRACE] Final API URL called: ${apiBaseURL}/schedule/my`);
      console.log(`[DEBUG] Token check: token exists=${!!token}, length=${token ? token.length : 0}`);
      
      // CRITICAL: Always use params object - NEVER construct query string manually
      // Manual query strings (e.g., `/schedule/my?month=${month}`) trigger Chrome's strict-mode preflight
      // which can be cancelled before reaching the server, causing CORS errors
      const params = month ? { month } : {};
      // Use /schedule/my endpoint which uses JWT authentication
      const fullURL = `${apiBaseURL}/schedule/my${params.month ? `?month=${params.month}` : ''}`;
      console.log(`[TRACE] Final API URL called: ${fullURL}`);
      const response = await api.get('/schedule/my', { params });
      
      console.log(`[TRACE] Received response status: ${response.status}`);
      console.log(`[DEBUG] ========== FRONTEND API RESPONSE ==========`);
      console.log(`[DEBUG] Response status:`, response.status);
      console.log(`[DEBUG] Response data type:`, typeof response.data, Array.isArray(response.data) ? 'Array' : 'Object');
      console.log(`[DEBUG] Response data:`, response.data);
      console.log(`[DEBUG] Response data keys:`, response.data && typeof response.data === 'object' && !Array.isArray(response.data) ? Object.keys(response.data) : 'N/A');
      
      // Handle 202 Accepted - Auto-sync triggered
      if (response.status === 202) {
        console.log(`[AUTO-SYNC] Received 202 Accepted - auto-sync triggered`);
        return {
          success: false,
          auto_sync_triggered: true,
          message: response.data?.message || 'Auto-sync triggered. Schedule will be available soon.',
          schedule: []
        };
      }
      
      // Log structure details
      if (response.data && typeof response.data === 'object' && !Array.isArray(response.data)) {
        console.log(`[DEBUG] Response structure:`);
        console.log(`[DEBUG]   - success:`, response.data.success);
        console.log(`[DEBUG]   - schedule:`, response.data.schedule, `(type: ${typeof response.data.schedule}, isArray: ${Array.isArray(response.data.schedule)}, length: ${Array.isArray(response.data.schedule) ? response.data.schedule.length : 'N/A'})`);
        console.log(`[DEBUG]   - month:`, response.data.month);
        console.log(`[DEBUG]   - error:`, response.data.error);
        if (response.data.schedule && Array.isArray(response.data.schedule)) {
          console.log(`[DEBUG]   - schedule entries: ${response.data.schedule.length}`);
          if (response.data.schedule.length > 0) {
            console.log(`[DEBUG]   - First entry:`, response.data.schedule[0]);
          }
        }
      } else if (Array.isArray(response.data)) {
        console.log(`[DEBUG] ⚠️ Response is array directly, length:`, response.data.length);
        if (response.data.length > 0) {
          console.log(`[DEBUG]   - First array item:`, response.data[0]);
        }
      }
      console.log(`[DEBUG] ===========================================`);
      
      const rawData = response.data;
      const normalizeSchedulePayload = (data) => {
        if (!data) {
          return { success: false, error: 'Empty response', schedule: [] };
        }

        if (Array.isArray(data)) {
          console.log(`[TRACE] Frontend: Response is array, converting to object format`);
          return {
            success: true,
            schedule: data,
            entries: data,
            month: month
          };
        }

        if (typeof data !== 'object') {
          console.warn(`[TRACE] Frontend: Unexpected response format, treating as empty`);
          return { success: true, schedule: [], entries: [], month: month };
        }

        const entries = Array.isArray(data.entries)
          ? data.entries
          : Array.isArray(data.schedule)
            ? data.schedule
            : Array.isArray(data.data?.schedule)
              ? data.data.schedule
              : [];

        if (!Array.isArray(data.entries) && Array.isArray(entries)) {
          data = { ...data, entries };
        }

        if (!Array.isArray(data.schedule) && Array.isArray(entries)) {
          data = { ...data, schedule: entries };
        }

        return data;
      };

      const normalized = normalizeSchedulePayload(rawData);
      console.log(`[TRACE] Frontend: Schedule loaded successfully, entries=${normalized.entries?.length || normalized.schedule?.length || 0}`);
      return normalized;
    } catch (error) {
      console.error('[DEBUG] ========== FRONTEND API ERROR ==========');
      console.error('[DEBUG] Error type:', error.name);
      console.error('[DEBUG] Error message:', error.message);
      console.error('[DEBUG] Response status:', error.response?.status);
      console.error('[DEBUG] Response data:', error.response?.data);
      console.error('[DEBUG] =========================================');
      
      // Handle 202 status in error response (axios might treat 202 as error in some configs)
      if (error.response?.status === 202) {
        console.log(`[AUTO-SYNC] Received 202 Accepted in error handler - auto-sync triggered`);
        return {
          success: false,
          auto_sync_triggered: true,
          message: error.response?.data?.message || 'Auto-sync triggered. Schedule will be available soon.',
          schedule: []
        };
      }
      
      // Return a structured error response instead of throwing
      return {
        success: false,
        error: error.response?.data?.error || error.message || 'Failed to fetch schedule',
        schedule: []
      };
    }
  },

  submitLeaveRequest: async (data) => {
    const response = await api.post('/employee/requests/leave', data);
    return response.data;
  },
};
