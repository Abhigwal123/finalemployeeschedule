import api from './api';

export const scheduleService = {
  getDefinitions: async (page = 1, perPage = 20, filters = {}) => {
    try {
      const response = await api.get('/schedule-definitions/', {  // Add trailing slash
        params: { page, per_page: perPage, ...filters },
      });
      console.log('[TRACE] Frontend: getDefinitions response:', response.data);
      // Backend returns: { page, per_page, total, items: [...] }
      return response.data;
    } catch (error) {
      console.error('[TRACE] Frontend: getDefinitions error:', error);
      console.error('[TRACE] Frontend: Error response:', error.response?.data);
      throw error;
    }
  },

  getDefinitionById: async (id) => {
    const response = await api.get(`/schedule-definitions/${id}`);
    return response.data;
  },

  createDefinition: async (data) => {
    const response = await api.post('/schedule-definitions', data);
    return response.data;
  },

  updateDefinition: async (id, data) => {
    const response = await api.put(`/schedule-definitions/${id}`, data);
    return response.data;
  },

  deleteDefinition: async (id) => {
    const response = await api.delete(`/schedule-definitions/${id}`);
    return response.data;
  },

  getPermissions: async (page = 1, perPage = 20, filters = {}) => {
    const response = await api.get('/schedule-permissions/', {  // Add trailing slash
      params: { page, per_page: perPage, ...filters },
    });
    return response.data;
  },

  updatePermission: async (id, data) => {
    const response = await api.put(`/schedule-permissions/${id}`, data);
    return response.data;
  },

  createPermission: async (data) => {
    const response = await api.post('/schedule-permissions', data);
    return response.data;
  },

  getJobLogs: async (page = 1, perPage = 50, filters = {}) => {
    console.log('[TRACE] Frontend: GET /schedule-job-logs/', { page, per_page: perPage, ...filters });
    
    const response = await api.get('/schedule-job-logs/', {  // Add trailing slash
      params: { page, per_page: perPage, ...filters },
    });
    
    console.log('[TRACE] Frontend: Response status:', response.status);
    console.log('[TRACE] Frontend: Response data keys:', Object.keys(response.data || {}));
    console.log('[DEBUG] Fetch Params → page=', page, 'per_page=', perPage, 'filters=', filters);
    
    // API returns { success: true, data: [...], pagination: {...} }
    const logs = response.data.data || response.data.logs || [];
    console.log('[DEBUG] Checking Schedule Logs → count:', logs.length);
    
    return {
      data: logs,
      pagination: response.data.pagination || {},
    };
  },

  runJob: async (data) => {
    console.log('[TRACE] Frontend: POST /schedule-job-logs/run', data);
    const response = await api.post('/schedule-job-logs/run', data);
    console.log('[TRACE] Frontend: Run job response:', response.status, response.data);
    return response.data;
  },

  getJobLogById: async (id) => {
    const response = await api.get(`/schedule-job-logs/${id}`);
    return response.data;
  },

  cancelJob: async (id, reason) => {
    const response = await api.post(`/schedule-job-logs/${id}/cancel`, { reason });
    return response.data;
  },

  // New methods for scheduling dashboard
  getD1Data: async (scheduleDefId = null) => {
    const params = scheduleDefId ? { schedule_def_id: scheduleDefId } : {};
    const response = await api.get('/schedulemanager/d1-scheduling', { params });
    return response.data;
  },

  getJobStatus: async (scheduleDefId) => {
    // Get latest job log for a schedule to check status
    const response = await api.get('/schedule-job-logs', {
      params: { schedule_def_id: scheduleDefId, per_page: 1 },
    });
    return response.data;
  },

  exportJobLog: async (logId) => {
    console.log('[TRACE] Frontend: Export job log:', logId);
    const response = await api.get(`/schedule-job-logs/${logId}/export`, {
      responseType: 'blob', // Important for file download
    });
    return response.data;
  },
};
