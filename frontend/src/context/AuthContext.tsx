import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiClient } from '../api/client';

export interface User {
  id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: 'super_admin' | 'director' | 'bursar' | 'teacher' | 'school_admin' | 'system_admin';
  phone_number?: string;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  logo?: string;
}

interface AuthContextType {
  user: User | null;
  tenant: Tenant | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isDemoMode: boolean;
  login: (usernameOrPhone: string, password: string) => Promise<void>;
  logout: () => void;
  setTenant: (tenant: Tenant) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const USER_STORAGE_KEY = 'schoolbridge_user_data';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [tenant, setTenantState] = useState<Tenant | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isDemoMode] = useState<boolean>(false);

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('schoolbridge_access_token');

      if (!token) {
        // No token — redirect to login (handled by ProtectedRoute)
        setIsLoading(false);
        return;
      }

      // Validate token against live backend
      try {
        const res = await apiClient.get('/auth/me/');
        const userData: User & { school?: string | number; school_name?: string } = res.data;
        setUser(userData);
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData));

        if (userData.school && userData.school_name) {
          const activeTenant: Tenant = {
            id: String(userData.school),
            name: userData.school_name,
            slug: userData.school_name.toLowerCase().replace(/\s+/g, '-'),
          };
          setTenantState(activeTenant);
          localStorage.setItem('schoolbridge_active_school_id', activeTenant.id);
          localStorage.setItem('schoolbridge_tenant_data', JSON.stringify(activeTenant));
        } else {
          const savedTenant = localStorage.getItem('schoolbridge_tenant_data');
          if (savedTenant) {
            setTenantState(JSON.parse(savedTenant));
          }
        }
      } catch {
        // Token invalid or expired — clear storage and send to login
        localStorage.removeItem('schoolbridge_access_token');
        localStorage.removeItem('schoolbridge_refresh_token');
        localStorage.removeItem(USER_STORAGE_KEY);
      }
      setIsLoading(false);
    };

    initAuth();
  }, []);

  const login = async (usernameOrPhone: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await apiClient.post('/auth/token/', {
        email: usernameOrPhone,
        password,
      });

      const { access, refresh, user: userData, school: schoolData } = res.data;
      localStorage.setItem('schoolbridge_access_token', access);
      localStorage.setItem('schoolbridge_refresh_token', refresh);

      if (userData) {
        setUser(userData);
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData));
      }
      if (schoolData) {
        setTenantState(schoolData);
        localStorage.setItem('schoolbridge_active_school_id', schoolData.id);
        localStorage.setItem('schoolbridge_tenant_data', JSON.stringify(schoolData));
      }
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem('schoolbridge_access_token');
    localStorage.removeItem('schoolbridge_refresh_token');
    localStorage.removeItem('schoolbridge_active_school_id');
    localStorage.removeItem('schoolbridge_tenant_data');
    localStorage.removeItem(USER_STORAGE_KEY);
    setUser(null);
    setTenantState(null);
    window.location.href = '/auth/login';
  };

  const setTenant = (newTenant: Tenant) => {
    setTenantState(newTenant);
    localStorage.setItem('schoolbridge_active_school_id', newTenant.id);
    localStorage.setItem('schoolbridge_tenant_data', JSON.stringify(newTenant));
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        tenant,
        isAuthenticated: !!user,
        isLoading,
        isDemoMode,
        login,
        logout,
        setTenant,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
