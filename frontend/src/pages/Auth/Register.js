import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import { ROUTES } from '../../utils/constants';

export default function Register() {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    email: '',
    role: 'Department_Employee',
    full_name: '',
    tenant_name: '',
  });

  // Get available roles based on current user's role
  // Hierarchy: Admin (ClientAdmin) > SysAdmin > ScheduleManager > Department_Employee
  const getAvailableRoles = () => {
    if (!isAuthenticated || !user) {
      // Public registration - only Employee
      return [{ value: 'Department_Employee', label: '部門員工' }];
    }

    const userRole = user.role;
    
    switch (userRole) {
      case 'ClientAdmin':
      case 'Client_Admin':
        // Admin (ClientAdmin) can register: ClientAdmin, SysAdmin, ScheduleManager, Department_Employee
        return [
          { value: 'ClientAdmin', label: 'Admin' },
          { value: 'SysAdmin', label: '系統管理員' },
          { value: 'ScheduleManager', label: '排班主管' },
          { value: 'Department_Employee', label: '部門員工' },
        ];
      case 'SysAdmin':
      case 'admin':
        // SysAdmin can register: ScheduleManager, Department_Employee
        return [
          { value: 'ScheduleManager', label: '排班主管' },
          { value: 'Department_Employee', label: '部門員工' },
        ];
      case 'ScheduleManager':
      case 'Schedule_Manager':
        // ScheduleManager can register: Department_Employee
        return [
          { value: 'Department_Employee', label: '部門員工' },
        ];
      case 'Employee':
      case 'Department_Employee':
      case 'employee':
        return []; // Employee cannot register anyone
      default:
        return [{ value: 'Department_Employee', label: '部門員工' }];
    }
  };

  const availableRoles = getAvailableRoles();
  const canRegister = availableRoles.length > 0 || !isAuthenticated;

  // Redirect if Employee tries to access
  useEffect(() => {
    if (isAuthenticated && user) {
      const userRole = user.role;
      if (userRole === 'Employee' || userRole === 'Department_Employee' || userRole === 'employee') {
        navigate(ROUTES.EMPLOYEE_MY);
      }
    }
  }, [isAuthenticated, user, navigate]);

  // Set default role
  useEffect(() => {
    if (availableRoles.length > 0 && !formData.role) {
      setFormData(prev => ({ ...prev, role: availableRoles[0].value }));
    }
  }, [availableRoles]);

  // Clear username and error when role changes
  useEffect(() => {
    setFormData(prev => ({ ...prev, username: '' }));
    setError('');
  }, [formData.role]);


  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // Validate username is provided
      if (!formData.username) {
        setError('請輸入用戶名（Username）');
        setLoading(false);
        return;
      }
      
      // For Department_Employee role only, validate username format (should be employee_id format like E01, N01, etc.)
      if (formData.role === 'Department_Employee' || formData.role === 'employee') {
        const usernamePattern = /^[A-Z]\d{2}$/i; // Matches patterns like E01, N01, etc.
        if (!usernamePattern.test(formData.username.trim())) {
          setError('請輸入有效的員工編號格式（例如：E01, N01）');
          setLoading(false);
          return;
        }
      }

      // Prepare request data
      // For Department_Employee role: username IS the employee_id (user enters employee_id as username)
      // For other roles: username is regular username
      // Normalize role value for backend (backend expects 'Department_Employee' or 'employee')
      let roleValue = formData.role;
      if (roleValue === 'employee') {
        roleValue = 'Department_Employee'; // Normalize to backend expected value
      }
      
      const requestData = {
        username: formData.username,
        password: formData.password,
        email: formData.email || undefined,
        role: roleValue,
        full_name: formData.full_name || undefined,
      };
      

      // If SysAdmin and tenant_name provided, include tenant creation
      if (user?.role === 'SysAdmin' && formData.tenant_name) {
        requestData.tenant = {
          tenantName: formData.tenant_name,
          is_active: true,
        };
        requestData.user = {
          username: formData.username,
          password: formData.password,
          email: formData.email || undefined,
          role: formData.role,
          full_name: formData.full_name || undefined,
        };
        delete requestData.username;
        delete requestData.password;
        delete requestData.email;
        delete requestData.role;
        delete requestData.full_name;
      }

      // Make API call
      const response = await api.post('/auth/register', requestData);

      if (response.data.success) {
        setSuccess(true);
        setTimeout(() => {
          // Redirect to appropriate dashboard
          if (isAuthenticated && user) {
            const role = user.role;
            if (role === 'SysAdmin') {
              navigate(ROUTES.SYSADMIN_DASHBOARD);
            } else if (role === 'ClientAdmin' || role === 'Client_Admin') {
              navigate(ROUTES.CLIENTADMIN_DASHBOARD);
            } else if (role === 'ScheduleManager' || role === 'Schedule_Manager') {
              navigate(ROUTES.SCHEDULEMANAGER_SCHEDULING);
            } else {
              navigate(ROUTES.EMPLOYEE_MY);
            }
          } else {
            navigate(ROUTES.LOGIN);
          }
        }, 2000);
      } else {
        setError(response.data.error || '註冊失敗');
      }
    } catch (err) {
      console.error('Registration error:', err);
      // Enhanced error handling for Employee ID validation
      let errorMessage = err.response?.data?.error || 
                        err.response?.data?.details || 
                        err.message || 
                        '註冊失敗，請稍後再試';
      
      // Handle specific Employee ID errors
      if (err.response?.status === 404) {
        if (errorMessage.includes('Employee ID') || errorMessage.includes('employee_id') || errorMessage.includes('Invalid Employee ID')) {
          errorMessage = '員工編號不存在。請確保 Google Sheet 已同步，或輸入正確的員工編號。';
        }
      } else if (err.response?.status === 409) {
        if (errorMessage.includes('Employee ID') || errorMessage.includes('employee_id') || errorMessage.includes('already registered')) {
          errorMessage = '此員工編號已被註冊。請輸入其他員工編號。';
        } else if (errorMessage.includes('Username already exists')) {
          errorMessage = '此用戶名已被使用。請輸入其他用戶名。';
        }
      } else if (err.response?.status === 400) {
        if (errorMessage.includes('Employee ID') || errorMessage.includes('employee_id')) {
          errorMessage = '請輸入有效的員工編號。';
        }
      } else if (err.response?.status === 403) {
        if (errorMessage.includes('Employee ID') || errorMessage.includes('inactive')) {
          errorMessage = '此員工編號已被停用。請聯繫管理員。';
        }
      }
      
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // Show access denied for Employee role
  if (isAuthenticated && user && (user.role === 'Employee' || user.role === 'Department_Employee' || user.role === 'employee')) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow-md p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4 text-center">無權限</h2>
          <p className="text-gray-600 text-center mb-4">
            員工角色無法註冊其他用戶。
          </p>
          <button
            onClick={() => navigate(ROUTES.EMPLOYEE_MY)}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 transition"
          >
            返回儀表板
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            註冊新用戶
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            {isAuthenticated && user ? (
              <>當前用戶：{user.username} ({user.role})</>
            ) : (
              <>公開註冊（僅限員工角色）</>
            )}
          </p>
        </div>

        {success ? (
          <div className="bg-green-50 border border-green-200 rounded-md p-4">
            <div className="flex items-center">
              <svg className="h-5 w-5 text-green-400 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <p className="text-green-800 font-medium">註冊成功 ✅</p>
            </div>
            <p className="text-green-700 text-sm mt-2">正在重定向...</p>
          </div>
        ) : (
          <form className="mt-8 space-y-6 bg-white p-6 rounded-lg shadow-md" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-md p-4">
                <p className="text-red-800 text-sm">{typeof error === 'string' ? error : (error?.message || error?.error || '發生錯誤')}</p>
              </div>
            )}

            <div className="space-y-4">
              {/* Username/Employee ID field - dynamically changes based on role */}
              {(formData.role === 'Department_Employee' || formData.role === 'employee') ? (
                // Employee role: Username = Employee ID (must match EmployeeMapping)
                <div>
                  <label htmlFor="username" className="block text-sm font-medium text-gray-700">
                    員工編號 (Employee ID) <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    required
                    value={formData.username}
                    onChange={handleChange}
                    className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                    placeholder="請輸入員工編號（例如：E01, N01）"
                  />
                </div>
              ) : (
                // Other roles: Regular username field
                <div>
                  <label htmlFor="username" className="block text-sm font-medium text-gray-700">
                    用戶名 (Username) <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="username"
                    name="username"
                    type="text"
                    required
                    value={formData.username}
                    onChange={handleChange}
                    className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                    placeholder="請輸入用戶名"
                  />
                </div>
              )}

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                  密碼 <span className="text-red-500">*</span>
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  required
                  value={formData.password}
                  onChange={handleChange}
                  className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                  placeholder="請輸入密碼"
                />
              </div>

              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                  電子郵箱
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  value={formData.email}
                  onChange={handleChange}
                  className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                  placeholder="請輸入電子郵箱（選填）"
                />
              </div>

              <div>
                <label htmlFor="full_name" className="block text-sm font-medium text-gray-700">
                  全名
                </label>
                <input
                  id="full_name"
                  name="full_name"
                  type="text"
                  value={formData.full_name}
                  onChange={handleChange}
                  className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                  placeholder="請輸入全名（選填）"
                />
              </div>

              <div>
                <label htmlFor="role" className="block text-sm font-medium text-gray-700">
                  角色 <span className="text-red-500">*</span>
                </label>
                <select
                  id="role"
                  name="role"
                  required
                  value={formData.role}
                  onChange={handleChange}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                  disabled={availableRoles.length === 0}
                >
                  {availableRoles.map(role => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
                {availableRoles.length === 0 && (
                  <p className="mt-1 text-sm text-gray-500">無可用角色</p>
                )}
              </div>


              {/* Show tenant_name field only for SysAdmin */}
              {isAuthenticated && user && (user.role === 'SysAdmin' || user.role === 'admin') && (
                <div>
                  <label htmlFor="tenant_name" className="block text-sm font-medium text-gray-700">
                    租戶名稱（選填）
                  </label>
                  <input
                    id="tenant_name"
                    name="tenant_name"
                    type="text"
                    value={formData.tenant_name}
                    onChange={handleChange}
                    className="mt-1 appearance-none relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
                    placeholder="請輸入租戶名稱（選填，留空則使用現有租戶）"
                  />
                  <p className="mt-1 text-xs text-gray-500">
                    留空則將新用戶添加到當前租戶
                  </p>
                </div>
              )}
            </div>

            <div>
              <button
                type="submit"
                disabled={loading || !canRegister}
                className="group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {loading ? '註冊中...' : '提交註冊'}
              </button>
            </div>

            <div className="text-center">
              <button
                type="button"
                onClick={() => {
                  if (isAuthenticated && user) {
                    const role = user.role;
                    if (role === 'SysAdmin') {
                      navigate(ROUTES.SYSADMIN_DASHBOARD);
                    } else if (role === 'ClientAdmin' || role === 'Client_Admin') {
                      navigate(ROUTES.CLIENTADMIN_DASHBOARD);
                    } else if (role === 'ScheduleManager' || role === 'Schedule_Manager') {
                      navigate(ROUTES.SCHEDULEMANAGER_SCHEDULING);
                    } else {
                      navigate(ROUTES.EMPLOYEE_MY);
                    }
                  } else {
                    navigate(ROUTES.LOGIN);
                  }
                }}
                className="text-sm text-blue-600 hover:text-blue-500"
              >
                返回
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}



