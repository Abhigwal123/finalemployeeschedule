import { useState, useEffect } from 'react';
import { scheduleService } from '../../services/scheduleService';
import { departmentService } from '../../services/departmentService';
import LoadingSpinner from '../../components/LoadingSpinner';
import Modal from '../../components/Modal';
import Button from '../../components/Button';

const getStatusBadge = (status) => {
  const statusMap = {
    'completed': { label: '成功', bg: 'bg-green-100', text: 'text-green-800' },
    'running': { label: '執行中...', bg: 'bg-yellow-100', text: 'text-yellow-800' },
    'pending': { label: '等待中', bg: 'bg-gray-100', text: 'text-gray-800' },
    'failed': { label: '失敗', bg: 'bg-red-100', text: 'text-red-800' },
    'cancelled': { label: '已取消', bg: 'bg-orange-100', text: 'text-orange-800' },
  };

  const statusConfig = statusMap[status] || { label: status || '未知', bg: 'bg-gray-100', text: 'text-gray-800' };

  return (
    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${statusConfig.bg} ${statusConfig.text}`}>
      {statusConfig.label}
    </span>
  );
};

const formatDateTime = (dateString) => {
  if (!dateString) return '--';
  const date = new Date(dateString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}/${month}/${day} ${hours}:${minutes}:${seconds}`;
};

const formatLogId = (logId) => {
  if (!logId) return '--';
  const str = String(logId);
  return str.length > 8 ? `${str.substring(0, 8)}...` : str;
};

export default function JobLogs() {
  const [jobLogs, setJobLogs] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDepartment, setSelectedDepartment] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [selectedDate, setSelectedDate] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedLog, setSelectedLog] = useState(null);
  const [logDetails, setLogDetails] = useState('');

  useEffect(() => {
    loadData();
  }, [selectedDepartment, selectedStatus, selectedDate]);

  const loadData = async () => {
    try {
      setLoading(true);
      
      // Load departments for filter
      const deptResponse = await departmentService.getAll(1, 100);
      setDepartments(deptResponse.data || []);

      // Build filters
      const filters = {};
      if (selectedDepartment !== 'all') {
        // Filter by schedule_def_id that belongs to department
        // We'll filter client-side after fetching
      }
      if (selectedStatus !== 'all') {
        filters.status = selectedStatus === 'success' ? 'completed' : selectedStatus;
      }
      if (selectedDate) {
        filters.date_from = `${selectedDate}T00:00:00Z`;
        filters.date_to = `${selectedDate}T23:59:59Z`;
      }
      
      console.log('[DEBUG] Fetch Params → dept=', selectedDepartment, 'status=', selectedStatus, 'date=', selectedDate);

      // Load job logs (limit to last 10 logs)
      console.log('[TRACE] ScheduleManager JobLogs: Loading data...');
      console.log('[TRACE] ScheduleManager JobLogs: Filters:', filters);
      
      const response = await scheduleService.getJobLogs(1, 10, filters);
      
      console.log('[TRACE] ScheduleManager JobLogs: Response:', response);
      console.log('[DEBUG] Checking Schedule Logs → count:', response.data?.length || 0);
      let logs = (response.data || []).slice(0, 10); // Ensure only 10 logs are displayed
      
      // If department filter is set, we need to filter by schedule_def_id
      // For now, we'll just load all and filter client-side
      // In production, this should be done server-side
      
      console.log('[TRACE] ScheduleManager JobLogs: Setting logs:', logs.length);
      console.log('[DEBUG] Frontend Response Rendered Successfully');
      
      setJobLogs(logs);
    } catch (err) {
      console.error('[TRACE] ScheduleManager JobLogs: Error loading data:', err);
      console.error('[TRACE] ScheduleManager JobLogs: Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
        url: err.config?.url,
      });
      setError(err.response?.data?.error || '載入執行日誌失敗');
      console.error('Error loading job logs:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleViewLog = async (log) => {
    try {
      setSelectedLog(log);
      
      // Fetch detailed log information
      const logId = log.logID || log.jobLogID;
      console.log('[TRACE] ScheduleManager JobLogs: Fetching log details for:', logId);
      const response = await scheduleService.getJobLogById(logId);
      const logData = response.data;
      
      // Format log details
      let details = '';
      if (logData.metadata) {
        if (typeof logData.metadata === 'string') {
          details = logData.metadata;
        } else {
          details = JSON.stringify(logData.metadata, null, 2);
        }
      }
      
      if (logData.resultSummary) {
        details += `\n\n結果摘要:\n${logData.resultSummary}`;
      }
      
      if (logData.error_message) {
        details += `\n\n錯誤訊息:\n${logData.error_message}`;
      }
      
      // If no details, create a default log entry
      if (!details) {
        const startTime = formatDateTime(logData.startTime);
        const endTime = formatDateTime(logData.endTime) || '執行中...';
        details = `[INFO] ${startTime} - 排班作業 '${formatLogId(logData.logID)}' 已啟動。\n`;
        if (logData.endTime) {
          details += `[INFO] ${endTime} - 作業${logData.status === 'completed' ? '成功結束' : '已結束'}。`;
        } else {
          details += `[INFO] ${startTime} - 作業執行中...`;
        }
      }
      
      setLogDetails(details);
      setIsModalOpen(true);
    } catch (err) {
      console.error('Error loading log details:', err);
      setLogDetails('載入日誌詳細內容失敗');
      setIsModalOpen(true);
    }
  };

  const getScheduleName = (log) => {
    // Extract schedule name from schedule_definition relationship
    if (log.schedule_definition?.scheduleName) {
      return log.schedule_definition.scheduleName;
    }
    if (log.scheduleName) {
      return log.scheduleName;
    }
    // Try to get from schedule definition if nested
    if (log.scheduleDefinition?.scheduleName) {
      return log.scheduleDefinition.scheduleName;
    }
    if (log.scheduleDefID || log.schedule_def_id) {
      return `班表 ${formatLogId(log.scheduleDefID || log.schedule_def_id)}`;
    }
    return '未知班表';
  };

  const getTriggerer = (log) => {
    // Check user relationship
    if (log.user) {
      const user = log.user;
      const userId = user.userID ? `SM-${String(user.userID).padStart(3, '0')}` : 'SM-000';
      return `${user.full_name || user.username} (${userId})`;
    }
    if (log.runByUser) {
      const user = log.runByUser;
      const userId = user.userID ? `SM-${String(user.userID).padStart(3, '0')}` : 'SM-000';
      return `${user.full_name || user.username} (${userId})`;
    }
    if (log.runByUserID) {
      return `使用者 (SM-${String(log.runByUserID).padStart(3, '0')})`;
    }
    return '系統';
  };

  if (loading && jobLogs.length === 0) {
    return <LoadingSpinner />;
  }

  return (
    <div className="bg-gray-100 p-4 md:p-8">
      {/* D2.1: 頂部標題和篩選 */}
      <div className="flex flex-col md:flex-row justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">排班作業執行日誌</h1>
          <p className="mt-1 text-sm text-gray-600">檢視所有 AI 排班作業的執行紀錄。</p>
        </div>
        <div className="flex flex-col md:flex-row gap-3 mt-4 md:mt-0">
          {/* 篩選器 */}
          <select
            value={selectedDepartment}
            onChange={(e) => setSelectedDepartment(e.target.value)}
            className="block w-full md:w-auto px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          >
            <option value="all">所有部門</option>
            {departments.map((dept) => (
              <option key={dept.departmentID} value={dept.departmentID}>
                {dept.departmentName}
              </option>
            ))}
          </select>
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="block w-full md:w-auto px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          >
            <option value="all">所有狀態</option>
            <option value="success">成功</option>
            <option value="error">失敗</option>
            <option value="running">執行中</option>
          </select>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="block w-full md:w-auto px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {typeof error === 'string' ? error : (error?.message || error?.error || String(error) || '發生錯誤')}
        </div>
      )}

      {/* D2.2: 日誌表格 */}
      <div className="bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="w-full overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  執行ID
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  班表名稱
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  開始時間
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  結束時間
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  狀態
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  觸發者
                </th>
                <th className="px-5 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {jobLogs.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-5 py-4 text-center text-sm text-gray-500">
                    目前沒有執行日誌
                  </td>
                </tr>
              ) : (
                jobLogs.map((log) => (
                  <tr key={log.logID || log.jobLogID}>
                    <td className="px-5 py-4 whitespace-nowrap text-sm font-mono text-gray-500">
                      {formatLogId(log.logID || log.jobLogID)}
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {getScheduleName(log)}
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatDateTime(log.startTime)}
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-500">
                      {formatDateTime(log.endTime)}
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap">
                      {getStatusBadge(log.status)}
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-500">
                      {getTriggerer(log)}
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap text-center text-sm font-medium">
                      <button
                        onClick={() => handleViewLog(log)}
                        className="text-indigo-600 hover:text-indigo-900"
                      >
                        檢視
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* D2.3: 日誌詳細內容彈出視窗 (Modal) */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedLog(null);
          setLogDetails('');
        }}
        title=""
        size="lg"
      >
        <div className="flex items-center justify-between pb-4 border-b border-gray-200">
          <h3 className="text-lg leading-6 font-bold text-gray-900">執行日誌詳細內容</h3>
          <button
            onClick={() => {
              setIsModalOpen(false);
              setSelectedLog(null);
              setLogDetails('');
            }}
            className="text-gray-400 hover:text-gray-600"
          >
            <svg
              className="h-6 w-6"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <div className="mt-4">
          {selectedLog && (
            <>
              <p className="text-sm text-gray-600">
                <strong>執行ID:</strong>{' '}
                <span className="font-mono">{formatLogId(selectedLog.logID || selectedLog.jobLogID)}</span>
              </p>
              <p className="text-sm text-gray-600 mt-1">
                <strong>狀態:</strong> {getStatusBadge(selectedLog.status)}
              </p>
            </>
          )}

          <label htmlFor="log-details" className="block text-sm font-medium text-gray-700 mt-4">
            詳細日誌:
          </label>
          <pre
            id="log-details"
            className="w-full h-64 p-3 mt-1 bg-gray-900 text-white text-xs font-mono rounded-md overflow-auto"
          >
            {logDetails || '載入中...'}
          </pre>
        </div>

        <div className="mt-6 text-right">
          <Button
            variant="secondary"
            onClick={() => {
              setIsModalOpen(false);
              setSelectedLog(null);
              setLogDetails('');
            }}
          >
            關閉
          </Button>
        </div>
      </Modal>
    </div>
  );
}
