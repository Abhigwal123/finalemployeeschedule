import { useState, useEffect } from 'react';
import { userService } from '../../services/userService';
import { departmentService } from '../../services/departmentService';
import { roleService } from '../../services/roleService';
import { authService } from '../../services/authService';
import { useAuth } from '../../context/AuthContext';
import LoadingSpinner from '../../components/LoadingSpinner';
import Modal from '../../components/Modal';
import Button from '../../components/Button';

const getRoleBadge = (role, roleConfigs = []) => {
  // Find role config from API
  const roleConfig = roleConfigs.find(r => r.role === role || r.name === role);
  
  if (roleConfig && roleConfig.badge) {
    return (
      <span className={`px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${roleConfig.badge.bg} ${roleConfig.badge.text}`}>
        {roleConfig.label || roleConfig.name || role}
      </span>
    );
  }

  // Fallback for unknown roles
  return (
    <span className="px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">
      {role || '未知'}
    </span>
  );
};

const getStatusBadge = (isActive) => {
  if (isActive) {
    return (
      <span className="px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
        啟用
      </span>
    );
  }
  return (
    <span className="px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">
      停用
    </span>
  );
};

export default function UserAccountManagement() {
  const { tenant, user } = useAuth();
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [formData, setFormData] = useState({
    full_name: '',
    username: '',
    email: '',
    role: 'ScheduleManager',
    departmentID: '',
    is_active: true,
    password: '',
  });
  const [registerFormData, setRegisterFormData] = useState({
    full_name: '',
    username: '',
    email: '',
    password: '',
    role: 'ScheduleManager',
  });
  const [saving, setSaving] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [tenantName, setTenantName] = useState(tenant?.tenantName || '機構');

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (tenant?.tenantName) {
      setTenantName(tenant.tenantName);
    }
  }, [tenant]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError('');
      
      console.log('[TRACE] ClientAdmin User Management: Loading data...');
      
      // Load roles first
      const roleResponse = await roleService.getAll();
      const roleData = roleResponse?.data || roleResponse || [];
      setRoles(roleData);
      
      const [userResponse, deptResponse] = await Promise.all([
        userService.getAll(1, 100),
        departmentService.getAll(1, 100),
      ]);

      console.log('[TRACE] ClientAdmin User Management: Users response:', userResponse);
      console.log('[TRACE] ClientAdmin User Management: Departments response:', deptResponse);

      const allUsers = userResponse.data || [];
      const allDepts = deptResponse.data || [];
      
      console.log('[TRACE] ClientAdmin User Management: Data counts:', {
        users: allUsers.length,
        departments: allDepts.length,
        roles: roleData.length,
      });

      // Map users with department names
      const usersWithDepts = allUsers.map(user => {
        const dept = allDepts.find(d => d.departmentID === user.departmentID);
        return {
          ...user,
          departmentName: dept?.departmentName || '未指定',
        };
      });

      setUsers(usersWithDepts);
      setDepartments(allDepts);
    } catch (err) {
      setError(err.response?.data?.error || '載入使用者資料失敗');
      console.error('Error loading users:', err);
    } finally {
      setLoading(false);
    }
  };

  // Check if current user can register users
  const canRegisterUsers = () => {
    if (!user) return false;
    const userRole = user.role || '';
    const allowedRoles = ['ClientAdmin', 'Client_Admin', 'SysAdmin', 'ScheduleManager', 'Schedule_Manager'];
    return allowedRoles.includes(userRole);
  };

  // Get available roles for registration based on current user's role
  const getAvailableRegisterRoles = () => {
    if (!user) return [];
    const userRole = user.role || '';
    
    if (userRole === 'ClientAdmin' || userRole === 'Client_Admin') {
      return [
        { value: 'ClientAdmin', label: 'Admin' },
        { value: 'SysAdmin', label: '系統管理員' },
        { value: 'ScheduleManager', label: '排班主管' },
        { value: 'Department_Employee', label: '部門員工' },
      ];
    } else if (userRole === 'SysAdmin') {
      return [
        { value: 'ScheduleManager', label: '排班主管' },
        { value: 'Department_Employee', label: '部門員工' },
      ];
    } else if (userRole === 'ScheduleManager' || userRole === 'Schedule_Manager') {
      return [
        { value: 'Department_Employee', label: '部門員工' },
      ];
    }
    return [];
  };

  const handleCreate = () => {
    setEditingUser(null);
    setFormData({
      full_name: '',
      username: '',
      email: '',
      role: 'ScheduleManager',
      departmentID: departments.length > 0 ? departments[0].departmentID : '',
      is_active: true,
      password: '',
    });
    setIsModalOpen(true);
  };

  const handleRegister = () => {
    setRegisterFormData({
      full_name: '',
      username: '',
      email: '',
      password: '',
      role: getAvailableRegisterRoles()[0]?.value || 'ScheduleManager',
    });
    setIsRegisterModalOpen(true);
  };

  const handleRegisterSubmit = async () => {
    try {
      setRegistering(true);
      setError('');

      if (!registerFormData.username || !registerFormData.password) {
        setError('請填寫使用者名稱和密碼');
        setRegistering(false);
        return;
      }

      const registerData = {
        username: registerFormData.username,
        password: registerFormData.password,
        email: registerFormData.email || registerFormData.username,
        role: registerFormData.role,
        full_name: registerFormData.full_name,
      };

      const result = await authService.register(registerData);

      if (result.success) {
        setIsRegisterModalOpen(false);
        await loadData();
        setError('');
      } else {
        setError(result.error || '註冊失敗');
      }
    } catch (err) {
      setError(err.response?.data?.error || '註冊失敗');
      console.error('Error registering user:', err);
    } finally {
      setRegistering(false);
    }
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    // Convert status string to boolean for form
    const isActive = user.status === 'active' || (user.is_active !== undefined ? user.is_active : true);
    setFormData({
      full_name: user.full_name || '',
      username: user.username || '',
      email: user.email || user.username || '',
      role: user.role || 'ScheduleManager',
      departmentID: user.departmentID || '',
      is_active: isActive,
      password: '', // Don't prefill password
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError('');

      if (!formData.full_name || !formData.username) {
        setError('請填寫所有必要欄位');
        setSaving(false);
        return;
      }

      if (!editingUser && !formData.password) {
        setError('新使用者必須設定密碼');
        setSaving(false);
        return;
      }

      const saveData = {
        full_name: formData.full_name,
        username: formData.username,
        email: formData.email || formData.username,
        role: formData.role,
        status: formData.is_active ? 'active' : 'inactive', // Convert boolean to string
        departmentID: formData.departmentID || null,
      };

      if (!editingUser) {
        saveData.password = formData.password;
      } else if (formData.password) {
        saveData.password = formData.password;
      }

      if (editingUser) {
        await userService.update(editingUser.userID, saveData);
      } else {
        await userService.create(saveData);
      }

      setIsModalOpen(false);
      await loadData();
    } catch (err) {
      setError(err.response?.data?.error || '儲存使用者失敗');
      console.error('Error saving user:', err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  return (
    <div className="bg-gray-100 p-4 md:p-8">
      {/* C3.1: 頂部操作列 */}
      <div className="flex flex-col md:flex-row justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">使用者帳號管理</h1>
          <p className="mt-1 text-sm text-gray-600">管理貴機構 ({tenantName}) 內的所有使用者帳號。</p>
        </div>
        <div className="flex gap-2 mt-4 md:mt-0">
          <button
            onClick={handleCreate}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none"
          >
            <svg className="h-5 w-5 mr-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
            </svg>
            新增使用者
          </button>
          {canRegisterUsers() && (
            <button
              onClick={handleRegister}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none"
            >
              <svg className="h-5 w-5 mr-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path d="M8 9a3 3 0 100-6 3 3 0 000 6zM8 11a6 6 0 016 6H2a6 6 0 016-6zM16 7a1 1 0 10-2 0v1h-1a1 1 0 100 2h1v1a1 1 0 102 0v-1h1a1 1 0 100-2h-1V7z" />
              </svg>
              註冊使用者
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {typeof error === 'string' ? error : (error?.message || error?.error || String(error) || '發生錯誤')}
        </div>
      )}

      {/* C3.2: 使用者列表表格 */}
      <div className="bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="w-full overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  使用者名稱
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  登入帳號 (Email)
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  角色
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  所屬部門
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  狀態
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {users.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-6 py-4 text-center text-sm text-gray-500">
                    目前沒有使用者資料
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.userID}>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">
                        {user.full_name || user.username}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {user.email || user.username}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getRoleBadge(user.role, roles)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {user.departmentName}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getStatusBadge(user.is_active)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        onClick={() => handleEdit(user)}
                        className="text-indigo-600 hover:text-indigo-900"
                      >
                        編輯
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* C3.3: 新增/編輯使用者 Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingUser(null);
        }}
        title=""
        size="md"
      >
        <div className="sm:flex sm:items-start">
          <div className="mx-auto flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-indigo-100 sm:mx-0 sm:h-10 sm:w-10">
            <svg className="h-6 w-6 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
          <div className="mt-3 text-center sm:mt-0 sm:ml-4 sm:text-left w-full">
            <h3 className="text-lg leading-6 font-medium text-gray-900">
              {editingUser ? '編輯使用者' : '新增使用者'}
            </h3>
            <div className="mt-4 space-y-4">
              <div>
                <label htmlFor="user-name" className="block text-sm font-medium text-gray-700">
                  使用者名稱
                </label>
                <input
                  type="text"
                  name="user-name"
                  id="user-name"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder="請輸入姓名"
                  required
                />
              </div>
              <div>
                <label htmlFor="user-email" className="block text-sm font-medium text-gray-700">
                  登入帳號 (Email)
                </label>
                <input
                  type="email"
                  name="user-email"
                  id="user-email"
                  value={formData.email || formData.username}
                  onChange={(e) => {
                    const email = e.target.value;
                    setFormData({ ...formData, email, username: email });
                  }}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder="user@tenant.com"
                  required
                />
              </div>
              <div>
                <label htmlFor="user-role" className="block text-sm font-medium text-gray-700">
                  角色
                </label>
                <select
                  id="user-role"
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                >
                  {roles.length > 0 ? (
                    roles.map((role) => (
                      <option key={role.role || role.name} value={role.role || role.name}>
                        {role.label || role.name || role.role}
                      </option>
                    ))
                  ) : (
                    <>
                      <option value="ScheduleManager">排班主管</option>
                      <option value="Employee">部門員工</option>
                    </>
                  )}
                </select>
              </div>
              <div>
                <label htmlFor="user-dept" className="block text-sm font-medium text-gray-700">
                  所屬部門
                </label>
                <select
                  id="user-dept"
                  value={formData.departmentID}
                  onChange={(e) => setFormData({ ...formData, departmentID: e.target.value })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                >
                  <option value="">請選擇部門</option>
                  {departments.map((dept) => (
                    <option key={dept.departmentID} value={dept.departmentID}>
                      {dept.departmentName}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">狀態</label>
                <select
                  value={formData.is_active ? 'active' : 'inactive'}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.value === 'active' })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                >
                  <option value="active">啟用</option>
                  <option value="inactive">停用</option>
                </select>
              </div>
              <div>
                <label htmlFor="user-password" className="block text-sm font-medium text-gray-700">
                  密碼 {editingUser && <span className="text-gray-500 text-xs">(留空則不更新)</span>}
                </label>
                <input
                  type="password"
                  name="user-password"
                  id="user-password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder={editingUser ? "留空則不更新密碼" : "請輸入密碼"}
                  required={!editingUser}
                />
                {editingUser && (
                  <p className="mt-1 text-xs text-gray-500">
                    僅在需要更改密碼時填寫，留空則保持原密碼不變
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse mt-6">
          <Button
            onClick={handleSave}
            loading={saving}
            className="w-full sm:ml-3 sm:w-auto"
          >
            儲存
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setIsModalOpen(false);
              setEditingUser(null);
            }}
            className="mt-3 w-full sm:mt-0 sm:ml-3 sm:w-auto"
          >
            取消
          </Button>
        </div>
      </Modal>

      {/* Register User Modal */}
      <Modal
        isOpen={isRegisterModalOpen}
        onClose={() => {
          setIsRegisterModalOpen(false);
          setRegisterFormData({
            full_name: '',
            username: '',
            email: '',
            password: '',
            role: 'ScheduleManager',
          });
        }}
        title="註冊使用者"
        size="md"
      >
        <div className="space-y-4">
          <div>
            <label htmlFor="register-full-name" className="block text-sm font-medium text-gray-700">
              使用者名稱
            </label>
            <input
              type="text"
              id="register-full-name"
              value={registerFormData.full_name}
              onChange={(e) => setRegisterFormData({ ...registerFormData, full_name: e.target.value })}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              placeholder="請輸入姓名"
            />
          </div>
          <div>
            <label htmlFor="register-username" className="block text-sm font-medium text-gray-700">
              登入帳號 (Username) *
            </label>
            <input
              type="text"
              id="register-username"
              value={registerFormData.username}
              onChange={(e) => setRegisterFormData({ ...registerFormData, username: e.target.value })}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              placeholder="請輸入登入帳號"
              required
            />
          </div>
          <div>
            <label htmlFor="register-email" className="block text-sm font-medium text-gray-700">
              電子郵件 (Email)
            </label>
            <input
              type="email"
              id="register-email"
              value={registerFormData.email}
              onChange={(e) => setRegisterFormData({ ...registerFormData, email: e.target.value })}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              placeholder="user@example.com"
            />
          </div>
          <div>
            <label htmlFor="register-password" className="block text-sm font-medium text-gray-700">
              密碼 *
            </label>
            <input
              type="password"
              id="register-password"
              value={registerFormData.password}
              onChange={(e) => setRegisterFormData({ ...registerFormData, password: e.target.value })}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              placeholder="請輸入密碼"
              required
            />
          </div>
          <div>
            <label htmlFor="register-role" className="block text-sm font-medium text-gray-700">
              角色 *
            </label>
            <select
              id="register-role"
              value={registerFormData.role}
              onChange={(e) => setRegisterFormData({ ...registerFormData, role: e.target.value })}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            >
              {getAvailableRegisterRoles().map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <Button
            variant="secondary"
            onClick={() => {
              setIsRegisterModalOpen(false);
              setRegisterFormData({
                full_name: '',
                username: '',
                email: '',
                password: '',
                role: 'ScheduleManager',
              });
            }}
          >
            取消
          </Button>
          <Button
            onClick={handleRegisterSubmit}
            loading={registering}
          >
            註冊
          </Button>
        </div>
      </Modal>
    </div>
  );
}
