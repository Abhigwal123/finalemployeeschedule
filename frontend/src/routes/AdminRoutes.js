import { Routes, Route } from 'react-router-dom';
import AdminLayout from '../layouts/AdminLayout';
import ProtectedRoute from './ProtectedRoute';
import {
  Dashboard,
  Department,
  UserAccountManagement,
  PermissionMaintenance,
  PermissionMatrix,
} from '../pages/ClientAdmin';

export default function AdminRoutes() {
  return (
    <ProtectedRoute requiredRole="ClientAdmin">
      <Routes>
        <Route path="/*" element={<AdminLayout />}>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="department" element={<Department />} />
          <Route path="users" element={<UserAccountManagement />} />
          <Route path="permissions" element={<PermissionMatrix />} />
          <Route index element={<Dashboard />} />
        </Route>
      </Routes>
    </ProtectedRoute>
  );
}

