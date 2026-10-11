import axios from 'axios';

const API_BASE_URL = '/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor: Attach JWT Token & Multi-Tenant X-School-ID Header
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('schoolbridge_access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    const schoolId = localStorage.getItem('schoolbridge_active_school_id');
    if (schoolId) {
      config.headers['X-School-ID'] = schoolId;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Silent Token Refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('schoolbridge_refresh_token');

      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE_URL}/auth/token/refresh/`, {
            refresh: refreshToken,
          });
          const { access } = res.data;
          localStorage.setItem('schoolbridge_access_token', access);
          originalRequest.headers.Authorization = `Bearer ${access}`;
          return apiClient(originalRequest);
        } catch (refreshError) {
          localStorage.removeItem('schoolbridge_access_token');
          localStorage.removeItem('schoolbridge_refresh_token');
          localStorage.removeItem('schoolbridge_user_data');
          window.location.href = '/auth/login';
          return Promise.reject(refreshError);
        }
      }
    }

    return Promise.reject(error);
  }
);

