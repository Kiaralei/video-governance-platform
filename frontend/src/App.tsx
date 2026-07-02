import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppLayout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { ReviewWorkbench } from './pages/ReviewWorkbench'
import { MachineMonitor } from './pages/MachineMonitor'
import { PolicyManagement } from './pages/PolicyManagement'
import { AppealsPage } from './pages/AppealsPage'
import { QualityPage } from './pages/QualityPage'
import { canAccessRoute, defaultRouteForRoles } from './auth/roleAccess'

function RequireAuth({ children }: { children: JSX.Element }) {
  const { authed } = useAuth()
  return authed ? children : <Navigate to="/login" replace />
}

function RoleHome() {
  const { roles } = useAuth()
  return <Navigate to={defaultRouteForRoles(roles)} replace />
}

function RequireRoute({ path, children }: { path: string; children: JSX.Element }) {
  const { roles } = useAuth()
  return canAccessRoute(path, roles) ? children : <RoleHome />
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
        <Route index element={<RoleHome />} />
        <Route path="workbench" element={<RequireRoute path="/workbench"><ReviewWorkbench /></RequireRoute>} />
        <Route path="monitor" element={<RequireRoute path="/monitor"><MachineMonitor /></RequireRoute>} />
        <Route path="policy" element={<RequireRoute path="/policy"><PolicyManagement /></RequireRoute>} />
        <Route path="appeals" element={<RequireRoute path="/appeals"><AppealsPage /></RequireRoute>} />
        <Route path="quality" element={<RequireRoute path="/quality"><QualityPage /></RequireRoute>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
