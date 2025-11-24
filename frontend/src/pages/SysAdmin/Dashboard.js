import { useState, useEffect } from 'react';
import api from '../../services/api';
import LoadingSpinner from '../../components/LoadingSpinner';

const formatTimeAgo = (timestamp) => {
  if (!timestamp) return '--';
  
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return '剛剛';
  if (diffMins < 60) return `${diffMins} 分鐘前`;
  if (diffHours < 24) return `${diffHours} 小時前`;
  return `${diffDays} 天前`;
};

const formatLogAction = (action, details) => {
  // Format log action message
  if (action === 'create_user') {
    return `新增了使用者 '${details?.username || details?.target || ''}'`;
  } else if (action === 'create_tenant') {
    return `新增了客戶機構 '${details?.name || details?.target || ''}'`;
  } else if (action === 'update_tenant') {
    return `更新了客戶機構 '${details?.name || details?.target || ''}'`;
  } else if (action === 'create_schedule') {
    return `新增了班表 '${details?.name || details?.target || ''}'`;
  }
  return details?.message || action || '執行了操作';
};

export default function Dashboard() {
  const [stats, setStats] = useState({
    totalClients: 0,
    totalSchedules: 0,
    systemStatus: '一切正常',
  });
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError('');

      console.log('[TRACE] Frontend: Loading SysAdmin dashboard data');

      // Fetch stats from sysadmin dashboard endpoint
      const statsResponse = await api.get('/sysadmin/dashboard');
      console.log('[TRACE] Frontend: Dashboard response:', statsResponse.data);
      
      const statsData = statsResponse.data.stats || statsResponse.data;
      console.log('[TRACE] Frontend: Stats data:', statsData);

      if (!statsResponse.data.success) {
        throw new Error(statsResponse.data.error || 'Failed to load dashboard');
      }

      // Set initial stats from dashboard response
      console.log('[DEBUG] 客戶機構總數 source: API /sysadmin/dashboard → backend Tenant.query.count() (DATABASE)');
      console.log('[DEBUG] 已設定班表總數 source: API /sysadmin/dashboard → backend ScheduleDefinition.query.count() (DATABASE)');
      
      setStats({
        totalClients: statsData.total_tenants || statsData.totalTenants || 0,
        totalSchedules: statsData.total_schedules || statsData.totalSchedules || 0,
        systemStatus: '檢查中...', // Will be updated from system-health endpoint
      });
      
      console.log('[TRACE] Frontend: Stats loaded from API:', {
        totalClients: statsData.total_tenants || statsData.totalTenants || 0,
        totalSchedules: statsData.total_schedules || statsData.totalSchedules || 0,
      });
      
      // Fetch system health dynamically
      try {
        console.log('[TRACE] Frontend: Fetching system health from /sysadmin/system-health');
        const healthResponse = await api.get('/sysadmin/system-health');
        console.log('[TRACE] Frontend: System health response:', healthResponse.data);
        console.log('[DEBUG] 系統健康狀態 source: API /sysadmin/system-health → computed dynamically (runtime checks)');
        
        const healthStatus = healthResponse.data.status === 'ok' ? '一切正常' : '系統異常';
        setStats(prev => ({ ...prev, systemStatus: healthStatus }));
        console.log(`[TRACE] Frontend: System health status updated to: ${healthStatus}`);
      } catch (err) {
        console.warn('[TRACE] Frontend: Failed to fetch system health:', err);
        console.warn('[TRACE] Frontend: Error details:', {
          message: err.message,
          response: err.response?.data,
          status: err.response?.status
        });
        // Fallback to "狀態未知" if health check fails
        setStats(prev => ({ ...prev, systemStatus: '狀態未知' }));
      }

      // Fetch logs
      try {
        console.log('[TRACE] Frontend: Fetching logs from /sysadmin/logs');
        console.log('[DEBUG] 系統日誌 source: API /sysadmin/logs → backend ScheduleJobLog.query (DATABASE)');
        const logsResponse = await api.get('/sysadmin/logs', {
          params: { limit: 10 },
        });
        console.log('[TRACE] Frontend: Logs response:', logsResponse.data);
        const logsData = logsResponse.data.logs || logsResponse.data.data || logsResponse.data || [];
        console.log(`[TRACE] Frontend: Loaded ${logsData.length} log entries from database`);
        // Ensure only last 10 logs are displayed
        setLogs(Array.isArray(logsData) ? logsData.slice(0, 10) : []);
      } catch (logErr) {
        console.warn('[TRACE] Frontend: Failed to load logs:', logErr);
        console.warn('[TRACE] Frontend: Log error details:', {
          message: logErr.message,
          response: logErr.response?.data,
          status: logErr.response?.status
        });
        // Use fallback logs
        setLogs([]);
      }
    } catch (err) {
      console.error('[TRACE] Frontend: Failed to load dashboard:', err);
      console.error('[TRACE] Frontend: Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status
      });
      setError(err.response?.data?.error || '載入儀表板資料失敗');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  return (
    <div className="bg-gray-100 p-4 md:p-8">
      {/* 頁面標題 */}
      <h1 className="text-3xl font-bold text-gray-900 mb-6">
        系統管理員儀表板
      </h1>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {typeof error === 'string' ? error : (error?.message || error?.error || String(error) || '發生錯誤')}
        </div>
      )}

      {/* B1.1: 統計卡片 (Stat Cards) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        {/* Card 1: 客戶總數 */}
        <div className="bg-white p-6 rounded-xl shadow-lg flex items-center space-x-4">
          <div className="flex-shrink-0 p-3 bg-indigo-100 rounded-full">
            <svg className="h-6 w-6 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">客戶機構總數</p>
            <p className="text-3xl font-bold text-gray-900">{stats.totalClients}</p>
          </div>
        </div>

        {/* Card 2: 班表總數 */}
        <div className="bg-white p-6 rounded-xl shadow-lg flex items-center space-x-4">
          <div className="flex-shrink-0 p-3 bg-green-100 rounded-full">
            <svg className="h-6 w-6 text-green-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">已設定班表總數</p>
            <p className="text-3xl font-bold text-gray-900">{stats.totalSchedules}</p>
          </div>
        </div>

        {/* Card 3: 系統狀態 */}
        <div className="bg-white p-6 rounded-xl shadow-lg flex items-center space-x-4">
          <div className="flex-shrink-0 p-3 bg-green-100 rounded-full">
            <svg className="h-6 w-6 text-green-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">系統健康狀態</p>
            <p className="text-xl font-bold text-green-700">{stats.systemStatus}</p>
          </div>
        </div>
      </div>

      {/* B1.2: 快捷操作或日誌 */}
      <div className="bg-white p-6 rounded-xl shadow-lg">
        <h2 className="text-xl font-semibold mb-4">系統日誌</h2>
        {logs.length === 0 ? (
          <p className="text-sm text-gray-500 py-4">無資料</p>
        ) : (
          <ul className="divide-y divide-gray-200">
            {logs.map((log, index) => {
              const userRole = log.user_role || log.role || '';
              const userEmail = log.user_email || log.email || log.username || '';
              const action = formatLogAction(log.action, log.details || log);
              const timestamp = log.timestamp || log.created_at || log.updated_at;

              return (
                <li key={log.id || log.logID || index} className="py-3 flex items-center space-x-3">
                  <svg className="h-5 w-5 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                  </svg>
                  <p className="text-sm text-gray-700 flex-1">
                    <span className="font-medium text-gray-900">
                      [{userRole || 'System'}] '{userEmail}'
                    </span>{' '}
                    {action}
                  </p>
                  <span className="text-xs text-gray-500">{formatTimeAgo(timestamp)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
