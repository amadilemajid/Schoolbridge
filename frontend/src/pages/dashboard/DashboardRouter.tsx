import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { ExecutiveDashboardPage } from './ExecutiveDashboardPage';
import { TeacherDashboardPage } from './TeacherDashboardPage';
import { BursarDashboardPage } from './BursarDashboardPage';

export const DashboardRouter: React.FC = () => {
  const { user } = useAuth();

  // Route teachers to dedicated Teacher Workspace Dashboard
  if (user?.role === 'teacher') {
    return <TeacherDashboardPage />;
  }

  // Route bursars to dedicated Bursar Operations & Financial Dashboard
  if (user?.role === 'bursar') {
    return <BursarDashboardPage />;
  }

  // Directors, Super Admins, and School Admins view Executive Operational Dashboard
  return <ExecutiveDashboardPage />;
};

export default DashboardRouter;
