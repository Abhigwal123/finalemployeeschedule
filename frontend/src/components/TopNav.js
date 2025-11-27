import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../utils/constants';

const getRoleDisplayName = (role) => {
  const roleMap = {
    SysAdmin: '系統管理員',
    ClientAdmin: 'Admin',
    ScheduleManager: '排班主管',
    Employee: '員工',
  };
  return roleMap[role] || role;
};

export default function TopNav({ title }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate(ROUTES.LOGIN);
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('#user-menu-btn') && !event.target.closest('#user-menu-dropdown')) {
        setUserMenuOpen(false);
      }
    };

    if (userMenuOpen) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [userMenuOpen]);

  return (
    <header className="sticky top-0 z-10 flex items-center justify-between h-16 px-6 bg-white shadow">
      {/* 左側空白 */}
      <div className="flex-1"></div>

      {/* 右側：使用者選單 */}
      <div className="relative">
        <button
          id="user-menu-btn"
          onClick={() => setUserMenuOpen(!userMenuOpen)}
          className="flex items-center text-sm rounded-full focus:outline-none"
        >
          <div className="mr-3 text-right">
            <div className="text-gray-900 font-medium">
              {user?.full_name || user?.username || 'User'}
            </div>
            <div className="text-xs text-gray-500">
              {getRoleDisplayName(user?.role)}
            </div>
          </div>
          <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center">
            <span className="text-gray-600 text-sm font-medium">
              {(user?.full_name || user?.username || 'U').charAt(0).toUpperCase()}
            </span>
          </div>
        </button>

        {/* 使用者下拉選單 */}
        <div
          id="user-menu-dropdown"
          className={`absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg py-1 ${
            userMenuOpen ? 'block' : 'hidden'
          }`}
        >
          <a
            href="#"
            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            onClick={(e) => {
              e.preventDefault();
              setUserMenuOpen(false);
              navigate(ROUTES.PROFILE);
            }}
          >
            個人資料
          </a>
          <a
            href="#"
            className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            onClick={(e) => {
              e.preventDefault();
              handleLogout();
            }}
          >
            登出
          </a>
        </div>
      </div>
    </header>
  );
}
