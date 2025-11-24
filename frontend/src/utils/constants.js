export const ROUTES = {
  // Auth routes
  LOGIN: '/login',
  LOGOUT: '/logout',
  REGISTER: '/register',
  
  // SysAdmin routes
  SYSADMIN_DASHBOARD: '/sysadmin/dashboard',
  SYSADMIN_ORG: '/sysadmin/org',
  SYSADMIN_SCHEDULE: '/sysadmin/schedule',
  
  // ClientAdmin routes
  CLIENTADMIN_DASHBOARD: '/client-admin/dashboard',
  CLIENTADMIN_DEPARTMENT: '/client-admin/department',
  CLIENTADMIN_USERS: '/client-admin/users',
  CLIENTADMIN_PERMISSIONS: '/client-admin/permissions',
  
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

