import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/layout/ProtectedRoute';
import { MainLayout } from './components/layout/MainLayout';
import { LoginPage } from './pages/auth/LoginPage';
import { PasswordResetPage } from './pages/auth/PasswordResetPage';
import { DashboardRouter } from './pages/dashboard/DashboardRouter';
import { StudentDirectoryPage } from './pages/students/StudentDirectoryPage';
import { AttendanceRegisterPage } from './pages/attendance/AttendanceRegisterPage';
import { ViewClassAttendancesPage } from './pages/attendance/ViewClassAttendancesPage';
import { ViewStudentAttendancesPage } from './pages/attendance/ViewStudentAttendancesPage';
import { MarksEntryPage } from './pages/academics/MarksEntryPage';
import { TimetablePage } from './pages/academics/TimetablePage';
import { FeeManagementPage } from './pages/finance/FeeManagementPage';
import { MoMoReconciliationPage } from './pages/finance/MoMoReconciliationPage';
import { CampaignHubPage } from './pages/communications/CampaignHubPage';
import { ReportsPage } from './pages/reports/ReportsPage';
import { SettingsPage } from './pages/settings/SettingsPage';
import { PublicPaymentPage } from './pages/finance/PublicPaymentPage';
import { SearchPaletteModal } from './components/navigation/SearchPaletteModal';
import { RbacGate } from './components/auth/RbacGate';
import { UnauthorizedPage } from './pages/auth/UnauthorizedPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,          // 30 s — fresh enough to avoid flicker, always re-fetches on mount/focus
      gcTime: 1000 * 60 * 10,    // keep in memory for 10 min but re-fetch when stale
      refetchOnWindowFocus: true,  // re-fetch when user returns to tab
      refetchOnMount: true,        // re-fetch whenever component mounts (page navigation)
      retry: 1,
    },
  },
});

export function App() {
  const [searchModalOpen, setSearchModalOpen] = useState(false);

  useEffect(() => {
    const handleOpenSearch = () => setSearchModalOpen(true);
    window.addEventListener('open-search-modal', handleOpenSearch);
    return () => window.removeEventListener('open-search-modal', handleOpenSearch);
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Router>
          <Routes>
            {/* Public Auth & Checkout Routes */}
            <Route path="/auth/login" element={<LoginPage />} />
            <Route path="/auth/reset-password" element={<PasswordResetPage />} />
            <Route path="/auth/forgot-password" element={<PasswordResetPage />} />
            <Route path="/reset-password" element={<PasswordResetPage />} />
            <Route path="/pay/:token" element={<PublicPaymentPage />} />

            {/* Protected App Routes */}
            <Route element={<ProtectedRoute />}>
              <Route element={<MainLayout />}>
                <Route path="/" element={<DashboardRouter />} />
                <Route path="/students" element={<StudentDirectoryPage />} />
                <Route path="/finance" element={
                  <RbacGate
                    permission="view:finance"
                    fallback={<UnauthorizedPage requiredPermission="view:finance" />}
                  >
                    <FeeManagementPage />
                  </RbacGate>
                } />
                <Route path="/finance/reconciliation" element={
                  <RbacGate
                    permission="finance:reconcile"
                    fallback={<UnauthorizedPage requiredPermission="finance:reconcile" backTo="/finance" />}
                  >
                    <MoMoReconciliationPage />
                  </RbacGate>
                } />
                <Route path="/academics" element={<MarksEntryPage />} />
                <Route path="/academics/timetable" element={<TimetablePage />} />
                <Route path="/timetable" element={<Navigate to="/academics/timetable" replace />} />
                <Route path="/attendance" element={<AttendanceRegisterPage />} />
                <Route path="/attendance/class" element={<ViewClassAttendancesPage />} />
                <Route path="/attendance/student" element={<ViewStudentAttendancesPage />} />
                <Route path="/communications" element={
                  <RbacGate
                    permission="view:communications"
                    fallback={<UnauthorizedPage requiredPermission="view:communications" />}
                  >
                    <CampaignHubPage />
                  </RbacGate>
                } />
                <Route path="/messaging" element={<Navigate to="/communications" replace />} />
                <Route path="/reports" element={
                  <RbacGate
                    permission="view:reports"
                    fallback={<UnauthorizedPage requiredPermission="view:reports" />}
                  >
                    <ReportsPage />
                  </RbacGate>
                } />
                <Route path="/settings" element={
                  <RbacGate
                    permission="view:settings"
                    fallback={<UnauthorizedPage requiredPermission="view:settings" />}
                  >
                    <SettingsPage />
                  </RbacGate>
                } />
              </Route>
            </Route>

            {/* Catch-all redirect */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

          {/* Global Search Command Palette Modal */}
          <SearchPaletteModal
            isOpen={searchModalOpen}
            onClose={() => setSearchModalOpen(false)}
          />
        </Router>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
