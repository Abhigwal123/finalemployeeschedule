import { useState, useEffect } from 'react';
import { tenantService } from '../../services/tenantService';
import LoadingSpinner from '../../components/LoadingSpinner';
import Modal from '../../components/Modal';
import Button from '../../components/Button';

const getStatusBadge = (isActive) => {
  if (isActive) {
    return (
      <span className="px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
        啟用
      </span>
    );
  }
  return (
    <span className="px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">
      停用
    </span>
  );
};

export default function OrganizationMaintenance() {
  const [tenants, setTenants] = useState([]);
  const [filteredTenants, setFilteredTenants] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingTenant, setEditingTenant] = useState(null);
  const [formData, setFormData] = useState({
    tenantCode: '',
    tenantName: '',
    contactPerson: '',
    gmail: '',
    contactPhone: '',
    startDate: '',
    category: '',
    is_active: true,
  });
  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  useEffect(() => {
    loadTenants();
  }, []);

  useEffect(() => {
    // Filter tenants based on search query
    if (searchQuery.trim() === '') {
      setFilteredTenants(tenants);
    } else {
      const filtered = tenants.filter(tenant =>
        tenant.tenantName?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        tenant.tenantCode?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        tenant.gmail?.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredTenants(filtered);
    }
  }, [searchQuery, tenants]);

  const loadTenants = async () => {
    try {
      setLoading(true);
      setError('');
      
      console.log('[TRACE] Frontend: Loading tenants data');
      // Use environment variable - MUST be set
      const apiBaseURL = import.meta.env.VITE_API_BASE_URL;
      console.log('[TRACE] Frontend: API base URL:', apiBaseURL);
      
      const response = await tenantService.getAll(1, 100);
      console.log('[TRACE] Frontend: Tenants response type:', typeof response);
      console.log('[TRACE] Frontend: Tenants response:', response);
      console.log('[TRACE] Frontend: Response keys:', response ? Object.keys(response) : 'null');
      
      // Backend returns: {success: true, data: [...], pagination: {...}}
      // tenantService.getAll() returns response.data which is the JSON body
      // So response is: {success: true, data: [...], pagination: {...}}
      const tenantsData = (response && response.data) ? response.data : (Array.isArray(response) ? response : []);
      console.log('[TRACE] Frontend: Tenants count:', tenantsData.length);
      
      if (tenantsData.length > 0) {
        console.log('[TRACE] Frontend: First tenant:', tenantsData[0]);
      }
      
      setTenants(tenantsData);
      setFilteredTenants(tenantsData);
    } catch (err) {
      console.error('[TRACE] Frontend: Error loading tenants:', err);
      console.error('[TRACE] Frontend: Error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
        config: err.config?.url
      });
      
      let errorMsg = '載入客戶資料失敗';
      if (err.response?.status === 403) {
        errorMsg = '無權限存取客戶資料，請確認您的角色權限';
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

  const handleCreate = () => {
    setEditingTenant(null);
    setFormData({
      tenantCode: '',
      tenantName: '',
      contactPerson: '',
      gmail: '',
      contactPhone: '',
      startDate: '',
      category: '',
      is_active: true,
    });
    setIsModalOpen(true);
  };

  const handleEdit = (tenant) => {
    setEditingTenant(tenant);
    // Extract tenant code from tenantID or use first part
    const tenantCode = tenant.tenantCode || 
                      tenant.tenantID?.substring(0, 10) || 
                      tenant.tenantID?.replace(/-/g, '').substring(0, 10)?.toUpperCase() || 
                      '';
    
    setFormData({
      tenantCode,
      tenantName: tenant.tenantName || '',
      contactPerson: tenant.contactPerson || tenant.contact_person || tenant.metadata?.contactPerson || '',
      gmail: tenant.gmail || tenant.email || tenant.metadata?.gmail || '',
      contactPhone: tenant.contactPhone || tenant.contact_phone || tenant.metadata?.contactPhone || '',
      startDate: tenant.startDate || tenant.start_date || tenant.created_at?.split('T')[0] || '',
      category: tenant.category || tenant.tenantCategory || tenant.metadata?.category || '',
      is_active: tenant.is_active !== undefined ? tenant.is_active : true,
    });
    setIsModalOpen(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    
    try {
      setSaving(true);
      setError('');
      setSuccessMessage('');

      const saveData = {
        tenantName: formData.tenantName,
        is_active: formData.is_active,
        // Store additional fields in metadata if backend supports it
        metadata: {
          tenantCode: formData.tenantCode,
          contactPerson: formData.contactPerson,
          gmail: formData.gmail,
          contactPhone: formData.contactPhone,
          startDate: formData.startDate,
          category: formData.category,
        },
        // Also set direct fields for compatibility
        email: formData.gmail,
        contact_person: formData.contactPerson,
        contact_phone: formData.contactPhone,
        start_date: formData.startDate,
        tenantCode: formData.tenantCode,
        gmail: formData.gmail,
        contactPerson: formData.contactPerson,
        contactPhone: formData.contactPhone,
        category: formData.category,
      };

      if (editingTenant) {
        await tenantService.update(editingTenant.tenantID, saveData);
        setSuccessMessage('客戶機構已成功更新');
      } else {
        await tenantService.create(saveData);
        setSuccessMessage('客戶機構已成功新增');
      }

      setIsModalOpen(false);
      await loadTenants();
      
      // Show success message briefly
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      setError(err.response?.data?.error || '儲存客戶機構失敗');
      console.error('Error saving tenant:', err);
    } finally {
      setSaving(false);
    }
  };

  if (loading && tenants.length === 0) {
    return <LoadingSpinner />;
  }

  return (
    <div className="bg-gray-100 p-4 md:p-8">
      {/* B2.1: 頂部操作列 */}
      <div className="flex flex-col md:flex-row justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-900">客戶機構維護</h1>
        <div className="flex space-x-2 mt-4 md:mt-0">
          <input
            type="text"
            placeholder="搜尋客戶名稱..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
          />
          <button
            onClick={handleCreate}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none"
          >
            <svg className="h-5 w-5 mr-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
            </svg>
            新增客戶
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {typeof error === 'string' ? error : (error?.message || error?.error || String(error) || '發生錯誤')}
        </div>
      )}

      {successMessage && (
        <div className="mb-4 bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded">
          {successMessage}
        </div>
      )}

      {/* B2.2: 客戶列表 (Table) */}
      <div className="bg-white rounded-xl shadow-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  客戶機構碼
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  客戶名稱
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  聯繫窗口
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  gmail郵箱
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  狀態
                </th>
                <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {filteredTenants.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-6 py-4 text-center text-sm text-gray-500">
                    目前無客戶機構資料
                  </td>
                </tr>
              ) : (
                filteredTenants.map((tenant) => (
                  <tr key={tenant.tenantID} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                      {tenant.tenantCode || tenant.metadata?.tenantCode || tenant.tenantID?.substring(0, 10) || 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {tenant.tenantName}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                      {tenant.contactPerson || tenant.contact_person || tenant.metadata?.contactPerson || '--'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                      {tenant.gmail || tenant.email || tenant.metadata?.gmail || '--'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {getStatusBadge(tenant.is_active)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-center text-sm font-medium">
                      <button
                        onClick={() => handleEdit(tenant)}
                        className="edit-tenant-btn text-indigo-600 hover:text-indigo-900"
                      >
                        編輯
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* B2.3: 新增/編輯 Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingTenant(null);
        }}
        title=""
        size="lg"
      >
        <form id="tenant-form" onSubmit={handleSave}>
          {/* Modal 標題 */}
          <div className="flex justify-between items-center p-5 border-b rounded-t">
            <h3 className="text-xl font-semibold text-gray-900">
              {editingTenant ? '編輯客戶機構' : '新增客戶機構'}
            </h3>
            <button
              type="button"
              onClick={() => {
                setIsModalOpen(false);
                setEditingTenant(null);
              }}
              className="close-tenant-modal-btn text-gray-400 bg-transparent hover:bg-gray-200 hover:text-gray-900 rounded-lg text-sm p-1.5 ml-auto inline-flex items-center"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>

          {/* Modal 表單內容 */}
          <div className="p-6 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="tenant-id" className="block mb-2 text-sm font-medium text-gray-900">
                  客戶機構碼*
                </label>
                <input
                  type="text"
                  id="tenant-id"
                  value={formData.tenantCode}
                  onChange={(e) => setFormData({ ...formData, tenantCode: e.target.value })}
                  className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5"
                  placeholder="例如: CLARIN-TC"
                  required
                  readOnly={!!editingTenant}
                />
              </div>
              <div>
                <label htmlFor="tenant-name" className="block mb-2 text-sm font-medium text-gray-900">
                  客戶名稱*
                </label>
                <input
                  type="text"
                  id="tenant-name"
                  value={formData.tenantName}
                  onChange={(e) => setFormData({ ...formData, tenantName: e.target.value })}
                  className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5"
                  placeholder="例如: 澄清醫院中港院區"
                  required
                />
              </div>
              <div>
                <label htmlFor="tenant-gmail" className="block mb-2 text-sm font-medium text-gray-900">
                  gmail郵箱*
                </label>
                <input
                  type="email"
                  id="tenant-gmail"
                  value={formData.gmail}
                  onChange={(e) => setFormData({ ...formData, gmail: e.target.value })}
                  className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5"
                  placeholder="用於 Google Sheet 授權"
                  required
                />
              </div>
              <div>
                <label htmlFor="tenant-contact-person" className="block mb-2 text-sm font-medium text-gray-900">
                  聯繫窗口
                </label>
                <input
                  type="text"
                  id="tenant-contact-person"
                  value={formData.contactPerson}
                  onChange={(e) => setFormData({ ...formData, contactPerson: e.target.value })}
                  className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5"
                  placeholder="例如: 王經理"
                />
              </div>
              <div>
                <label htmlFor="tenant-contact-phone" className="block mb-2 text-sm font-medium text-gray-900">
                  連絡電話
                </label>
                <input
                  type="tel"
                  id="tenant-contact-phone"
                  value={formData.contactPhone}
                  onChange={(e) => setFormData({ ...formData, contactPhone: e.target.value })}
                  className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5"
                />
              </div>
              <div>
                <label htmlFor="tenant-start-date" className="block mb-2 text-sm font-medium text-gray-900">
                  啟用日期
                </label>
                <input
                  type="date"
                  id="tenant-start-date"
                  value={formData.startDate}
                  onChange={(e) => setFormData({ ...formData, startDate: e.target.value })}
                  className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5"
                />
              </div>
              <div className="md:col-span-2">
                <label htmlFor="tenant-category" className="block mb-2 text-sm font-medium text-gray-900">
                  客戶分類
                </label>
                <input
                  type="text"
                  id="tenant-category"
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  className="bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-indigo-500 focus:border-indigo-500 block w-full p-2.5"
                  placeholder="例如: 醫療機構"
                />
              </div>
            </div>
          </div>

          {/* Modal 尾部 (按鈕) */}
          <div className="flex items-center p-6 space-x-2 border-t border-gray-200 rounded-b">
            <Button type="submit" loading={saving}>
              儲存
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setIsModalOpen(false);
                setEditingTenant(null);
              }}
            >
              取消
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
