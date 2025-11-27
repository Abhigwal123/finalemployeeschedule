import { Link, useLocation } from 'react-router-dom';
import { ROUTES } from '../utils/constants';
import { useAuth } from '../context/AuthContext';
import { useState } from 'react';

const getNavItemsForRole = (role) => {
  switch (role) {
    case 'SysAdmin':
      return [
        { section: '系統管理', items: [
          { path: ROUTES.SYSADMIN_DASHBOARD, label: '儀表板', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
          { path: ROUTES.SYSADMIN_ORG, label: '客戶機構維護', icon: 'M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z' },
          { path: ROUTES.SYSADMIN_SCHEDULE, label: '班表清單維護', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01' },
          { path: ROUTES.REGISTER, label: '註冊使用者', icon: 'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z' },
        ]}
      ];
    case 'ClientAdmin':
      return [
        { section: 'Admin', items: [
          { path: ROUTES.CLIENTADMIN_DASHBOARD, label: '儀表板', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
          { path: ROUTES.CLIENTADMIN_USERS, label: '使用者帳號管理', icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z' },
          { path: ROUTES.CLIENTADMIN_DEPARTMENT, label: '部門管理', icon: 'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4' },
          { path: ROUTES.CLIENTADMIN_PERMISSIONS, label: '使用者帳號排班權限維護', icon: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z' },
          { path: ROUTES.REGISTER, label: '註冊使用者', icon: 'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z' },
        ]}
      ];
    case 'ScheduleManager':
      return [
        { section: '排班主管', items: [
          { path: ROUTES.SCHEDULEMANAGER_SCHEDULING, label: '排班作業', icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z' },
          { path: ROUTES.SCHEDULEMANAGER_EXPORT, label: '匯出', icon: 'M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
          { path: ROUTES.SCHEDULEMANAGER_LOGS, label: '執行日誌', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
          { path: ROUTES.REGISTER, label: '註冊使用者', icon: 'M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z' },
        ]}
      ];
    case 'Employee':
      return [
        { section: '員工', items: [
          { path: ROUTES.EMPLOYEE_MY, label: '我的班表', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
        ]}
      ];
    default:
      return [];
  }
};

export default function Sidebar({ role }) {
  const location = useLocation();
  const { user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navItems = getNavItemsForRole(role);

  const SidebarIcon = ({ iconPath }) => (
    <svg className="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={iconPath} />
    </svg>
  );

  return (
    <>
      {/* Mobile Overlay */}
      <div
        className={`fixed inset-0 z-20 bg-black bg-opacity-50 transition-opacity duration-300 md:hidden ${
          sidebarOpen ? 'opacity-100' : 'opacity-0 hidden'
        }`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* Sidebar */}
      <div
        id="sidebar"
        className={`fixed inset-y-0 left-0 z-30 w-64 bg-gray-900 text-white transform transition-transform duration-300 overflow-y-auto ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Logo */}
        <div className="flex items-center justify-center h-16 px-6 bg-gray-800">
          <span className="text-2xl font-bold text-white">自動排班系統</span>
        </div>

        {/* Navigation */}
        <nav className="py-6 px-4">
          {navItems.map((section, sectionIdx) => (
            <div key={sectionIdx}>
              <h3 className="px-3 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                {section.section}
              </h3>
              {section.items.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={() => setSidebarOpen(false)}
                    className={`flex items-center px-3 py-3 text-sm font-medium rounded-md transition-colors ${
                      isActive
                        ? 'bg-gray-700 text-white'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                    }`}
                  >
                    <span className="mr-3">
                      <SidebarIcon iconPath={item.icon} />
                    </span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </div>

      {/* Mobile Menu Button */}
      <button
        id="sidebar-open-btn"
        className="fixed top-4 left-4 z-40 text-gray-500 focus:outline-none md:hidden bg-white p-2 rounded-md shadow"
        onClick={() => setSidebarOpen(true)}
      >
        <svg className="h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
    </>
  );
}