import api from './api';

export const sysadminService = {
  getOverview: async () => {
    const response = await api.get('/sysadmin/dashboard');
    return response.data;
  },

  getStats: async () => {
    const response = await api.get('/sysadmin/dashboard');
    return response.data.stats || response.data;
  },

  getLogs: async (page = 1, perPage = 10) => {
    const response = await api.get('/sysadmin/logs', {
      params: { page, per_page: perPage },
    });
    return response.data;
  },
};








































