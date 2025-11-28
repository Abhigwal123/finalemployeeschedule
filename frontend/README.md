# Role-Based Dashboard Frontend

A complete React frontend structure for a role-based dashboard system supporting four roles:
- **SysAdmin**: System Administrator
- **ClientAdmin**: Client Administrator  
- **ScheduleManager**: Schedule Manager
- **Employee**: Employee

## 🏗️ Project Structure

```
frontend/
├── src/
│   ├── App.js                 # Main app component with routing setup
│   ├── index.js               # Entry point
│   ├── index.css              # Global styles with TailwindCSS
│   │
│   ├── routes/                # Routing configuration
│   │   ├── index.js           # Main routing setup
│   │   ├── ProtectedRoute.js  # Route protection wrapper
│   │   ├── SysAdminRoutes.js
│   │   ├── ClientAdminRoutes.js
│   │   ├── ScheduleManagerRoutes.js
│   │   └── EmployeeRoutes.js
│   │
│   ├── layouts/               # Layout components
│   │   ├── MainFrame.js       # Base layout with sidebar and top nav
│   │   ├── SysAdminLayout.js
│   │   ├── ClientAdminLayout.js
│   │   ├── ScheduleManagerLayout.js
│   │   └── EmployeeLayout.js
│   │
│   ├── pages/                 # Page components
│   │   ├── Auth/
│   │   │   ├── Login.js
│   │   │   └── Logout.js
│   │   ├── SysAdmin/
│   │   ├── ClientAdmin/
│   │   ├── ScheduleManager/
│   │   └── Employee/
│   │
│   ├── components/            # Reusable components
│   │   ├── Sidebar.js
│   │   ├── TopNav.js
│   │   └── LoadingSpinner.js
│   │
│   ├── context/               # React Context providers
│   │   ├── AuthContext.js
│   │   └── RoleContext.js
│   │
│   └── utils/                 # Utility functions
│       ├── roles.js
│       ├── constants.js
│       └── helpers.js
│
├── package.json
├── vite.config.js
├── tailwind.config.js
└── postcss.config.js
```

## 🚀 Getting Started

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
npm run dev
```

The app will start on `http://localhost:5173` (default Vite port).

### Build

```bash
npm run build
```

## 📍 Routes

### Authentication
- `/login` - Login page (mock authentication with role selection)
- `/logout` - Logout handler

### SysAdmin Routes (`/sysadmin/*`)
- `/sysadmin/dashboard` - Dashboard
- `/sysadmin/org` - Organization Maintenance
- `/sysadmin/schedule` - Schedule List Maintenance

### ClientAdmin Routes (`/client-admin/*`)
- `/client-admin/dashboard` - Dashboard
- `/client-admin/department` - Department Management
- `/client-admin/users` - User Account Management
- `/client-admin/permissions` - Permission Maintenance

### ScheduleManager Routes (`/schedule-manager/*`)
- `/schedule-manager/scheduling` - Scheduling
- `/schedule-manager/export` - Export

### Employee Routes (`/employee/*`)
- `/employee/my` - My Dashboard

## 🎨 Features

- **React Router v6** for navigation
- **TailwindCSS** for styling
- **Role-based access control** with protected routes
- **Context API** for authentication and role management
- **Modular folder structure** for scalability
- **Responsive sidebar navigation** with role-specific menus

## 🔐 Authentication

The frontend is fully integrated with the Flask backend API:

1. **Login**: Users authenticate via `/api/v1/auth/login` with username and password
2. **Token Storage**: JWT tokens are stored in localStorage and automatically included in API requests
3. **Auto-redirect**: After login, users are redirected to their role-specific dashboard
4. **Token Refresh**: The app automatically verifies token validity on mount

## 🔌 Backend Integration

The frontend connects to the Flask backend using `VITE_API_BASE_URL` environment variable (set in `.env` or build args).

### API Endpoints Used

- **Authentication**: `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/me`
- **Tenants**: `/api/v1/tenants` (CRUD)
- **Users**: `/api/v1/users` (CRUD)
- **Departments**: `/api/v1/departments` (CRUD)
- **Schedules**: `/api/v1/schedule-definitions`, `/api/v1/schedule-permissions`, `/api/v1/schedule-job-logs`

## 🎯 Features Implemented

### SysAdmin
- ✅ Dashboard with system statistics
- ✅ Tenant (Organization) Management (CRUD)
- ✅ Schedule Definition Management

### ClientAdmin
- ✅ Dashboard with tenant overview
- ✅ Department Management (CRUD)
- ✅ User Account Management (CRUD)
- ✅ Schedule Permission Management

### ScheduleManager
- ✅ Scheduling Dashboard
- ✅ Run Schedule Jobs
- ✅ Export Completed Jobs
- ✅ Job Logs Viewer with filtering

### Employee
- ✅ My Schedule Dashboard
- ✅ View upcoming shifts

## 📝 Notes

- All pages are fully connected to the backend API
- Reusable components: DataTable, Modal, FormInput, Button, Pagination
- Error handling and loading states included
- Protected routes with role-based access control
- Responsive design with TailwindCSS

