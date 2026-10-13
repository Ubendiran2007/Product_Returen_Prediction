import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor for error formatting
apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'An unexpected error occurred while communicating with the backend.';
    console.error(`[API Error] ${error.config?.url}:`, message);
    return Promise.reject(new Error(message));
  }
);

export const api = {
  // Health & System
  getHealth: () => apiClient.get('/health'),
  getSettings: () => apiClient.get('/settings'),
  getFilters: () => apiClient.get('/filters'),

  // Datasets & Preprocessing
  getDatasets: () => apiClient.get('/datasets'),
  getDatasetProfile: () => apiClient.get('/datasets/profile'),
  cleanDatasets: () => apiClient.post('/datasets/clean'),
  getDataQuality: () => apiClient.get('/data-quality'),
  getDataExplorer: (params) => apiClient.get('/data-explorer', { params }),

  // Analytics Endpoints
  getOverview: (params) => apiClient.get('/overview', { params }),
  getReturnsAnalytics: (params) => apiClient.get('/analytics/returns', { params }),
  getCategoryAnalytics: (params) => apiClient.get('/analytics/categories', { params }),
  getDiscountAnalytics: (params) => apiClient.get('/analytics/discounts', { params }),
  getDeliveryInsights: (params) => apiClient.get('/analytics/delivery', { params }),
  getCustomerAnalytics: (params) => apiClient.get('/analytics/customers', { params }),
  getSellerAnalytics: (params) => apiClient.get('/analytics/sellers', { params }),

  // Feature Engineering & ML Models
  generateFeatures: () => apiClient.post('/features/generate'),
  getFeatures: () => apiClient.get('/features'),
  trainModels: () => apiClient.post('/models/train'),
  getModelResults: () => apiClient.get('/models/results'),
  getRiskScores: (limit = 20) => apiClient.get('/models/risk-scores', { params: { limit } }),

  // Recommendations
  getRecommendations: () => apiClient.get('/recommendations'),

  // Reports
  generateExcelReport: () =>
    axios.post(`${API_BASE}/reports/excel`, {}, { responseType: 'blob' }),
  generatePdfReport: () =>
    axios.post(`${API_BASE}/reports/pdf`, {}, { responseType: 'blob' }),
  exportCsv: (table) =>
    axios.get(`${API_BASE}/reports/csv/${table}`, { responseType: 'blob' }),
};

export default api;
