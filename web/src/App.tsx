

import { useEffect, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import AppLayout from './ui/widgets/Layout/AppLayout'
import ChatWorkbench from './ui/views/ChatWorkbench'
import Projects from './ui/views/Projects'
import ProjectCreate from './ui/views/ProjectCreate'
import Agents from './ui/views/Agents'
import Providers from './ui/views/Providers'
import Memory from './ui/views/Memory'
import Skills from './ui/views/Skills'
import Credits from './ui/views/Credits'
import Login from './ui/views/Login'
import Account from './ui/views/Account'
import AdminUsers from './ui/views/admin/Users'
import AdminRoles from './ui/views/admin/Roles'
import AdminBilling from './ui/views/admin/Billing'
import AdminEvolution from './ui/views/admin/Evolution'
import AdminMonitor from './ui/views/admin/Monitor'
import AdminAuthEvents from './ui/views/admin/AuthEvents'
import AdminProjects from './ui/views/admin/Projects'
import Market from './ui/views/Market'
import { api, type AuthUser } from './client/services/client'
import {
  useAuthStore,
  checkPermission,
  forceLogout,
} from './application/state/authStore'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  const setUser = useAuthStore((s) => s.setUser)
  const [validating, setValidating] = useState(!!token)
  const loc = useLocation()

  useEffect(() => {
    if (!token) {
      setValidating(false)
      return
    }
    let cancelled = false
    setValidating(true)
    api
      .me()
      .then((u) => {
        if (!cancelled) {
          setUser(u as AuthUser)
          setValidating(false)
        }
      })
      .catch(() => {
        if (!cancelled) forceLogout()
      })
    return () => {
      cancelled = true
    }
  }, [token, setUser])

  if (!token) {
    return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  }
  if (validating) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
        正在验证登录状态…
      </div>
    )
  }
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const isAdmin = useAuthStore((s) => s.isAdmin)
  if (!isAdmin) return <Navigate to="/chat" replace />
  return <>{children}</>
}

function RequirePermission({
  perm,
  children,
}: {
  perm: string
  children: React.ReactNode
}) {
  const ok = useAuthStore((s) => checkPermission(s.user, perm))
  if (!ok) return <Navigate to="/chat" replace />
  return <>{children}</>
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/chat" replace />} />
        <Route path="/chat" element={<ChatWorkbench />} />
        <Route path="/chat/:projectId" element={<ChatWorkbench />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/new" element={<ProjectCreate />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/skills" element={<Skills />} />
        <Route path="/providers" element={<Providers />} />
        <Route path="/memory" element={<Memory />} />
        <Route path="/credits" element={<Credits />} />
        <Route path="/account" element={<Account />} />
        <Route
          path="/market"
          element={
            <RequirePermission perm="market.browse">
              <Market />
            </RequirePermission>
          }
        />
        <Route
          path="/admin/users"
          element={
            <RequirePermission perm="user.manage">
              <AdminUsers />
            </RequirePermission>
          }
        />
        <Route
          path="/admin/roles"
          element={
            <RequirePermission perm="role.manage">
              <AdminRoles />
            </RequirePermission>
          }
        />
        <Route
          path="/admin/billing"
          element={
            <RequirePermission perm="billing.manage">
              <AdminBilling />
            </RequirePermission>
          }
        />
        <Route
          path="/admin/evolution"
          element={
            <RequirePermission perm="evolution.manage">
              <AdminEvolution />
            </RequirePermission>
          }
        />
        <Route
          path="/admin/monitor"
          element={
            <RequireAdmin>
              <AdminMonitor />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/projects"
          element={
            <RequireAdmin>
              <AdminProjects />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/auth-events"
          element={
            <RequirePermission perm="audit.view">
              <AdminAuthEvents />
            </RequirePermission>
          }
        />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Route>
    </Routes>
  )
}

export default App
