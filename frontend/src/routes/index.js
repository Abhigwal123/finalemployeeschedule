import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Login from '../pages/Auth/Login';
import Logout from '../pages/Auth/Logout';
import Register from '../pages/Auth/Register';
import Profile from '../pages/Profile/Profile';
import SysAdminRoutes from './SysAdminRoutes';
import AdminRoutes from './AdminRoutes';
import ScheduleManagerRoutes from './ScheduleManagerRoutes';
import EmployeeRoutes from './EmployeeRoutes';
import ProtectedRoute from './ProtectedRoute';
import { ROUTES } from '../utils/constants';

export default function AppRoutes() {
  const { isAuthenticated, user } = useAuth();

  // Helper function to get default route based on role
  const getDefaultRoute = (role) => {
    const roleLower = role?.toLowerCase() || '';
    switch (roleLower) {
      case 'sysadmin':
        return ROUTES.SYSADMIN_DASHBOARD;
      case 'clientadmin':
      case 'client_admin':
        return ROUTES.CLIENTADMIN_DASHBOARD;
      case 'schedulemanager':
      case 'schedule_manager':
        return ROUTES.SCHEDULEMANAGER_SCHEDULING;
      case 'employee':
      case 'department_employee':
        return ROUTES.EMPLOYEE_MY;
      default:
        return ROUTES.LOGIN;
    }
  };

  return (
    <Routes>
      {/* Root path - redirect based on auth state */}
      <Route
        path="/"
        element={
          isAuthenticated && user ? (
            <Navigate to={getDefaultRoute(user.role)} replace />
          ) : (
            <Navigate to={ROUTES.LOGIN} replace />
          )
        }
      />
      
      {/* Login route - always accessible when not authenticated */}
      <Route
        path="/login"
        element={
          isAuthenticated && user ? (
            <Navigate to={getDefaultRoute(user.role)} replace />
          ) : (
            <Login />
          )
        }
      />
      
      {/* Logout route */}
      <Route path="/logout" element={<Logout />} />
      
      {/* Register route - accessible when authenticated (role-based) or public */}
      <Route
        path="/register"
        element={<Register />}
      />

      {/* Protected routes - only show when authenticated */}
      {isAuthenticated && user ? (
        <>
          {/* Profile route - accessible to all authenticated users */}
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <Profile />
              </ProtectedRoute>
            }
          />
          
          <Route path="/sysadmin/*" element={<SysAdminRoutes />} />
          <Route path="/admin/*" element={<AdminRoutes />} />
          {/* Legacy support for old client-admin URLs */}
          <Route path="/client-admin/*" element={<Navigate to={ROUTES.CLIENTADMIN_DASHBOARD} replace />} />
          <Route path="/schedule-manager/*" element={<ScheduleManagerRoutes />} />
          <Route path="/employee/*" element={<EmployeeRoutes />} />
          
          {/* Catch-all for authenticated users */}
          <Route
            path="*"
            element={<Navigate to={getDefaultRoute(user.role)} replace />}
          />
        </>
      ) : (
        <>
          {/* Catch-all for unauthenticated users - always redirect to login */}
          <Route path="*" element={<Navigate to={ROUTES.LOGIN} replace />} />
        </>
      )}
    </Routes>
  );
}
