export const ROLES = {
  SYSADMIN: 'SysAdmin',
  CLIENT_ADMIN: 'ClientAdmin',
  SCHEDULE_MANAGER: 'ScheduleManager',
  EMPLOYEE: 'Employee',
};

export const ROLE_HIERARCHY = {
  [ROLES.SYSADMIN]: 4,
  [ROLES.CLIENT_ADMIN]: 3,
  [ROLES.SCHEDULE_MANAGER]: 2,
  [ROLES.EMPLOYEE]: 1,
};

export const hasRoleAccess = (userRole, requiredRole) => {
  const userLevel = ROLE_HIERARCHY[userRole] || 0;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] || 0;
  return userLevel >= requiredLevel;
};

export const getAllRoles = () => Object.values(ROLES);





























