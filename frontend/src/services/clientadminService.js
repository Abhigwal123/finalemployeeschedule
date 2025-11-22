import api from './api';

export const clientadminService = {
  getOverview: async () => {
    const response = await api.get('/clientadmin/dashboard');
    return response.data;
  },
};





























