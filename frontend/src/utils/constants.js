export const ROUTES = {
  // Auth routes
  LOGIN: '/login',
  LOGOUT: '/logout',
  REGISTER: '/register',
  
  // SysAdmin routes
  SYSADMIN_DASHBOARD: '/sysadmin/dashboard',
  SYSADMIN_ORG: '/sysadmin/org',
  SYSADMIN_SCHEDULE: '/sysadmin/schedule',
  
  // Admin routes (formerly ClientAdmin)
  CLIENTADMIN_DASHBOARD: '/admin/dashboard',
  CLIENTADMIN_DEPARTMENT: '/admin/department',
  CLIENTADMIN_USERS: '/admin/users',
  CLIENTADMIN_PERMISSIONS: '/admin/permissions',
  
  // ScheduleManager routes
  SCHEDULEMANAGER_SCHEDULING: '/schedule-manager/scheduling',
  SCHEDULEMANAGER_EXPORT: '/schedule-manager/export',
  SCHEDULEMANAGER_LOGS: '/schedule-manager/logs',
  
  // Employee routes
  EMPLOYEE_MY: '/employee/my',
  
  // Profile route (accessible to all authenticated users)
  PROFILE: '/profile',
};

export const NAV_ITEMS = {
  [ROUTES.SYSADMIN_DASHBOARD]: { label: 'Dashboard', role: 'SysAdmin' },
  [ROUTES.SYSADMIN_ORG]: { label: 'Organization Maintenance', role: 'SysAdmin' },
  [ROUTES.SYSADMIN_SCHEDULE]: { label: 'Schedule List Maintenance', role: 'SysAdmin' },
  
  [ROUTES.CLIENTADMIN_DASHBOARD]: { label: 'Dashboard', role: 'ClientAdmin' },
  [ROUTES.CLIENTADMIN_DEPARTMENT]: { label: 'Department', role: 'ClientAdmin' },
  [ROUTES.CLIENTADMIN_USERS]: { label: 'User Account Management', role: 'ClientAdmin' },
  [ROUTES.CLIENTADMIN_PERMISSIONS]: { label: 'Permission Maintenance', role: 'ClientAdmin' },
  
  [ROUTES.SCHEDULEMANAGER_SCHEDULING]: { label: 'Scheduling', role: 'ScheduleManager' },
  [ROUTES.SCHEDULEMANAGER_EXPORT]: { label: 'Export', role: 'ScheduleManager' },
  
  [ROUTES.EMPLOYEE_MY]: { label: 'My Dashboard', role: 'Employee' },
};

