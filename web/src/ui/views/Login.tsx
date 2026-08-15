import { useEffect, useState } from 'react'
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { api, ApiError, type CaptchaChallenge } from '@/client/services/client'
import { useAuthStore, type AuthUser } from '@/application/state/authStore'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { toast } from '@/ui/widgets/ui/sonner'
import { BrandHero, useBrandVariant } from '@/ui/widgets/Layout/BrandMark'

type Mode = 'login' | 'register' | 'forgot' | 'reset'

export default function Login() {
  const nav = useNavigate()
  const loc = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const setAuth = useAuthStore((s) => s.setAuth)
  const brand = useBrandVariant()

  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [captcha, setCaptcha] = useState<CaptchaChallenge | null>(null)
  const [captchaAnswer, setCaptchaAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const resetToken = searchParams.get('reset_token')
  const verifyToken = searchParams.get('verify_token')

  const { data: reg } = useQuery({
    queryKey: ['registration-status'],
    queryFn: () => api.getRegistrationStatus(),
    staleTime: 60_000,
  })
  const allowRegistration = !!reg?.allow_registration
  const requireInviteCode = !!reg?.require_invite_code
  const requireCaptcha = !!reg?.require_captcha

  useEffect(() => {
    if (resetToken) setMode('reset')
  }, [resetToken])

  useEffect(() => {
    if (!allowRegistration && mode === 'register') setMode('login')
  }, [allowRegistration, mode])

  useEffect(() => {
    if (mode === 'register' && requireCaptcha) {
      let cancelled = false
      api
        .getCaptcha()
        .then((ch) => {
          if (!cancelled) {
            setCaptcha(ch)
            setCaptchaAnswer('')
          }
        })
        .catch(() => {})
      return () => {
        cancelled = true
      }
    }
    return undefined
  }, [mode, requireCaptcha])

  useEffect(() => {
    if (!verifyToken) return
    let cancelled = false
    api
      .verifyEmail(verifyToken)
      .then(() => {
        if (!cancelled) toast.success('邮箱验证成功')
      })
      .catch((err) => {
        if (!cancelled) toast.error(err instanceof Error ? err.message : '邮箱验证失败')
      })
      .finally(() => {
        if (!cancelled) {
          searchParams.delete('verify_token')
          setSearchParams(searchParams, { replace: true })
        }
      })
    return () => {
      cancelled = true
    }
  }, [verifyToken, searchParams, setSearchParams])

  const from = (loc.state as { from?: string } | null)?.from || '/chat'

  const onLoginOrRegister = async (e: React.FormEvent) => {
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
      if (password.length < 8) {
        toast.error('密码至少需要 8 位')
        return
      }
      if (!email.trim()) {
        toast.error('请填写邮箱')
        return
      }
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
        toast.error('邮箱格式不正确')
        return
      }
      if (password !== confirmPassword) {
        toast.error('两次输入的密码不一致')
        return
      }
      if (requireInviteCode && !inviteCode.trim()) {
        toast.error('请输入邀请码')
        return
      }
      if (requireCaptcha && (!captcha || !captchaAnswer.trim())) {
        toast.error('请完成人机验证')
        return
      }
    }
    setSubmitting(true)
    try {
      const resp =
        mode === 'login'
          ? await api.login(
              username.trim(),
              password,
              captcha && captchaAnswer.trim()
                ? { id: captcha.id, answer: captchaAnswer.trim() }
                : undefined,
            )
          : await api.register({
              username: username.trim(),
              password,
              email: email.trim(),
              display_name: displayName.trim() || undefined,
              invite_code: requireInviteCode ? inviteCode.trim() : undefined,
              captcha:
                requireCaptcha && captcha
                  ? { id: captcha.id, answer: captchaAnswer.trim() }
                  : undefined,
            })
      setAuth(resp.access_token, resp.user as AuthUser)
      toast.success(mode === 'login' ? '登录成功' : '注册成功，已自动登录')

      const brandQ = new URLSearchParams(loc.search).get('brand')
      const target = brandQ
        ? `${from}${from.includes('?') ? '&' : '?'}brand=${brandQ}`
        : from
      nav(target, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.challenge) {
        setCaptcha(err.challenge)
        setCaptchaAnswer('')
      }
      toast.error(err instanceof Error ? err.message : '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const onForgot = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim()) {
      toast.error('请输入用户名或邮箱')
      return
    }
    setSubmitting(true)
    try {
      const value = username.trim()
      await api.forgotPassword(
        value.includes('@') ? { email: value } : { username: value },
      )
      toast.success('如账号存在且已绑定邮箱，重置邮件已发送，请查收')
      setMode('login')
      setUsername('')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  const onReset = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!resetToken) {
      toast.error('缺少重置令牌')
      return
    }
    if (password.length < 8) {
      toast.error('新密码至少需要 8 位')
      return
    }
    if (password !== confirmPassword) {
      toast.error('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    try {
      await api.resetPassword(resetToken, password)
      toast.success('密码已重置，请使用新密码登录')
      searchParams.delete('reset_token')
      setSearchParams(searchParams, { replace: true })
      setMode('login')
      setPassword('')
      setConfirmPassword('')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '重置失败')
    } finally {
      setSubmitting(false)
    }
  }

  const showTabs = mode !== 'reset'

  return (
    <div className="flex h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
        <div className="mb-6">
          <BrandHero brand={brand} size={96} />
          <p className="mt-3 rounded-md border border-secondary/40 bg-secondary/10 px-3 py-2 text-center text-[12px] leading-relaxed text-secondary">
            界面版本 0815-b：产出物只在「对话洞察」第四个 Tab，已去掉右侧悬浮窗
          </p>
        </div>

        {showTabs && allowRegistration && (
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

        {mode === 'forgot' && (
          <div className="mb-5 rounded-lg bg-muted p-3 text-[12px] leading-relaxed text-muted-foreground">
            输入注册时使用的用户名或邮箱，系统将发送密码重置链接（需已配置邮件服务）。
          </div>
        )}

        <form
          onSubmit={
            mode === 'login' || mode === 'register'
              ? onLoginOrRegister
              : mode === 'forgot'
                ? onForgot
                : onReset
          }
          className="space-y-4"
        >
          {mode !== 'reset' && (
            <div className="space-y-1.5">
              <Label htmlFor="username">
                {mode === 'forgot' ? '用户名或邮箱' : '用户名'}
              </Label>
              <Input
                id="username"
                autoComplete={mode === 'forgot' ? 'email' : 'username'}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={mode === 'forgot' ? '请输入用户名或邮箱' : '请输入用户名'}
              />
            </div>
          )}

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

          {mode === 'register' && (
            <div className="space-y-1.5">
              <Label htmlFor="email">邮箱（必填，用于找回密码）</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com（必填）"
                required
              />
            </div>
          )}

          {mode === 'register' && requireInviteCode && (
            <div className="space-y-1.5">
              <Label htmlFor="invite_code">邀请码</Label>
              <Input
                id="invite_code"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                placeholder="请输入邀请码"
              />
            </div>
          )}

          {(mode === 'login' || mode === 'register' || mode === 'reset') && (
            <div className="space-y-1.5">
              <Label htmlFor="password">
                {mode === 'reset' ? '新密码（至少 8 位）' : '密码'}
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete={
                  mode === 'login'
                    ? 'current-password'
                    : mode === 'register'
                      ? 'new-password'
                      : 'new-password'
                }
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === 'reset' ? '至少 8 位' : '请输入密码'}
              />
            </div>
          )}

          {(mode === 'register' || mode === 'reset') && (
            <div className="space-y-1.5">
              <Label htmlFor="confirm_password">确认密码</Label>
              <Input
                id="confirm_password"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="再次输入密码"
              />
            </div>
          )}

          {(mode === 'register' ? requireCaptcha : mode === 'login' && !!captcha) && captcha && (
            <div className="space-y-1.5 rounded-lg border border-border bg-muted/40 p-3">
              <Label htmlFor="captcha_answer">人机验证：{captcha.question}</Label>
              <Input
                id="captcha_answer"
                inputMode="numeric"
                autoComplete="off"
                value={captchaAnswer}
                onChange={(e) => setCaptchaAnswer(e.target.value)}
                placeholder="输入计算结果"
              />
            </div>
          )}

          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting
              ? '请稍候…'
              : mode === 'login'
                ? '登录'
                : mode === 'register'
                  ? '注册并登录'
                  : mode === 'forgot'
                    ? '发送重置邮件'
                    : '重置密码'}
          </Button>
        </form>

        <div className="mt-4 flex flex-col items-center gap-2">
          {mode === 'login' && (
            <button
              type="button"
              onClick={() => setMode('forgot')}
              className="text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              忘记密码？
            </button>
          )}
          {(mode === 'forgot' || mode === 'reset') && (
            <button
              type="button"
              onClick={() => {
                setMode('login')
                setPassword('')
                setConfirmPassword('')
              }}
              className="text-[12px] text-muted-foreground transition-colors hover:text-foreground"
            >
              返回登录
            </button>
          )}
          <p className="text-center text-[11px] leading-relaxed text-muted-foreground">
            {allowRegistration
              ? mode === 'register'
                ? '首次部署可直接注册——第一个注册用户将成为管理员。'
                : '没有账号？切换到"注册"自助建号。'
              : '本实例未开放自助注册，请联系管理员建号。'}
          </p>
        </div>
      </div>
    </div>
  )
}
