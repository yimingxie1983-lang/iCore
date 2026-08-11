

import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api } from '@/client/services/client'
import { useAuthStore, type AuthUser } from '@/application/state/authStore'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { toast } from '@/ui/widgets/ui/sonner'
import { BrandHero, useBrandVariant } from '@/ui/widgets/Layout/BrandMark'

type Mode = 'login' | 'register'

export default function Login() {
  const nav = useNavigate()
  const loc = useLocation()
  const setAuth = useAuthStore((s) => s.setAuth)
  const brand = useBrandVariant()

  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const { data: reg } = useQuery({
    queryKey: ['registration-status'],
    queryFn: () => api.getRegistrationStatus(),
    staleTime: 60_000,
  })
  const allowRegistration = !!reg?.allow_registration

  useEffect(() => {
    if (!allowRegistration && mode === 'register') setMode('login')
  }, [allowRegistration, mode])

  const from = (loc.state as { from?: string } | null)?.from || '/chat'

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      toast.error('请输入用户名和密码')
      return
    }
    if (mode === 'register') {
      if (username.trim().length < 3) {
        toast.error('用户名至少需要 3 个字符')
        return
      }
      if (password.length < 6) {
        toast.error('密码至少需要 6 位')
        return
      }
    }
    setSubmitting(true)
    try {
      const resp =
        mode === 'login'
          ? await api.login(username.trim(), password)
          : await api.register({
              username: username.trim(),
              password,
              display_name: displayName.trim() || undefined,
            })
      setAuth(resp.access_token, resp.user as AuthUser)
      toast.success(mode === 'login' ? '登录成功' : '注册成功，已自动登录')

      const brandQ = new URLSearchParams(loc.search).get('brand')
      const target = brandQ
        ? `${from}${from.includes('?') ? '&' : '?'}brand=${brandQ}`
        : from
      nav(target, { replace: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
        <div className="mb-6">
          {}
          <BrandHero brand={brand} size={96} />
        </div>

        {}
        {allowRegistration && (
          <div className="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-muted p-1 text-sm">
            {(['login', 'register'] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={
                  'rounded-md py-1.5 font-medium transition-colors ' +
                  (mode === m
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground')
                }
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="username">用户名</Label>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
            />
          </div>

          {mode === 'register' && (
            <div className="space-y-1.5">
              <Label htmlFor="display_name">显示名（可选）</Label>
              <Input
                id="display_name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="不填则与用户名相同"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'register' ? '至少 6 位' : '请输入密码'}
            />
          </div>

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录'}
          </Button>
        </form>

        <p className="mt-4 text-center text-[11px] leading-relaxed text-muted-foreground">
          {allowRegistration
            ? mode === 'register'
              ? '首次部署可直接注册——首个注册用户将成为管理员。'
              : '没有账号？切换到"注册"自助建号。'
            : '本实例未开放自助注册，请联系管理员建号。'}
        </p>
      </div>
    </div>
  )
}
