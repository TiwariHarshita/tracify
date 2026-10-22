import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthLayout } from './auth/AuthLayout';
import { PublicOnly, RequireAuth } from './auth/RouteGuards';
import { AppShell } from './components/AppShell';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { RecoveryPage } from './pages/RecoveryPage';
import { WorkspacePage } from './pages/WorkspacePage';
import { ReportEditorPage } from './pages/ReportEditorPage';
import { AccountPage } from './pages/AccountPage';

export default function App() {
  return <Routes>
    <Route element={<PublicOnly />}><Route element={<AuthLayout />}>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/forgot-password" element={<RecoveryPage key="reset" />} />
      <Route path="/check-email" element={<RecoveryPage key="verify" verify />} />
    </Route></Route>
    <Route element={<RequireAuth />}><Route element={<AppShell />}>
      <Route path="/app" element={<WorkspacePage />} />
      <Route path="/app/reports/:reportId" element={<ReportEditorPage />} />
      <Route path="/app/account" element={<AccountPage />} />
    </Route></Route>
    <Route path="*" element={<Navigate to="/app" replace />} />
  </Routes>;
}
