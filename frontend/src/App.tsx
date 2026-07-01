import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppLayout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { ReviewWorkbench } from './pages/ReviewWorkbench'
import { MachineMonitor } from './pages/MachineMonitor'
import { PolicyManagement } from './pages/PolicyManagement'
import { AppealsPage } from './pages/AppealsPage'
import { QualityPage } from './pages/QualityPage'

function RequireAuth({ children }: { children: JSX.Element }) {
  const { authed } = useAuth()
  return authed ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/workbench" replace />} />
        <Route path="workbench" element={<ReviewWorkbench />} />
        <Route path="monitor" element={<MachineMonitor />} />
        <Route path="policy" element={<PolicyManagement />} />
        <Route path="appeals" element={<AppealsPage />} />
        <Route path="quality" element={<QualityPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
