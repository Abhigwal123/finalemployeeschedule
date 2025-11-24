import api from './api';

export const scheduleManagerService = {
  getSchedules: async () => {
    const response = await api.get('/schedule');
    return response.data;
  },

  generateSchedule: async (data) => {
    const response = await api.post('/schedule/generate', data);
    return response.data;
  },

  getJobLogs: async (page = 1, perPage = 50) => {
    const response = await api.get('/schedule-job-logs', {
      params: { page, per_page: perPage },
    });
    return response.data;
  },
};


































