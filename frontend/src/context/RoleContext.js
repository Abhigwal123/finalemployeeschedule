import React, { createContext, useContext, useState } from 'react';
import { useAuth } from './AuthContext';
import { ROLES } from '../utils/roles';

const RoleContext = createContext(null);

export const useRole = () => {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error('useRole must be used within a RoleProvider');
  }
  return context;
};

export const RoleProvider = ({ children }) => {
  const { user } = useAuth();
  const [currentRole, setCurrentRole] = useState(user?.role || null);

  // Update role when user changes
  React.useEffect(() => {
    if (user?.role) {
      setCurrentRole(user.role);
    } else {
      setCurrentRole(null);
    }
  }, [user]);

  const hasRole = (role) => {
    return currentRole === role;
  };

  const hasAnyRole = (roles) => {
    return roles.includes(currentRole);
  };

  const value = {
    currentRole,
    setCurrentRole,
    hasRole,
    hasAnyRole,
    ROLES,
  };

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
};











































