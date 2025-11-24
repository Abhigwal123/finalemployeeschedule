import { useState, useEffect } from 'react';
import { scheduleService } from '../../services/scheduleService';
import { departmentService } from '../../services/departmentService';
import { tenantService } from '../../services/tenantService';
import { useAuth } from '../../context/AuthContext';
import LoadingSpinner from '../../components/LoadingSpinner';
import Modal from '../../components/Modal';
import Button from '../../components/Button';
import { normalizeApiError, ensureString } from '../../utils/apiError';

const getStatusBadge = (status) => {
  const statusMap = {
    'completed': { label: '已完成', bg: 'bg-green-100', text: 'text-green-800' },
    'running': { label: '執行中...', bg: 'bg-yellow-100', text: 'text-yellow-800' },
    'pending': { label: '等待中', bg: 'bg-gray-100', text: 'text-gray-800' },
    'failed': { label: '失敗', bg: 'bg-red-100', text: 'text-red-800' },
    'open': { label: '開放中', bg: 'bg-green-100', text: 'text-green-800' },
    'closed': { label: '關閉', bg: 'bg-red-100', text: 'text-red-800' },
  };

  const statusConfig = statusMap[status] || { label: status || '未知', bg: 'bg-gray-100', text: 'text-gray-800' };

  return (
    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${statusConfig.bg} ${statusConfig.text}`}>
      {statusConfig.label}
    </span>
  );
};

const formatDate = (dateString) => {
  if (!dateString) return '--';
  const date = new Date(dateString);
  const month = date.getMonth() + 1;
  const day = date.getDate();
  return `${month}/${day}`;
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

export default function Scheduling() {
  const { user } = useAuth();
  const [schedules, setSchedules] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedTenant, setSelectedTenant] = useState('all');
  const [selectedDepartment, setSelectedDepartment] = useState('all');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedSchedule, setSelectedSchedule] = useState(null);
  const [running, setRunning] = useState(false);
  const [isAnalysisModalOpen, setIsAnalysisModalOpen] = useState(false);
  const [selectedScheduleForAnalysis, setSelectedScheduleForAnalysis] = useState(null);
  const [scheduleLogs, setScheduleLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);

  useEffect(() => {
    loadData();
  }, [selectedTenant, selectedDepartment]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError('');
      
      console.log('[DEBUG] Fetch schedule data...');
      
      // Load departments and tenants for filters
      const [deptResponse, tenantResponse, schedulesResponse] = await Promise.all([
        departmentService.getAll(1, 100),
        user?.is_admin ? tenantService.getAll(1, 100) : Promise.resolve({ data: [] }),
        scheduleService.getDefinitions(1, 100, { 
          active: 'true',
          ...(selectedDepartment !== 'all' && { department_id: selectedDepartment })
        }),
      ]);

      setDepartments(deptResponse.data || []);
      setTenants(tenantResponse.data || []);
      const scheduleDefs = schedulesResponse.items || [];

      // Create department map for quick lookup
      const departmentMap = new Map();
      deptResponse.data?.forEach(dept => {
        departmentMap.set(dept.departmentID, dept.departmentName);
      });

      // Load job status for each schedule
      console.log('[DEBUG] Loading job status for', scheduleDefs.length, 'schedules...');
      const schedulesWithStatus = await Promise.all(
        scheduleDefs.map(async (schedule) => {
          try {
            console.log('[DEBUG] Checking job status for schedule:', schedule.scheduleDefID);
            
            // Get only the latest job status (1 log is enough for status check)
            const jobStatusResponse = await scheduleService.getJobLogs(1, 1, {
              schedule_def_id: schedule.scheduleDefID,
            });
            
            console.log('[DEBUG] Job status response for', schedule.scheduleDefID, ':', jobStatusResponse);
            const latestJob = (jobStatusResponse.data || [])?.[0] || null;
            console.log('[DEBUG] Latest job for', schedule.scheduleDefID, ':', latestJob ? {status: latestJob.status, logID: latestJob.logID} : 'none');
            
            // Determine pre-schedule status (open/closed) - this would come from Google Sheets
            // For now, check if there's a recent completed job
            const preScheduleStatus = latestJob?.status === 'completed' ? 'closed' : 'open';
            
            return {
              ...schedule,
              departmentName: departmentMap.get(schedule.departmentID) || '未指定部門',
              latestJob,
              preScheduleStatus,
              lastModifiedDate: schedule.updated_at || schedule.created_at,
            };
          } catch (err) {
            console.error(`Error loading status for schedule ${schedule.scheduleDefID}:`, err);
            return {
              ...schedule,
              departmentName: departmentMap.get(schedule.departmentID) || '未指定部門',
              latestJob: null,
              preScheduleStatus: 'open',
              lastModifiedDate: schedule.updated_at || schedule.created_at,
            };
          }
        })
      );

      // Filter by tenant if needed
      let filteredSchedules = schedulesWithStatus;
      if (selectedTenant !== 'all') {
        filteredSchedules = schedulesWithStatus.filter(
          s => s.tenantID?.toString() === selectedTenant
        );
      }

      console.log('[DEBUG] Final schedules with status:', filteredSchedules.length);
      console.log('[DEBUG] Frontend received updated logs');
      if (filteredSchedules.length > 0) {
        console.log('[DEBUG] First schedule status:', {
          name: filteredSchedules[0].scheduleName,
          status: filteredSchedules[0].preScheduleStatus,
          latestJob: filteredSchedules[0].latestJob ? {status: filteredSchedules[0].latestJob.status} : null
        });
      }
      
      setSchedules(filteredSchedules);
    } catch (err) {
      console.error('[DEBUG] Error loading schedule data:', err);
      console.error('[DEBUG] Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
        url: err.config?.url
      });
      
      let errorMsg = '載入班表資料失敗';
      if (err.response?.status === 403) {
        errorMsg = '無權限存取班表資料，請確認您的角色權限';
      } else if (err.response?.status === 401) {
        errorMsg = '登入已過期，請重新登入';
      } else if (!err.response) {
        errorMsg = '無法連接到伺服器，請確認後端服務是否正在運行';
      } else if (err.response?.data?.error) {
        errorMsg = err.response.data.error;
      }
      
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleRunSchedule = (schedule) => {
    setSelectedSchedule(schedule);
    setIsModalOpen(true);
  };

  const handleViewScheduleAnalysis = async (schedule) => {
    try {
      setSelectedScheduleForAnalysis(schedule);
      setIsAnalysisModalOpen(true);
      setLoadingLogs(true);
      setScheduleLogs([]);
      
      console.log('[DEBUG] Fetching logs for schedule:', schedule.scheduleDefID);
      
      // Fetch logs for this specific schedule (limit to last 10 logs)
      const response = await scheduleService.getJobLogs(1, 10, {
        schedule_def_id: schedule.scheduleDefID,
      });
      
      console.log('[DEBUG] Schedule logs response:', response);
      const logs = (response.data || []).slice(0, 10); // Ensure only 10 logs are displayed
      console.log('[DEBUG] Retrieved', logs.length, 'logs for schedule');
      
      setScheduleLogs(logs);
    } catch (err) {
      console.error('[DEBUG] Error loading schedule logs:', err);
      setError('載入班表執行日誌失敗');
      setScheduleLogs([]);
    } finally {
      setLoadingLogs(false);
    }
  };

  const confirmRunSchedule = async () => {
    if (!selectedSchedule) return;

    try {
      setRunning(true);
      setError(''); // Clear previous errors
      
      console.log('[DEBUG] Received Schedule Run Request');
      console.log('[DEBUG] Job Params:', { 
        scheduleDefID: selectedSchedule.scheduleDefID, 
        scheduleName: selectedSchedule.scheduleName 
      });
      
      const response = await scheduleService.runJob({
        scheduleDefID: selectedSchedule.scheduleDefID,
      });
      
      console.log('[DEBUG] Schedule run response:', response);
      console.log('[DEBUG] Response status:', response.success, 'job_id:', response.celery_task_id || response.data?.logID);
      
      if (response.success) {
        const executedScheduleDefID = selectedSchedule?.scheduleDefID;
        
        setIsModalOpen(false);
        setSelectedSchedule(null);
        
        // Reload data to show updated status
        console.log('[DEBUG] Reloading schedule data after run...');
        await loadData();
        console.log('[DEBUG] Schedule data reloaded successfully');
        console.log('[DEBUG] Frontend received updated logs');
        
        // If analysis modal is open for this schedule, refresh the logs
        if (isAnalysisModalOpen && selectedScheduleForAnalysis?.scheduleDefID === executedScheduleDefID) {
          console.log('[DEBUG] Refreshing logs in analysis modal...');
          await handleViewScheduleAnalysis(selectedScheduleForAnalysis);
        }
        
        // Get the job log ID from the response
        const jobLogId = response.data?.logID || response.data?.jobLogID || response.data?.log_id;
        
        if (jobLogId) {
          // Poll the job status for a few seconds to check if it fails quickly
          // This catches errors that happen during execution (e.g., "Error loading input data")
          let pollCount = 0;
          const maxPolls = 10; // Poll for up to 5 seconds (10 * 500ms)
          const pollInterval = 500; // Check every 500ms
          
          const checkJobStatus = async () => {
            try {
              const jobLogResponse = await scheduleService.getJobLogById(jobLogId);
              const jobLog = jobLogResponse.data || jobLogResponse;
              const status = jobLog.status;
              const errorMessage = jobLog.error_message || jobLog.errorMessage;
              
              console.log('[DEBUG] Job status check:', { status, errorMessage, pollCount });
              
              if (status === 'failed') {
                // Job failed - show the actual error message
                let errorMsg = errorMessage || '排班作業執行失敗';
                // Extract the actual error if it's in a specific format
                if (errorMessage) {
                  // Clean up error message - remove system prefixes and timestamps if present
                  let cleanError = errorMessage;
                  // Remove common prefixes like "[System] 'system' " or similar
                  cleanError = cleanError.replace(/^\[System\]\s*['"]?system['"]?\s*/i, '');
                  // Remove trailing timestamps like "5 小時前" or similar patterns
                  cleanError = cleanError.replace(/\s*\d+\s*(小時前|分鐘前|秒前|hours? ago|minutes? ago|seconds? ago).*$/i, '');
                  
                  if (cleanError.includes('Error loading input data')) {
                    errorMsg = `載入輸入資料時發生錯誤: ${cleanError}`;
                  } else {
                    errorMsg = cleanError;
                  }
                }
                setError(errorMsg);
                return true; // Stop polling
              } else if (status === 'completed' || status === 'success') {
                // Job completed successfully - no need to show message, data will refresh
                return true; // Stop polling
              } else if (status === 'running' || status === 'pending') {
                // Job is still running - continue polling
                if (pollCount < maxPolls) {
                  pollCount++;
                  setTimeout(checkJobStatus, pollInterval);
                }
                return false; // Continue polling
              }
            } catch (pollErr) {
              console.error('[DEBUG] Error polling job status:', pollErr);
              // If polling fails, just continue (job might still be running)
              return true; // Stop polling on error
            }
          };
          
          // Start polling after a short delay
          setTimeout(checkJobStatus, pollInterval);
        }
        
        // Show initial message that job was started
        alert('排班作業已開始執行');
      } else {
        setError(ensureString(response.error) || '執行排班失敗');
      }
    } catch (err) {
      console.error('[DEBUG] Schedule run error:', err);
      console.error('[DEBUG] Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
        url: err.config?.url
      });
      
      let errorMsg = '執行排班失敗';
      if (err.response?.status === 403) {
        errorMsg = '無權限執行排班作業，請確認您的角色權限';
      } else if (err.response?.status === 401) {
        errorMsg = '登入已過期，請重新登入';
      } else if (!err.response) {
        errorMsg = '無法連接到伺服器，請確認後端服務是否正在運行';
      } else {
        // Get detailed error message from backend
        const errorData = err.response?.data;
        if (errorData?.details) {
          // Show detailed error message from backend
          errorMsg = `執行排班失敗: ${errorData.details}`;
          console.error('[DEBUG] Backend error details:', errorData.details);
          console.error('[DEBUG] Backend error type:', errorData.error_type);
        } else {
          // Use normalizeApiError as fallback
          errorMsg = normalizeApiError(err);
        }
      }
      
      setError(errorMsg);
    } finally {
      setRunning(false);
    }
  };

  const getScheduleMonth = (schedule) => {
    // Extract month from schedule name or use current month
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    return `${year}/${month}`;
  };

  const getLatestJobStatus = (schedule) => {
    console.log('[DEBUG] Getting schedule status for:', schedule.scheduleName, {
      hasLatestJob: !!schedule.latestJob,
      latestJobStatus: schedule.latestJob?.status,
      preScheduleStatus: schedule.preScheduleStatus
    });
    
    // Determine status based on latest job and pre-schedule status
    if (!schedule.latestJob) {
      // No job yet - check pre-schedule status
      return schedule.preScheduleStatus === 'closed' ? 'closed' : 'open';
    }
    
    const jobStatus = schedule.latestJob.status || 'pending';
    
    // Map job status to UI status
    if (jobStatus === 'running') return 'running';
    if (jobStatus === 'completed' || jobStatus === 'success') return 'completed';
    if (jobStatus === 'failed') return 'failed';
    return 'pending';
  };

  const employeeId = user?.userID ? `SM-${String(user.userID).padStart(3, '0')}` : 'SM-000';
  const employeeName = user?.full_name || user?.username || '排班主管';

  if (loading && schedules.length === 0) {
    return <LoadingSpinner />;
  }

  return (
    <div className="bg-gray-100 p-4 md:p-8">
      {/* D1.1: 頂部標題和篩選 */}
      <div className="flex flex-col md:flex-row justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">排班作業儀表板</h1>
          <p className="mt-1 text-sm text-gray-600">歡迎，{employeeName} ({employeeId})</p>
        </div>
        <div className="flex gap-4 mt-4 md:mt-0">
          {/* 篩選器 */}
          {user?.is_admin && (
            <select
              value={selectedTenant}
              onChange={(e) => setSelectedTenant(e.target.value)}
              className="block w-full md:w-auto px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            >
              <option value="all">所有客戶機構</option>
              {tenants.map((tenant) => (
                <option key={tenant.tenantID} value={tenant.tenantID}>
                  {tenant.tenantName}
                </option>
              ))}
            </select>
          )}
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
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {ensureString(error)}
        </div>
      )}

      {/* D1.2: 排班作業表格 */}
      <div className="bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="w-full overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  部門
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  班表名稱
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  排班參數表
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  員工預排班表
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  排班結果及分析表
                </th>
                <th className="px-5 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  功能按鈕
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {schedules.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-5 py-4 text-center text-sm text-gray-500">
                    目前沒有班表資料
                  </td>
                </tr>
              ) : (
                schedules.map((schedule) => {
                  const jobStatus = getLatestJobStatus(schedule);
                  const hasCompletedJob = jobStatus === 'completed';
                  
                  return (
                    <tr key={schedule.scheduleDefID}>
                      <td className="px-5 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {schedule.departmentName}
                      </td>
                      <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-500">
                        {schedule.scheduleName}
                      </td>
                      <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-500">
                        <span className="text-xs text-gray-400 block">
                          最後異動日 {formatDate(schedule.lastModifiedDate)}
                        </span>
                        <a
                          href={schedule.paramsSheetURL || '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-600 hover:text-indigo-900 font-medium"
                        >
                          開啟
                        </a>
                      </td>
                      <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-500">
                        <span className="text-xs text-gray-400 block">
                          班表年月: {getScheduleMonth(schedule)}
                        </span>
                        {getStatusBadge(schedule.preScheduleStatus)}
                        <a
                          href={schedule.prefsSheetURL || schedule.paramsSheetURL || '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-2 text-indigo-600 hover:text-indigo-900 font-medium"
                        >
                          開啟
                        </a>
                      </td>
                      <td className="px-5 py-4 whitespace-nowrap text-sm text-gray-500">
                        {getStatusBadge(jobStatus)}
                        <a
                          href={schedule.resultsSheetURL || '#'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-2 text-indigo-600 hover:text-indigo-900 font-medium"
                        >
                          開啟
                        </a>
                        {hasCompletedJob && (
                          <a
                            href={schedule.resultsSheetURL || '#'}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ml-2 text-indigo-600 hover:text-indigo-900 font-medium"
                          >
                            (匯出)
                          </a>
                        )}
                      </td>
                      <td className="px-5 py-4 whitespace-nowrap text-center text-sm font-medium">
                        <button
                          onClick={() => handleRunSchedule(schedule)}
                          className="w-24 text-white bg-indigo-600 hover:bg-indigo-700 focus:ring-4 focus:ring-indigo-300 font-medium rounded-lg text-sm px-4 py-2 mr-2 mb-2"
                        >
                          執行排班
                        </button>
                        <button 
                          onClick={() => handleViewScheduleAnalysis(schedule)}
                          className="w-24 text-gray-900 bg-white border border-gray-300 hover:bg-gray-100 focus:ring-4 focus:ring-gray-200 font-medium rounded-lg text-sm px-4 py-2 mb-2"
                        >
                          班表分析
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* D1.3: 執行排班的彈出確認視窗 (Modal) */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedSchedule(null);
        }}
        title=""
        size="md"
      >
        <div className="flex items-start">
          <div className="flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-indigo-100 sm:h-10 sm:w-10">
            <svg
              className="h-6 w-6 text-indigo-600"
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
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div className="ml-4 text-left flex-1">
            <h3 className="text-lg leading-6 font-bold text-gray-900">確認執行排班？</h3>
            <div className="mt-2">
              <p className="text-sm text-gray-600">
                您即將為「<span className="font-semibold">{selectedSchedule?.scheduleName || ''}</span>」執行 AI 自動排班。
              </p>
              <p className="text-sm text-gray-500 mt-1">
                此動作將會覆蓋現有的「排班結果及分析表」。確定要繼續嗎？
              </p>
            </div>
          </div>
        </div>
        <div className="mt-6 sm:flex sm:flex-row-reverse">
          <Button
            onClick={confirmRunSchedule}
            loading={running}
            className="w-full sm:ml-3 sm:w-auto"
          >
            確認執行
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setIsModalOpen(false);
              setSelectedSchedule(null);
            }}
            className="mt-3 w-full sm:mt-0 sm:w-auto"
          >
            取消
          </Button>
        </div>
      </Modal>

      {/* D1.4: 班表分析彈出視窗 (Schedule Analysis Modal) */}
      <Modal
        isOpen={isAnalysisModalOpen}
        onClose={() => {
          setIsAnalysisModalOpen(false);
          setSelectedScheduleForAnalysis(null);
          setScheduleLogs([]);
        }}
        title=""
        size="xl"
      >
        <div className="flex items-center justify-between pb-4 border-b border-gray-200">
          <div>
            <h3 className="text-lg leading-6 font-bold text-gray-900">班表分析</h3>
            <p className="text-sm text-gray-600 mt-1">
              {selectedScheduleForAnalysis?.scheduleName || '班表執行日誌'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={async () => {
                if (selectedScheduleForAnalysis) {
                  await handleViewScheduleAnalysis(selectedScheduleForAnalysis);
                }
              }}
              className="text-gray-600 hover:text-gray-800 p-1"
              title="重新載入日誌"
            >
              <svg
                className="h-5 w-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
            </button>
            <button
              onClick={() => {
                setIsAnalysisModalOpen(false);
                setSelectedScheduleForAnalysis(null);
                setScheduleLogs([]);
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
        </div>

        <div className="mt-4">
          {loadingLogs ? (
            <div className="flex items-center justify-center py-8">
              <div className="text-gray-500">載入日誌中...</div>
            </div>
          ) : scheduleLogs.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <p>目前沒有執行日誌</p>
              <p className="text-sm mt-2">執行排班後，日誌將會顯示在這裡</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      執行ID
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      開始時間
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      結束時間
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      狀態
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      執行時間
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {scheduleLogs.map((log) => (
                    <tr key={log.logID || log.jobLogID}>
                      <td className="px-4 py-3 whitespace-nowrap text-sm font-mono text-gray-500">
                        {log.logID ? `${log.logID.substring(0, 8)}...` : '--'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                        {formatDateTime(log.startTime)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                        {log.endTime ? formatDateTime(log.endTime) : '執行中...'}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {getStatusBadge(log.status)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                        {log.execution_time_seconds
                          ? `${log.execution_time_seconds} 秒`
                          : '--'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="mt-6 pt-4 border-t border-gray-200">
          {selectedScheduleForAnalysis?.latestJob && (
            <div className="mb-4 p-3 bg-gray-50 rounded-lg">
              <h4 className="text-sm font-medium text-gray-700 mb-2">最新執行狀態</h4>
              <div className="text-sm text-gray-600">
                <p>
                  <strong>狀態:</strong> {getStatusBadge(selectedScheduleForAnalysis.latestJob.status)}
                </p>
                {selectedScheduleForAnalysis.latestJob.resultSummary && (
                  <p className="mt-1">
                    <strong>結果摘要:</strong> {selectedScheduleForAnalysis.latestJob.resultSummary}
                  </p>
                )}
                {selectedScheduleForAnalysis.latestJob.error_message && (
                  <p className="mt-1 text-red-600">
                    <strong>錯誤訊息:</strong> {selectedScheduleForAnalysis.latestJob.error_message}
                  </p>
                )}
              </div>
            </div>
          )}
          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                setIsAnalysisModalOpen(false);
                setSelectedScheduleForAnalysis(null);
                setScheduleLogs([]);
              }}
            >
              關閉
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
