import { useState, useEffect } from 'react';
import { scheduleService } from '../../services/scheduleService';
import DataTable from '../../components/DataTable';
import Button from '../../components/Button';

export default function Export() {
  const [jobLogs, setJobLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    loadJobLogs();
  }, []);

  const loadJobLogs = async () => {
    try {
      setLoading(true);
      setError('');
      
      console.log('[TRACE] ScheduleManager Export: Loading completed job logs...');
      
      // Filter for both 'completed' and 'success' statuses (both indicate completed jobs)
      // Limit to last 10 logs
      const response = await scheduleService.getJobLogs(1, 10, { status: 'completed' });
      // Note: Backend filters by exact status match, so we get 'completed' status
      // If backend supports multiple statuses, we could use: { status: ['completed', 'success'] }
      
      console.log('[TRACE] ScheduleManager Export: Response:', response);
      console.log('[DEBUG] Checking Schedule Logs → count:', response.data?.length || 0);
      
      setJobLogs((response.data || []).slice(0, 10)); // Ensure only 10 logs are displayed
      
      console.log('[DEBUG] Frontend Response Rendered Successfully');
    } catch (err) {
      console.error('[TRACE] ScheduleManager Export: Error loading data:', err);
      console.error('[TRACE] ScheduleManager Export: Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
      });
      setError(err.response?.data?.error || 'Failed to load job logs');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (jobLog, event) => {
    try {
      console.log('[DEBUG] Exporting job log:', jobLog.logID);
      
      // Show loading state
      const exportButton = event?.target;
      if (exportButton) {
        exportButton.disabled = true;
        exportButton.textContent = '匯出中...';
      }
      
      // Call export API
      let blob;
      try {
        blob = await scheduleService.exportJobLog(jobLog.logID || jobLog.jobLogID);
        
        // Check if response is actually an error (blob might contain JSON error)
        if (blob.type === 'application/json' || blob.type.includes('json')) {
          const text = await blob.text();
          const errorData = JSON.parse(text);
          throw { response: { data: errorData, status: errorData.error ? 400 : 500 } };
        }
      } catch (apiError) {
        // If it's a blob error response, try to parse it
        if (apiError.response?.data instanceof Blob) {
          const text = await apiError.response.data.text();
          const errorData = JSON.parse(text);
          throw { response: { data: errorData, status: errorData.error ? 400 : 500 } };
        }
        throw apiError;
      }
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      // Generate filename from job log
      const scheduleName = jobLog.scheduleName || jobLog.schedule_definition?.scheduleName || 'schedule';
      const logId = jobLog.logID || jobLog.jobLogID || 'unknown';
      const date = new Date().toISOString().split('T')[0].replace(/-/g, '');
      const filename = `${scheduleName.replace(/\s+/g, '_')}_${logId.substring(0, 8)}_${date}.csv`;
      
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      
      // Cleanup
      link.remove();
      window.URL.revokeObjectURL(url);
      
      console.log('[DEBUG] Export completed successfully');
      
      // Reset button
      if (exportButton) {
        exportButton.disabled = false;
        exportButton.textContent = '匯出';
      }
    } catch (err) {
      console.error('[DEBUG] Export error:', err);
      console.error('[DEBUG] Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
      });
      
      let errorMsg = '匯出失敗';
      if (err.response?.status === 404) {
        errorMsg = '找不到此作業日誌';
      } else if (err.response?.status === 400) {
        errorMsg = err.response.data?.error || '作業尚未完成，無法匯出';
      } else if (err.response?.status === 403) {
        errorMsg = '無權限匯出此作業';
      } else if (err.response?.data?.error) {
        errorMsg = err.response.data.error;
      }
      
      alert(errorMsg);
      
      // Reset button
      const exportButton = event?.target;
      if (exportButton) {
        exportButton.disabled = false;
        exportButton.textContent = '匯出';
      }
    }
  };

  const columns = [
    { key: 'logID', label: '作業ID', render: (value) => value ? `${value.substring(0, 8)}...` : '--' },
    { 
      key: 'scheduleName', 
      label: '班表名稱',
      render: (value, row) => row.schedule_definition?.scheduleName || row.scheduleName || '--'
    },
    { 
      key: 'status', 
      label: '狀態', 
      render: (value) => (
        <span className={`px-2 py-1 text-xs rounded-full ${
          value === 'completed' || value === 'success' ? 'bg-green-100 text-green-800' :
          value === 'running' ? 'bg-blue-100 text-blue-800' :
          value === 'failed' ? 'bg-red-100 text-red-800' :
          'bg-gray-100 text-gray-800'
        }`}>
          {value === 'completed' || value === 'success' ? '已完成' :
           value === 'running' ? '執行中' :
           value === 'failed' ? '失敗' : value}
        </span>
      )
    },
    { key: 'startTime', label: '開始時間', render: (value) => value ? new Date(value).toLocaleString('zh-TW') : '--' },
    { key: 'endTime', label: '完成時間', render: (value) => value ? new Date(value).toLocaleString('zh-TW') : '--' },
  ];

  const actions = (row) => (
    <Button 
      size="sm" 
      onClick={(e) => handleExport(row, e)}
      disabled={row.status !== 'completed' && row.status !== 'success'}
      title={row.status !== 'completed' && row.status !== 'success' ? '只能匯出已完成的作業' : '匯出排班結果'}
    >
      匯出
    </Button>
  );

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">匯出</h1>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {typeof error === 'string' ? error : (error?.message || error?.error || String(error) || '發生錯誤')}
        </div>
      )}

      <DataTable
        columns={columns}
        data={jobLogs}
        loading={loading}
        actions={actions}
        emptyMessage="目前沒有已完成的作業可匯出"
      />
    </div>
  );
}
