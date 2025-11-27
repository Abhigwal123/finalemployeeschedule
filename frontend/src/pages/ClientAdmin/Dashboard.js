import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { departmentService } from '../../services/departmentService';
import { userService } from '../../services/userService';
import { scheduleService } from '../../services/scheduleService';
import { alertService } from '../../services/alertService';
import { ROUTES } from '../../utils/constants';
import { Link } from 'react-router-dom';
import LoadingSpinner from '../../components/LoadingSpinner';

export default function Dashboard() {
  const { user, tenant } = useAuth();
  const [stats, setStats] = useState({
    departments: 0,
    users: 0,
    activeSchedules: 0,
    pendingAlerts: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError('');
      
      console.log('[TRACE] ClientAdmin Dashboard: Loading data...');
      
      // Fetch all stats in parallel
      const [deptResponse, userResponse, scheduleResponse, alertsResponse] = await Promise.all([
        departmentService.getAll(1, 100),
        userService.getAll(1, 100),
        scheduleService.getDefinitions(1, 100, { active: 'true' }),
        alertService.getPending().catch(() => ({ data: [] })), // Gracefully handle missing endpoint
      ]);

      console.log('[TRACE] ClientAdmin Dashboard: Departments response:', deptResponse);
      console.log('[TRACE] ClientAdmin Dashboard: Users response:', userResponse);
      console.log('[TRACE] ClientAdmin Dashboard: Schedules response:', scheduleResponse);
      console.log('[TRACE] ClientAdmin Dashboard: Alerts response:', alertsResponse);

      const departments = deptResponse.data || [];
      const users = userResponse.data || [];
      const schedules = scheduleResponse.items || scheduleResponse.data || [];
      const pendingAlerts = Array.isArray(alertsResponse) ? alertsResponse : (alertsResponse?.data || []);

      console.log('[TRACE] ClientAdmin Dashboard: Data counts:', {
        departments: departments.length,
        users: users.length,
        schedules: schedules.length,
        pendingAlerts: pendingAlerts.length,
      });

      setStats({
        departments: departments.length,
        users: users.length,
        activeSchedules: schedules.filter(s => s.is_active !== false).length,
        pendingAlerts: pendingAlerts.length,
      });
      
      console.log('[TRACE] ClientAdmin Dashboard: Stats set successfully');
    } catch (err) {
      console.error('[TRACE] ClientAdmin Dashboard: Error loading data:', err);
      console.error('[TRACE] ClientAdmin Dashboard: Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
        url: err.config?.url,
      });
      setError(err.response?.data?.error || '載入儀表板資料失敗');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  const managerName = user?.full_name || user?.username || '管理員';
  const tenantName = tenant?.tenantName || '機構';

  return (
    <div className="bg-gray-100 p-4 md:p-8">
      {/* C1.1: 頂部標題 */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Admin 儀表板</h1>
        <p className="mt-1 text-lg text-gray-600">
          歡迎回來，{managerName} ({tenantName})
        </p>
      </div>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {typeof error === 'string' ? error : (error?.message || error?.error || String(error) || '發生錯誤')}
        </div>
      )}

      {/* C1.2: 統計卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* 卡片 1: 部門總數 */}
        <div className="bg-white rounded-xl shadow-lg p-6 border-t-4 border-blue-500">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-500 uppercase tracking-wider">部門總數</div>
              <div className="text-3xl font-bold text-gray-900 mt-2">{stats.departments}</div>
            </div>
            <div className="flex-shrink-0 bg-blue-100 text-blue-600 rounded-full h-12 w-12 flex items-center justify-center">
              <svg className="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
            </div>
          </div>
          <Link to={ROUTES.CLIENTADMIN_DEPARTMENT} className="mt-4 text-sm text-blue-600 hover:underline block">
            前往部門管理
          </Link>
        </div>

        {/* 卡片 2: 使用者總數 */}
        <div className="bg-white rounded-xl shadow-lg p-6 border-t-4 border-green-500">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-500 uppercase tracking-wider">使用者總數</div>
              <div className="text-3xl font-bold text-gray-900 mt-2">{stats.users}</div>
            </div>
            <div className="flex-shrink-0 bg-green-100 text-green-600 rounded-full h-12 w-12 flex items-center justify-center">
              <svg className="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 016-6h6a6 6 0 016 6v1h-3M15 21a2 2 0 002 2h2a2 2 0 002-2v-1a2 2 0 00-2-2h-2a2 2 0 00-2 2v1z" />
              </svg>
            </div>
          </div>
          <Link to={ROUTES.CLIENTADMIN_USERS} className="mt-4 text-sm text-green-600 hover:underline block">
            前往使用者管理
          </Link>
        </div>

        {/* 卡片 3: 已啟動班表 */}
        <div className="bg-white rounded-xl shadow-lg p-6 border-t-4 border-indigo-500">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-500 uppercase tracking-wider">已啟動班表</div>
              <div className="text-3xl font-bold text-gray-900 mt-2">{stats.activeSchedules}</div>
            </div>
            <div className="flex-shrink-0 bg-indigo-100 text-indigo-600 rounded-full h-12 w-12 flex items-center justify-center">
              <svg className="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
          </div>
          <a href="#" className="mt-4 text-sm text-indigo-600 hover:underline block">查看班表清單</a>
        </div>

        {/* 卡片 4: 待處理警示 */}
        <div className="bg-white rounded-xl shadow-lg p-6 border-t-4 border-red-500">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium text-gray-500 uppercase tracking-wider">待處理警示</div>
              <div className="text-3xl font-bold text-gray-900 mt-2">{stats.pendingAlerts}</div>
            </div>
            <div className="flex-shrink-0 bg-red-100 text-red-600 rounded-full h-12 w-12 flex items-center justify-center">
              <svg className="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
          </div>
          <a href="#" className="mt-4 text-sm text-red-600 hover:underline block">查看警示</a>
        </div>
      </div>

      {/* C1.3: 快速存取連結 */}
      <div className="mt-8 bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="p-5 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-800">快速存取</h2>
        </div>
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Link
            to={ROUTES.CLIENTADMIN_DEPARTMENT}
            className="block p-4 bg-gray-50 rounded-lg hover:bg-gray-100 hover:shadow-md transition-all"
          >
            <div className="font-medium text-indigo-700">管理部門</div>
            <p className="text-sm text-gray-600 mt-1">新增或編輯機構內的部門單位。</p>
          </Link>
          <Link
            to={ROUTES.CLIENTADMIN_USERS}
            className="block p-4 bg-gray-50 rounded-lg hover:bg-gray-100 hover:shadow-md transition-all"
          >
            <div className="font-medium text-indigo-700">管理使用者</div>
            <p className="text-sm text-gray-600 mt-1">建立排班主管或員工的帳號。</p>
          </Link>
          <Link
            to={ROUTES.CLIENTADMIN_PERMISSIONS}
            className="block p-4 bg-gray-50 rounded-lg hover:bg-gray-100 hover:shadow-md transition-all"
          >
            <div className="font-medium text-indigo-700">設定排班權限</div>
            <p className="text-sm text-gray-600 mt-1">分配主管可管理的班表範圍。</p>
          </Link>
          <a
            href="#"
            className="block p-4 bg-gray-50 rounded-lg hover:bg-gray-100 hover:shadow-md transition-all"
          >
            <div className="font-medium text-indigo-700">查看排班日誌</div>
            <p className="text-sm text-gray-600 mt-1">檢視所有排班作業的執行紀錄。</p>
          </a>
        </div>
      </div>
    </div>
  );
}
