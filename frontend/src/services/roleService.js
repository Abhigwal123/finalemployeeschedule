import api from './api';

export const roleService = {
  getAll: async () => {
    try {
      const response = await api.get('/roles/');
      return response.data;
    } catch (error) {
      // If endpoint doesn't exist yet, return default roles
      console.warn('[roleService] Roles endpoint not available, using defaults');
      return {
        success: true,
        data: [
          {
            role: 'ScheduleManager',
            label: '排班主管',
            badge: { bg: 'bg-blue-100', text: 'text-blue-800' },
          },
          {
            role: 'Schedule_Manager',
            label: '排班主管',
            badge: { bg: 'bg-blue-100', text: 'text-blue-800' },
          },
          {
            role: 'Employee',
            label: '部門員工',
            badge: { bg: 'bg-gray-100', text: 'text-gray-800' },
          },
          {
            role: 'ClientAdmin',
            label: 'Admin',
            badge: { bg: 'bg-purple-100', text: 'text-purple-800' },
          },
          {
            role: 'Client_Admin',
            label: 'Admin',
            badge: { bg: 'bg-purple-100', text: 'text-purple-800' },
          },
        ],
      };
    }
  },

  getRoleConfig: async (role) => {
    const response = await roleService.getAll();
    const roles = response.data || response || [];
    const roleConfig = roles.find(r => r.role === role || r.name === role);
    
    if (roleConfig) {
      return roleConfig;
    }
    
    // Default fallback
    return {
      role: role || 'unknown',
      label: role || '未知',
      badge: { bg: 'bg-gray-100', text: 'text-gray-800' },
    };
  },
};


