import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { authService } from '../../services/authService';

export default function Profile() {
  const { user: authUser, isAuthenticated } = useAuth();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchUserProfile = async () => {
      if (!isAuthenticated) {
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        const response = await authService.getCurrentUser();
        if (response.success && response.user) {
          setUser(response.user);
        } else {
          setError('無法載入用戶資料');
        }
      } catch (err) {
        console.error('Error fetching user profile:', err);
        setError('載入用戶資料時發生錯誤');
      } finally {
        setLoading(false);
      }
    };

    fetchUserProfile();
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#f9f9fa] flex items-center justify-center p-12">
        <div className="max-w-md w-full bg-white rounded-lg shadow-xl p-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-4 text-center">請先登入</h2>
          <p className="text-gray-600 text-center">您需要登入才能查看個人資料。</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f9f9fa] flex items-center justify-center p-12">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-pink-600"></div>
          <p className="mt-4 text-gray-600">載入中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#f9f9fa] flex items-center justify-center p-12">
        <div className="max-w-md w-full bg-white rounded-lg shadow-xl p-6">
          <div className="bg-red-50 border border-red-200 rounded-md p-4">
            <p className="text-red-800">{typeof error === 'string' ? error : (error?.message || error?.error || '發生錯誤')}</p>
          </div>
        </div>
      </div>
    );
  }

  const displayUser = user || authUser;

  const getRoleDisplayName = (role) => {
    const roleMap = {
      SysAdmin: '系統管理員',
      ClientAdmin: 'Admin',
      ScheduleManager: '排班主管',
      Employee: '員工',
      Department_Employee: '部門員工',
    };
    return roleMap[role] || role;
  };

  const getUserInitial = () => {
    const name = displayUser?.full_name || displayUser?.username || 'U';
    return name.charAt(0).toUpperCase();
  };

  return (
    <div className="min-h-screen bg-[#f9f9fa] flex items-center justify-center p-4 md:p-8">
      <div className="card user-card-full w-full max-w-4xl shadow-xl rounded-lg overflow-hidden bg-white">
        <div className="grid grid-cols-1 md:grid-cols-3">
          {/* Left Section - Profile Summary */}
          <div className="bg-c-lite-green text-white flex flex-col items-center justify-center p-8 relative">
            {/* Avatar with decorative bubbles */}
            <div className="relative mb-6">
              <div className="w-32 h-32 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center border-4 border-white/30 shadow-lg">
                <span className="text-5xl font-bold text-white">{getUserInitial()}</span>
              </div>
              {/* Decorative bubbles */}
              <div className="absolute -top-2 -right-2 w-6 h-6 bg-yellow-300 rounded-full opacity-80"></div>
              <div className="absolute -bottom-1 -left-1 w-4 h-4 bg-blue-300 rounded-full opacity-80"></div>
              <div className="absolute top-8 -left-3 w-3 h-3 bg-yellow-300 rounded-full opacity-60"></div>
              <div className="absolute bottom-6 -right-4 w-5 h-5 bg-blue-300 rounded-full opacity-60"></div>
            </div>
            
            {/* Name */}
            <h2 className="text-2xl font-bold mb-2 text-center">
              {displayUser?.full_name || displayUser?.username || 'User'}
            </h2>
            
            {/* Role */}
            <p className="text-lg text-white/90 text-center">
              {getRoleDisplayName(displayUser?.role) || 'User'}
            </p>
          </div>

          {/* Right Section - Detailed Information */}
          <div className="col-span-2 p-8">
            {/* Information Section */}
            <div className="mb-6">
              <h6 className="font-bold text-xl text-gray-800 mb-4">資訊</h6>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
                <div>
                  <p className="font-bold text-gray-700 mb-2">電子郵箱</p>
                  <p className="text-gray-600">{displayUser?.email || '未設定'}</p>
                </div>
              </div>
              <hr className="border-gray-200 my-4" />
            </div>

            {/* Additional Information Section */}
            <div className="mb-6">
              <h6 className="font-bold text-xl text-gray-800 mb-4">帳戶詳情</h6>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
                <div>
                  <p className="font-bold text-gray-700 mb-2">用戶名</p>
                  <p className="text-gray-600">{displayUser?.username || 'N/A'}</p>
                </div>
                {displayUser?.employee_id && (
                  <div>
                    <p className="font-bold text-gray-700 mb-2">員工編號</p>
                    <p className="text-gray-600">{displayUser.employee_id}</p>
                  </div>
                )}
                <div>
                  <p className="font-bold text-gray-700 mb-2">狀態</p>
                  <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
                    displayUser?.status === 'active' 
                      ? 'bg-green-100 text-green-800' 
                      : 'bg-gray-100 text-gray-800'
                  }`}>
                    {displayUser?.status === 'active' ? '啟用' : displayUser?.status || '未知'}
                  </span>
                </div>
                <div>
                  <p className="font-bold text-gray-700 mb-2">用戶 ID</p>
                  <p className="text-gray-600 text-sm font-mono">{displayUser?.userID || 'N/A'}</p>
                </div>
              </div>
              <hr className="border-gray-200 my-4" />
            </div>

            {/* Account Activity Section */}
            {displayUser?.created_at && (
              <div className="mb-6">
                <h6 className="font-bold text-xl text-gray-800 mb-4">活動</h6>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <p className="font-bold text-gray-700 mb-2">最近</p>
                    <p className="text-gray-600 text-sm">
                      {new Date(displayUser.created_at).toLocaleDateString('zh-TW')}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .bg-c-lite-green {
          background: linear-gradient(to bottom, #ee5a6f, #f29263);
        }
      `}</style>
    </div>
  );
}

