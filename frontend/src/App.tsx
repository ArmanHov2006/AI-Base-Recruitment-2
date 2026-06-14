import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, theme, Spin } from 'antd';
import { AuthProvider } from './context/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import AppLayout from './components/Layout/AppLayout';

const CandidateList = lazy(() => import('./pages/CandidateList'));
const CandidateDetail = lazy(() => import('./pages/CandidateDetail'));
const JobList = lazy(() => import('./pages/JobList'));
const JobDetail = lazy(() => import('./pages/JobDetail'));
const CompareCandidates = lazy(() => import('./pages/CompareCandidates'));
const Leaderboard = lazy(() => import('./pages/Leaderboard'));
const Pipeline = lazy(() => import('./pages/Pipeline'));
const Analytics = lazy(() => import('./pages/Analytics'));
const RoleAnalytics = lazy(() => import('./pages/RoleAnalytics'));
const AdminUsers = lazy(() => import('./pages/AdminUsers'));
const AuditLog = lazy(() => import('./pages/AuditLog'));
const Notifications = lazy(() => import('./pages/Notifications'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const ForgotPassword = lazy(() => import('./pages/ForgotPassword'));
const ResetPassword = lazy(() => import('./pages/ResetPassword'));
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'));
const InterviewSession = lazy(() => import('./pages/InterviewSession'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        theme={{
          algorithm: theme.darkAlgorithm,
          token: {
            colorPrimary: '#5b6af5',
            colorPrimaryHover: '#6b7aff',
            colorInfo: '#5b6af5',
            colorSuccess: '#34d399',
            colorWarning: '#fbbf24',
            colorError: '#f87171',
            colorText: '#ededf5',
            colorTextSecondary: '#a1a1bb',
            colorTextTertiary: '#64648a',
            colorBgBase: '#09090e',
            colorBgLayout: '#09090e',
            colorBgContainer: '#0e0e15',
            colorBgElevated: '#13131c',
            colorBorder: 'rgba(255,255,255,0.1)',
            borderRadius: 8,
            fontFamily: "'Fira Sans', 'Segoe UI', system-ui, -apple-system, Arial, sans-serif",
            controlHeight: 40,
          },
          components: {
            Button: {
              controlHeight: 40,
              fontWeight: 650,
            },
            Card: {
              headerFontSize: 15,
              colorBgContainer: '#0e0e15',
            },
            Table: {
              headerBg: '#13131c',
              headerColor: '#64648a',
              rowHoverBg: '#13131c',
              colorBgContainer: '#0e0e15',
            },
            Menu: {
              darkItemBg: 'transparent',
              darkSubMenuItemBg: 'transparent',
              darkItemSelectedBg: 'rgba(91, 106, 245, 0.18)',
              darkItemHoverBg: 'rgba(255, 255, 255, 0.05)',
            },
            Select: {
              colorBgContainer: '#13131c',
              colorBgElevated: '#1a1a28',
            },
            Input: {
              colorBgContainer: '#13131c',
              activeBg: '#1a1a28',
            },
            DatePicker: {
              colorBgContainer: '#13131c',
              colorBgElevated: '#1a1a28',
            },
            Popover: {
              colorBgElevated: '#13131c',
            },
            Tooltip: {
              colorBgSpotlight: '#1a1a28',
            },
          },
        }}
      >
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AuthProvider>
            <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#09090e' }}><Spin size="large" /></div>}>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/verify-email" element={<VerifyEmail />} />
              <Route path="/interview/:sessionId" element={<InterviewSession />} />

              {/* Protected routes */}
              <Route
                path="/"
                element={
                  <PrivateRoute>
                    <AppLayout />
                  </PrivateRoute>
                }
              >
                <Route index element={<CandidateList />} />
                <Route path="candidates/:id" element={<CandidateDetail />} />
                <Route path="jobs" element={<JobList />} />
                <Route path="jobs/:id" element={<JobDetail />} />
                <Route path="jobs/:jobId/compare" element={<CompareCandidates />} />
                <Route path="jobs/:jobId/leaderboard" element={<Leaderboard />} />
                <Route path="jobs/:jobId/pipeline" element={<Pipeline />} />
                <Route path="pipeline" element={<Pipeline />} />
                <Route path="jobs/:jobId/role-analytics" element={<RoleAnalytics />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="admin/users" element={<AdminUsers />} />
                <Route path="admin/audit" element={<AuditLog />} />
                <Route path="notifications" element={<Notifications />} />
                <Route
                  path="*"
                  element={
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#09090e', gap: 16 }}>
                      <span style={{ color: '#64648a', fontSize: 13, letterSpacing: 2, textTransform: 'uppercase' }}>404</span>
                      <h2 style={{ color: '#ededf5', margin: 0, fontSize: 24 }}>Page not found</h2>
                      <Link to="/" style={{ color: '#5b6af5', fontSize: 14 }}>← Back to candidates</Link>
                    </div>
                  }
                />
              </Route>
            </Routes>
            </Suspense>
          </AuthProvider>
        </BrowserRouter>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
