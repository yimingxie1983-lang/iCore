import { useState } from 'react'
import { KeyRound, MailCheck, MailWarning } from 'lucide-react'

import { api } from '@/client/services/client'
import { useAuthStore } from '@/application/state/authStore'
import { Badge } from '@/ui/widgets/ui/badge'
import { Button } from '@/ui/widgets/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/ui/widgets/ui/card'
import { Input } from '@/ui/widgets/ui/input'
import { Label } from '@/ui/widgets/ui/label'
import { toast } from '@/ui/widgets/ui/sonner'

export default function Account() {
  const user = useAuthStore((s) => s.user)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sendingMail, setSendingMail] = useState(false)

  const onChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentPassword || !newPassword) {
      toast.error('请填写当前密码和新密码')
      return
    }
    if (newPassword.length < 8) {
      toast.error('新密码至少需要 8 位')
      return
    }
    if (newPassword !== confirmPassword) {
      toast.error('两次输入的新密码不一致')
      return
    }
    setSubmitting(true)
    try {
      await api.changePassword(currentPassword, newPassword)
      toast.success('密码已修改，请使用新密码重新登录')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '修改密码失败')
    } finally {
      setSubmitting(false)
    }
  }

  const onSendVerification = async () => {
    setSendingMail(true)
    try {
      await api.sendVerificationEmail()
      toast.success('验证邮件已发送，请查收')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '发送失败')
    } finally {
      setSendingMail(false)
    }
  }

  const verified = !!user?.email_verified

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 p-4 sm:p-6">
      <div>
        <h1 className="text-lg font-semibold text-foreground">账户设置</h1>
        <p className="text-xs text-muted-foreground">
          {user?.display_name || user?.username} · {user?.email || '未绑定邮箱'}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            修改密码
          </CardTitle>
          <CardDescription>修改后当前账号的其它登录会话将失效，请重新登录。</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onChangePassword} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="current_password">当前密码</Label>
              <Input
                id="current_password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new_password">新密码（至少 8 位）</Label>
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirm_password">确认新密码</Label>
              <Input
                id="confirm_password"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={submitting}>
              {submitting ? '提交中…' : '修改密码'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {verified ? (
              <MailCheck className="h-4 w-4 text-secondary" />
            ) : (
              <MailWarning className="h-4 w-4 text-muted-foreground" />
            )}
            邮箱
          </CardTitle>
          <CardDescription>
            绑定并验证邮箱后，可通过「忘记密码」自助找回账号。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">{user?.email || '未绑定邮箱'}</span>
            <Badge variant={verified ? 'secondary' : 'outline'}>
              {verified ? '已验证' : '未验证'}
            </Badge>
          </div>
          {user?.email && !verified && (
            <Button variant="outline" size="sm" disabled={sendingMail} onClick={onSendVerification}>
              {sendingMail ? '发送中…' : '发送验证邮件'}
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
