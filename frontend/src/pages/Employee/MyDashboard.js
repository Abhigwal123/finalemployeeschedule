
import { useState, useEffect } from 'react';
import { employeeService } from '../../services/employeeService';
import { useAuth } from '../../context/AuthContext';
import LoadingSpinner from '../../components/LoadingSpinner';

const getDayOfWeek = (date) => {
  const days = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
  const dayIndex = new Date(date).getDay();
  return days[dayIndex];
};

const formatDate = (dateString) => {
  // Handle multiple date formats: "2025/10/01", "2025-10-01", "2025-10-01T00:00:00"
  let dateObj;
  
  if (!dateString) return '';
  
  // Try to parse various formats
  if (typeof dateString === 'string') {
    if (dateString.includes('/')) {
      // Format: "2025/10/01"
      const parts = dateString.split('/');
      if (parts.length >= 3) {
        dateObj = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
      } else {
        dateObj = new Date(dateString);
      }
    } else if (dateString.includes('-')) {
      // Format: "2025-10-01" or "2025-10-01T00:00:00"
      dateObj = new Date(dateString);
    } else {
      dateObj = new Date(dateString);
    }
  } else {
    dateObj = dateString;
  }
  
  // Check if date is valid
  if (!dateObj || isNaN(dateObj.getTime())) {
    // If invalid, try to extract from string
    const match = String(dateString).match(/(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/);
    if (match) {
      dateObj = new Date(parseInt(match[1]), parseInt(match[2]) - 1, parseInt(match[3]));
    } else {
      return String(dateString); // Return original if can't parse
    }
  }
  
  if (isNaN(dateObj.getTime())) {
    return String(dateString); // Return original if still invalid
  }
  
  const month = dateObj.getMonth() + 1;
  const day = dateObj.getDate();
  return `${month} 月 ${day} 日`;
};

const getShiftBadge = (shiftValue, shiftType) => {
  // If shiftValue is the actual Excel value (contains Chinese characters or is not a simple code)
  // Display it directly instead of mapping to generic labels
  if (shiftValue && shiftValue !== shiftType && shiftValue.length > 1) {
    // This is the actual shift value from Excel (e.g., "C 櫃台人力", "A 藥局人力")
    // Determine badge color based on shift type if available
    const shiftMap = {
      'D': { bg: 'bg-blue-100', text: 'text-blue-800' },
      'E': { bg: 'bg-orange-100', text: 'text-orange-800' },
      'N': { bg: 'bg-indigo-100', text: 'text-indigo-800' },
      'OFF': { bg: 'bg-gray-100', text: 'text-gray-800' },
    };
    
    const normalizedType = shiftType || 'D';
    const colors = shiftMap[normalizedType] || { bg: 'bg-gray-100', text: 'text-gray-800' };
    
    return (
      <span className={`px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${colors.bg} ${colors.text}`}>
        {shiftValue}
      </span>
    );
  }
  
  // Fallback to normalized shift type mapping for simple codes
  const shiftMap = {
    'D': { label: '白班 (D)', bg: 'bg-blue-100', text: 'text-blue-800' },
    'E': { label: '小夜 (E)', bg: 'bg-orange-100', text: 'text-orange-800' },
    'N': { label: '大夜 (N)', bg: 'bg-indigo-100', text: 'text-indigo-800' },
    'OFF': { label: '休假 (OFF)', bg: 'bg-gray-100', text: 'text-gray-800' },
  };

  const shift = shiftMap[shiftType] || { label: shiftType || '--', bg: 'bg-gray-100', text: 'text-gray-800' };
  
  return (
    <span className={`px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${shift.bg} ${shift.text}`}>
      {shift.label}
    </span>
  );
};

const getTimePeriod = (shiftType, timeRange) => {
  if (shiftType === 'OFF' || !shiftType) {
    return '--';
  }
  
  if (timeRange) {
    return timeRange;
  }

  // Default time ranges if not provided
  const defaultTimes = {
    'D': '08:00 - 16:00',
    'E': '16:00 - 00:00',
    'N': '00:00 - 08:00',
  };
  
  return defaultTimes[shiftType] || '--';
};

const generateMonthOptions = () => {
  const options = [];
  const currentDate = new Date();
  
  for (let i = 0; i < 12; i++) {
    const date = new Date(currentDate.getFullYear(), currentDate.getMonth() - i, 1);
    const year = date.getFullYear();
    const month = date.getMonth() + 1;
    const value = `${year}-${String(month).padStart(2, '0')}`;
    const label = `${year} 年 ${month} 月`;
    options.push({ value, label });
  }
  
  return options;
};

export default function MyDashboard() {
  const { user } = useAuth();
  const [scheduleData, setScheduleData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastSyncedAt, setLastSyncedAt] = useState(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState('尚未同步'); // '尚未同步', '同步中...', '已同步'
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });

  useEffect(() => {
    loadSchedule();
    checkSyncStatus();
  }, [selectedMonth]);

  const loadSchedule = async (retryCount = 0) => {
    try {
      setLoading(true);
      setError(''); // Clear previous errors
      
      console.log(`[TRACE] Frontend: Loading schedule for month=${selectedMonth} (attempt ${retryCount + 1})`);
      
      // Try new schedule endpoint first
      try {
        const response = await employeeService.getSchedule(selectedMonth);
        console.log('[DEBUG] ========== MYDASHBOARD RESPONSE HANDLING ==========');
        console.log('[DEBUG] Response type:', typeof response, Array.isArray(response) ? 'Array' : 'Object');
        console.log('[DEBUG] Response:', response);
        console.log('[DEBUG] Response keys:', response && typeof response === 'object' && !Array.isArray(response) ? Object.keys(response) : 'N/A');
        console.log('[DEBUG] ===================================================');
        
        // Handle 202 Accepted - Auto-sync triggered
        if (response && response.auto_sync_triggered && response.message && response.message.includes('Auto-sync triggered')) {
          console.log('[AUTO-SYNC] Backend triggered auto-sync, will retry in 30 seconds');
          setSyncStatus('同步中...');
          setIsSyncing(true);
          setError(''); // Clear error - show sync message instead
          
          // Auto-retry after 30 seconds (max 5 retries = 2.5 minutes)
          if (retryCount < 5) {
            setTimeout(() => {
              console.log(`[AUTO-SYNC] Retrying schedule fetch (attempt ${retryCount + 2})`);
              loadSchedule(retryCount + 1);
            }, 30000); // 30 seconds
          } else {
            console.warn('[AUTO-SYNC] Max retries reached, showing error');
            setError('班表同步時間過長，請稍後手動重新整理');
            setIsSyncing(false);
            setSyncStatus('尚未同步');
            setLoading(false);
          }
          return;
        }
        
        // Handle raw_data from Google Sheets fallback
        if (response && response.raw_data && response.source === 'google_sheets') {
          console.log('[TRACE] Frontend: Received raw_data from Google Sheets, parsing...');
          const parsedSchedules = parseScheduleData({ data: { my_schedule: response.raw_data } }, user);
          setScheduleData(parsedSchedules);
          setLoading(false);
          setError('');
          return;
        }
        
        if (response && response.success !== false) {
          // Handle both old and new response formats
          const scheduleSource = Array.isArray(response)
            ? response
            : response.entries ||
              response.schedule ||
              response.data?.entries ||
              response.data?.schedule ||
              [];
          const schedule = Array.isArray(scheduleSource) ? scheduleSource : [];
          console.log(`[TRACE] Frontend: Schedule endpoint returned ${schedule.length} entries`);
          console.log(`[TRACE] Frontend: Response structure:`, {
            success: response.success,
            month: response.month,
            scheduleLength: schedule.length,
            metadata: response.metadata
          });
          
          // Update sync status based on backend response
          if (response.last_synced_at) {
            setLastSyncedAt(response.last_synced_at);
          }
          
          // Determine sync status: if synced=true from backend OR if schedule data exists
          const isSynced = response.synced === true || schedule.length > 0;
          if (isSynced) {
            setSyncStatus('已同步');
            setIsSyncing(false);
          }
          
          if (schedule.length > 0) {
            console.log(`[TRACE] Frontend: First entry sample:`, schedule[0]);
            
            // Transform data to expected format
            const schedules = schedule.map(entry => {
              // Ensure date is formatted correctly
              let dateStr = entry.date;
              // Convert "2025/10/01" to "2025-10-01" format if needed
              if (dateStr && dateStr.includes('/')) {
                dateStr = dateStr.replace(/\//g, '-');
              }
              
              // CRITICAL: Use actual shift value from Excel (e.g., "C 櫃台人力", "A 藥局人力")
              // Fallback to normalized shift_type only if shift is not available
              const actualShift = entry.shift || entry.shift_value || entry.shiftValue;
              const normalizedShiftType = entry.shift_type || entry.shiftType || entry.shift_code || entry.shiftCode;
              
              // Use actual shift value if available, otherwise use normalized type
              const shiftDisplay = actualShift || normalizedShiftType || 'D';
              
              let timeRange = entry.time_range || entry.timeRange;
              if (!timeRange && (entry.start_time || entry.end_time)) {
                const start = entry.start_time || '--';
                const end = entry.end_time || '--';
                if (start !== '--' || end !== '--') {
                  timeRange = `${start || '--'} - ${end || '--'}`;
                }
              }

              return {
                date: dateStr,
                shift: shiftDisplay,  // Store actual shift value from Excel
                shiftType: normalizedShiftType || 'D',  // Keep normalized type for time range calculation
                timeRange: timeRange || getTimePeriod(normalizedShiftType || 'D', entry.time_range || entry.timeRange),
              };
            });
            
            console.log(`[TRACE] Frontend: Transformed ${schedules.length} schedule entries`);
            console.log(`[DEBUG] Frontend rendering ${schedules.length} schedule rows`);
            console.log(`[TRACE] Frontend: First transformed entry:`, schedules[0]);
            
            setScheduleData(schedules);
            setError(''); // Clear error - data exists, no error
            setIsSyncing(false); // Clear syncing state
            setSyncStatus('已同步'); // Mark as synced when data exists
            console.log(`[DEBUG] ========== FINAL SCHEDULE DATA SET ==========`);
            console.log(`[DEBUG] Total schedules:`, schedules.length);
            if (schedules.length > 0) {
              console.log(`[DEBUG] First schedule:`, schedules[0]);
              console.log(`[DEBUG] Last schedule:`, schedules[schedules.length - 1]);
            }
            console.log(`[DEBUG] =============================================`);
            console.log(`[TRACE] Frontend: ✅ Successfully loaded ${schedules.length} schedule entries`);
            console.log(`[DEBUG] ✅ Employee dashboard successfully loaded`);
            return;
          } else {
            console.warn('[TRACE] Frontend: Schedule endpoint returned empty schedule array');
            setScheduleData([]);
            
            // Update sync status: if backend says synced=true, mark as synced even if empty
            if (response.synced === true) {
              setSyncStatus('已同步');
              setIsSyncing(false);
              setError(''); // No error - data was synced, just empty for this month
            } else {
              setSyncStatus('尚未同步');
            }
            
            // Check if there's a helpful message
            if (response.message) {
              console.log(`[TRACE] Frontend: Response message: ${response.message}`);
              // Only show error if not synced - if synced but empty, that's OK
              if (response.synced !== true) {
                setError(response.message);
              } else {
                setError(''); // Synced but empty - no error
              }
            } else if (response.available_months && response.available_months.length > 0) {
              const msg = `目前沒有 ${selectedMonth} 的班表資料。可用月份：${response.available_months.join(', ')}`;
              // Only show as error if not synced
              if (response.synced !== true) {
                setError(msg);
              } else {
                setError(''); // Synced but empty - no error
              }
            } else {
              setError(''); // Clear error - empty is OK if synced, just show "目前沒有班表資料" in UI
            }
          }
        } else if (response && (response.success === false || response.error)) {
          console.error(`[TRACE] Frontend: Schedule endpoint error - ${response.error || 'Unknown error'}`);
          
          // Only show error if we don't have schedule data
          // If schedule data exists, don't show error even if success=false
          const hasScheduleData =
            (Array.isArray(response.entries) && response.entries.length > 0) ||
            (Array.isArray(response.schedule) && response.schedule.length > 0) ||
            (Array.isArray(response.data?.entries) && response.data.entries.length > 0) ||
            (Array.isArray(response.data?.schedule) && response.data.schedule.length > 0);
          
          if (!hasScheduleData) {
            // Enhanced error messages
            let errorMsg = response.error || '載入班表資料失敗';
            
            if (response.error && response.error.includes('Google Sheets service not available')) {
              errorMsg = '無法連接到 Google Sheets 服務，請聯絡系統管理員';
            } else if (response.error && (response.error.includes('not found') || response.error.includes('404'))) {
              errorMsg = `無法找到 Google Sheets 資料：${response.error}`;
            } else if (response.error && response.error.includes('Failed sheets')) {
              errorMsg = `Google Sheets 讀取失敗：${response.error}`;
            } else if (response.details) {
              // Show specific sheet errors if available
              const failedSheets = Object.entries(response.details.sheets || {})
                .filter(([_, data]) => data && !data.success)
                .map(([name, data]) => `${name}: ${data.error || 'Unknown error'}`);
              if (failedSheets.length > 0) {
                errorMsg = `無法讀取以下工作表：${failedSheets.join(', ')}`;
              }
            }
            
            setError(errorMsg);
            setSyncStatus('尚未同步');
          } else {
            // Data exists, no error
            setError('');
            setSyncStatus('已同步');
          }
        } else {
          console.warn('[TRACE] Frontend: Unexpected response structure:', response);
          console.warn('[TRACE] Frontend: Response keys:', Object.keys(response || {}));
          setError('無法載入班表資料，請稍後再試');
        }
      } catch (scheduleErr) {
        console.error('[TRACE] Frontend: Schedule endpoint failed:', scheduleErr);
        console.error('[TRACE] Frontend: Error details:', {
          message: scheduleErr.message,
          response: scheduleErr.response?.data,
          status: scheduleErr.response?.status,
          code: scheduleErr.code,
          config: scheduleErr.config?.url
        });
        
        // Enhanced error message based on error type
        let errorMsg = '無法載入班表資料，請稍後再試';
        
        if (!scheduleErr.response) {
          // Network error - backend not reachable
          errorMsg = '無法連接到伺服器，請確認後端服務是否正在運行';
          console.error('[TRACE] Frontend: Network/CORS error - backend may not be running');
        } else if (scheduleErr.response.status === 500) {
          const errorData = scheduleErr.response.data;
          if (errorData?.details && errorData.details.includes('os')) {
            errorMsg = '後端服務錯誤，請聯絡系統管理員 (服務配置問題)';
          } else {
            errorMsg = errorData?.error || '後端服務錯誤，請稍後再試';
          }
        } else if (scheduleErr.response.status === 503) {
          errorMsg = scheduleErr.response.data?.error || 'Google Sheets 服務暫時無法使用';
        } else {
          errorMsg = scheduleErr.response.data?.error || errorMsg;
        }
        
        setError(errorMsg);
        
        // Skip fallback to schedule-data endpoint (it times out)
        // Exit early if schedule endpoint fails
        console.log('[TRACE] Frontend: Skipping fallback schedule-data endpoint (timeout issue)');
        return;
      }
      
      // If we get here, schedule endpoint failed and we skip fallback
      console.log('[TRACE] Frontend: Schedule endpoint failed, not trying fallback (timeout issue)');
      
      // Check if response has data structure
      if (response && typeof response === 'object') {
        if (response.success && response.data) {
          // Parse the schedule data from Google Sheets
          const schedules = parseScheduleData(response, user);
          console.log('✅ Parsed schedules:', schedules);
          
          if (schedules.length > 0) {
            setScheduleData(schedules);
            setError(''); // Clear error if we got data
          } else {
            // Check if there's actually data but parsing failed
            const mySchedule = response.data?.my_schedule;
            const rows = mySchedule?.rows || [];
            const columns = mySchedule?.columns || [];
            
            console.log('📊 Data structure check:', {
              hasMySchedule: !!mySchedule,
              rowCount: rows.length,
              columnCount: columns.length,
              firstRow: rows[0],
              columns: columns.slice(0, 5)
            });
            
            if (rows && rows.length > 0) {
              console.warn('⚠️ Data exists but parsing failed. Rows:', rows);
              console.warn('⚠️ Columns:', columns);
              console.warn('[TRACE] Frontend: Data exists but parsing failed - rows:', rows.length, 'columns:', columns.length);
              setError('班表資料格式無法解析，請聯絡管理員（資料存在但格式不正確）');
            } else {
              console.warn('[TRACE] Frontend: No rows in schedule data');
              setError('無法從 Google Sheets 取得班表資料，請確認資料是否存在');
            }
          }
        } else if (response.error) {
          // Backend returned an error
          console.error('[TRACE] Frontend: Backend returned error:', response.error);
          
          // Only show error if we don't have schedule data
          const hasScheduleData =
            (Array.isArray(response.entries) && response.entries.length > 0) ||
            (Array.isArray(response.schedule) && response.schedule.length > 0) ||
            (Array.isArray(response.data?.entries) && response.data.entries.length > 0) ||
            (Array.isArray(response.data?.schedule) && response.data.schedule.length > 0);
          
          if (!hasScheduleData) {
            // Check if it's the Google Sheets service error
            if (response.error.includes('Google Sheets service not available')) {
              setError('無法連接到 Google Sheets 服務，請聯絡系統管理員');
            } else {
              setError(response.error || '載入班表資料失敗');
            }
            setSyncStatus('尚未同步');
            
            // Try fallback endpoint
            console.log('🔄 Trying fallback schedule endpoint...');
            try {
              const fallbackResponse = await employeeService.getMySchedule(selectedMonth);
              if (fallbackResponse && fallbackResponse.schedule && fallbackResponse.schedule.length > 0) {
                setScheduleData(fallbackResponse.schedule);
                setError(''); // Clear error if fallback worked
                setSyncStatus('已同步');
              }
            } catch (fallbackErr) {
              console.error('Fallback also failed:', fallbackErr);
            }
          } else {
            // Data exists, no error
            setError('');
            setSyncStatus('已同步');
          }
        } else {
          // Response structure unclear - try fallback
          console.warn('⚠️ Unexpected response structure:', response);
          console.log('🔄 Trying fallback endpoint...');
          try {
            const fallbackResponse = await employeeService.getMySchedule(selectedMonth);
            if (fallbackResponse && fallbackResponse.schedule && fallbackResponse.schedule.length > 0) {
              setScheduleData(fallbackResponse.schedule);
              setError(''); // Clear error if fallback worked
              setSyncStatus('已同步');
            } else {
              setError('無法載入班表資料，請檢查後端服務');
              setSyncStatus('尚未同步');
            }
          } catch (fallbackErr) {
            console.error('Fallback failed:', fallbackErr);
            setError('無法載入班表資料，請檢查後端服務');
            setSyncStatus('尚未同步');
          }
        }
      } else {
        // Response is not an object - error
        // Only show error if no data exists
        if (scheduleData.length === 0) {
          setError('無法載入班表資料，請檢查後端服務');
          setSyncStatus('尚未同步');
        }
        console.error('❌ Invalid response format:', typeof response, response);
      }
    } catch (err) {
      console.error('Error loading schedule:', err);
      
      // Only show error if we don't have existing schedule data
      // If schedule data already exists, don't overwrite it with error
      if (scheduleData.length === 0) {
        setError(err.response?.data?.error || '載入班表資料失敗');
        setSyncStatus('尚未同步');
      } else {
        // Keep existing data, just log the error
        console.warn('Error loading schedule but keeping existing data:', err);
      }
      
      // Try fallback endpoint only if no data exists
      if (scheduleData.length === 0) {
        try {
          const fallbackResponse = await employeeService.getMySchedule(selectedMonth);
          if (fallbackResponse && fallbackResponse.schedule && fallbackResponse.schedule.length > 0) {
            setScheduleData(fallbackResponse.schedule);
            setError(''); // Clear error if fallback worked
            setSyncStatus('已同步');
          }
        } catch (fallbackErr) {
          console.error('Fallback also failed:', fallbackErr);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const checkSyncStatus = async () => {
    try {
      // Get schedule definition ID from user's tenant
      const scheduleResponse = await employeeService.getSchedule(selectedMonth);
      if (scheduleResponse && scheduleResponse.last_synced_at) {
        setLastSyncedAt(scheduleResponse.last_synced_at);
        return;
      }
      
      // Fallback to sync status endpoint
      // Use environment variable - MUST be set
      const apiBaseURL = import.meta.env.VITE_API_BASE_URL;
      const response = await fetch(`${apiBaseURL}/admin/sync/status`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.last_synced_at) {
          setLastSyncedAt(data.last_synced_at);
        }
      }
    } catch (err) {
      console.error('Error checking sync status:', err);
    }
  };

  const formatSyncTime = (isoString) => {
    if (!isoString) return '尚未同步';
    
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now - date;
      const diffMins = Math.floor(diffMs / 60000);
      
      if (diffMins < 1) return '剛剛同步';
      if (diffMins < 60) return `${diffMins} 分鐘前同步`;
      
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours} 小時前同步`;
      
      const diffDays = Math.floor(diffHours / 24);
      return `${diffDays} 天前同步`;
    } catch (e) {
      return '同步時間未知';
    }
  };

  const parseScheduleData = (data, user) => {
    const schedules = [];
    console.log('📊 Parsing schedule data:', data);
    console.log('📊 User info:', { username: user?.username, full_name: user?.full_name, userID: user?.userID });
    
    // Handle data from employee dashboard service
    if (data && data.data && data.data.my_schedule) {
      const mySchedule = data.data.my_schedule;
      const rows = mySchedule.rows || [];
      const columns = mySchedule.columns || [];
      
      console.log('📊 Schedule rows:', rows);
      console.log('📊 Schedule columns:', columns);
      console.log('📊 Row count:', rows.length, 'Column count:', columns.length);
      
      if (rows.length > 0) {
        // Rows can be either arrays or objects (dictionaries)
        rows.forEach((row, rowIndex) => {
          let rowData = null;
          
          // Handle both array and object formats
          if (Array.isArray(row)) {
            // Row is an array: [employeeId, date1_value, date2_value, ...]
            rowData = row;
          } else if (typeof row === 'object' && row !== null) {
            // Row is an object/dict: {employee_id: 'xxx', '2024-01-01': 'D', ...}
            // Convert object to array format using column order
            rowData = [];
            if (columns.length > 0) {
              // First column is usually the employee identifier
              const firstColumn = columns[0];
              rowData.push(row[firstColumn] || row.employee_id || row.username || row.name || '');
              
              // Rest are dates
              for (let i = 1; i < columns.length; i++) {
                const colName = columns[i];
                rowData.push(row[colName] || null);
              }
            } else {
              // No columns, use object keys
              const keys = Object.keys(row);
              rowData = keys.map(key => row[key]);
            }
          }
          
          if (rowData && rowData.length > 1) {
            // Skip first column (employee identifier), process date columns
            for (let colIndex = 1; colIndex < rowData.length; colIndex++) {
              const cellValue = rowData[colIndex];
              const columnHeader = columns[colIndex] || columns[colIndex - 1] || '';
              
              if (cellValue && cellValue !== '' && cellValue !== null && cellValue !== undefined) {
                // Try to parse date from column header
                let dateStr = null;
                if (columnHeader) {
                  // Try multiple date formats
                  const dateMatch = columnHeader.toString().match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
                  if (dateMatch) {
                    dateStr = dateMatch[1].replace(/\//g, '-');
                  } else {
                    // Try to parse from different formats
                    const date = new Date(columnHeader);
                    if (!isNaN(date.getTime())) {
                      dateStr = date.toISOString().split('T')[0];
                    }
                  }
                }
                
                // If no date from header, use column index to estimate date
                if (!dateStr && colIndex > 0) {
                  const [year, month] = selectedMonth.split('-').map(Number);
                  const day = colIndex; // colIndex 1 = day 1, colIndex 2 = day 2, etc.
                  if (day <= 31) {
                    dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                  }
                }
                
                // CRITICAL: Keep the original cell value (e.g., "C 櫃台人力", "A 藥局人力")
                const cellStr = cellValue.toString().trim();
                const cellStrUpper = cellStr.toUpperCase();
                
                // Determine normalized shift type for time range calculation
                let shiftType = 'D'; // Default to day shift
                if (cellStrUpper === 'OFF' || cellStrUpper === '休' || cellStrUpper.includes('休假') || cellStr === '' || cellStr === 'NULL') {
                  shiftType = 'OFF';
                } else if (cellStrUpper === 'E' || cellStrUpper.includes('小夜') || cellStrUpper === 'EVENING') {
                  shiftType = 'E';
                } else if (cellStrUpper === 'N' || cellStrUpper.includes('大夜') || cellStrUpper === 'NIGHT') {
                  shiftType = 'N';
                } else if (cellStrUpper === 'D' || cellStrUpper.includes('白班') || cellStrUpper === 'DAY') {
                  shiftType = 'D';
                } else if (cellStrUpper.length === 1 && ['D', 'E', 'N'].includes(cellStrUpper)) {
                  shiftType = cellStrUpper;
                } else {
                  // For complex values like "C 櫃台人力", use 'D' as normalized type but keep original value
                  shiftType = 'D';
                }
                
                if (dateStr) {
                  schedules.push({
                    date: dateStr,
                    shift: cellStr,  // Store actual value from Excel
                    shiftType: shiftType,  // Normalized type for time range
                    timeRange: getTimePeriod(shiftType),
                  });
                  console.log(`✅ Added schedule: ${dateStr} -> "${cellStr}" (type: ${shiftType})`);
                } else {
                  console.warn(`⚠️ Skipped schedule entry: no date parsed for column "${columnHeader}", value: "${cellValue}"`);
                }
              }
            }
          }
        });
      }
    }
    
    // Fallback: try to parse from direct data structure
    if (schedules.length === 0 && data && data.data && data.data.my_schedule && data.data.my_schedule.rows) {
      const rows = data.data.my_schedule.rows;
      const columns = data.data.my_schedule.columns || [];
      // For employees, username IS the employee_id (e.g., E01, N01), so use it for matching
      const userIdentifier = (user?.username || user?.full_name || user?.userID || '').toLowerCase();
      const usernameUpper = user?.username ? user.username.toUpperCase() : '';
      
      console.log('📊 Trying fallback parsing, user:', userIdentifier);
      console.log('📊 Username (employee_id for employees):', usernameUpper);
      console.log('📊 Fallback - rows:', rows.length, 'columns:', columns.length);
      
      rows.forEach((row, rowIndex) => {
        let rowData = null;
        
        // Handle both formats
        if (Array.isArray(row)) {
          rowData = row;
        } else if (typeof row === 'object' && row !== null) {
          // Convert object to array using columns
          if (columns.length > 0) {
            rowData = columns.map(col => row[col] || row[col.toLowerCase()] || null);
          } else {
            // Use object keys
            const keys = Object.keys(row);
            rowData = keys.map(key => row[key]);
          }
        }
        
        if (rowData && rowData.length > 0) {
          // Check if this row belongs to the current user (first column should match)
          const firstColValue = rowData[0]?.toString().trim() || '';
          const firstColLower = firstColValue.toLowerCase();
          const firstColUpper = firstColValue.toUpperCase();
          
          // For employees, match by username (employee_id) - exact match or partial match
          const matchesUser = !userIdentifier || 
                             firstColLower === userIdentifier ||
                             firstColUpper === usernameUpper || // Exact match with username (employee_id)
                             firstColUpper.includes(usernameUpper) || // Partial match
                             usernameUpper.includes(firstColUpper) ||
                             firstColLower.includes(userIdentifier) || 
                             userIdentifier.includes(firstColLower) ||
                             rowIndex === 0 || // Include first row
                             rows.length === 1; // If only one row, use it
          
          console.log(`📊 Row ${rowIndex}: firstCol="${firstColValue}", userIdentifier="${userIdentifier}", username="${usernameUpper}", matches=${matchesUser}`);
          
          if (matchesUser || rows.length === 1) {
            // Process date columns (skip first column which is identifier)
            for (let colIndex = 1; colIndex < rowData.length; colIndex++) {
              const cellValue = rowData[colIndex];
              const columnHeader = columns[colIndex] || columns[colIndex - 1] || '';
              
              if (cellValue && cellValue !== '' && cellValue !== null && cellValue !== undefined) {
                // CRITICAL: Keep the original cell value (e.g., "C 櫃台人力", "A 藥局人力")
                const cellStr = String(cellValue).trim();
                if (cellStr === '' || cellStr === 'null' || cellStr === 'NULL') continue;
                
                const cellStrUpper = cellStr.toUpperCase();
                let shiftType = 'D';
                
                if (cellStrUpper === 'OFF' || cellStrUpper === '休' || cellStrUpper.includes('休假')) shiftType = 'OFF';
                else if (cellStrUpper === 'E' || cellStrUpper.includes('小夜') || cellStrUpper === 'EVENING') shiftType = 'E';
                else if (cellStrUpper === 'N' || cellStrUpper.includes('大夜') || cellStrUpper === 'NIGHT') shiftType = 'N';
                else if (cellStrUpper === 'D' || cellStrUpper.includes('白班') || cellStrUpper === 'DAY') shiftType = 'D';
                else if (cellStrUpper.length === 1 && ['D', 'E', 'N'].includes(cellStrUpper)) shiftType = cellStrUpper;
                
                // Parse date from column header or use index
                let dateStr = null;
                if (columnHeader) {
                  // Try multiple date formats
                  const dateMatch = columnHeader.toString().match(/(\d{4}[-/]\d{1,2}[-/]\d{1,2})/);
                  if (dateMatch) {
                    dateStr = dateMatch[1].replace(/\//g, '-');
                  } else {
                    // Try parsing as Date
                    const parsedDate = new Date(columnHeader);
                    if (!isNaN(parsedDate.getTime())) {
                      dateStr = parsedDate.toISOString().split('T')[0];
                    }
                  }
                }
                
                // If no date from header, use column index
                if (!dateStr && colIndex > 0) {
                  const [year, month] = selectedMonth.split('-').map(Number);
                  const day = colIndex; // colIndex 1 = day 1, etc.
                  if (day >= 1 && day <= 31) {
                    dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                  }
                }
                
                if (dateStr) {
                  schedules.push({
                    date: dateStr,
                    shift: cellStr,  // Store actual value from Excel
                    shiftType: shiftType,  // Normalized type for time range
                    timeRange: getTimePeriod(shiftType),
                  });
                  console.log(`✅ Fallback: Added schedule ${dateStr} -> "${cellStr}" (type: ${shiftType})`);
                }
              }
            }
          }
        }
      });
    }
    
    // If still no data, return empty array (don't generate fake data)
    // The UI will show "目前沒有班表資料"
    
    // Sort by date
    return schedules
      .filter(s => s.date)
      .map(schedule => ({
        ...schedule,
        date: schedule.date || new Date().toISOString().split('T')[0],
      }))
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  const monthOptions = generateMonthOptions();
  // For employees, username is the employee_id (e.g., E01, N01)
  // Display username instead of EMP-userID
  const employeeDisplay = user?.username || (user?.userID ? `EMP-${user.userID}` : 'EMP-000');
  const employeeName = user?.full_name || user?.username || '員工';

  return (
    <div className="bg-gray-100 p-4 md:p-8">
      {/* E.1: 頂部標題和月份選擇 */}
      <div className="flex flex-col md:flex-row justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">我的班表</h1>
          <p className="mt-1 text-sm text-gray-600">歡迎，{employeeName} ({employeeDisplay})</p>
        </div>
        <div className="mt-4 md:mt-0">
          <label htmlFor="month-select" className="block text-sm font-medium text-gray-700 mb-1">
            選擇月份
          </label>
          <select
            id="month-select"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            className="block w-full md:w-auto px-3 py-2 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          >
            {monthOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {/* Show sync status and last sync time */}
          <div className="mt-2 text-xs">
            {syncStatus === '已同步' ? (
              <span className="text-green-600 font-medium">✅ 已同步</span>
            ) : syncStatus === '同步中...' || isSyncing ? (
              <span className="text-blue-600 font-medium">🔄 同步中...</span>
            ) : (
              <span className="text-gray-500">⚠️ 尚未同步</span>
            )}
            {lastSyncedAt && syncStatus === '已同步' && (
              <span className="text-gray-500 ml-2">({formatSyncTime(lastSyncedAt)})</span>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {typeof error === 'string' ? error : (error?.message || error?.error || '發生錯誤')}
        </div>
      )}

      {/* E.2: 個人班表表格 */}
      <div className="bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="w-full overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  日期
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  星期
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  班別
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  時段
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {scheduleData.length === 0 ? (
                <tr>
                  <td colSpan="4" className="px-6 py-4 text-center text-sm text-gray-500">
                    目前沒有班表資料
                  </td>
                </tr>
              ) : (
                scheduleData.map((schedule, index) => (
                  <tr key={index}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {formatDate(schedule.date)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {getDayOfWeek(schedule.date)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getShiftBadge(schedule.shift, schedule.shiftType)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {getTimePeriod(schedule.shiftType, schedule.timeRange)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}