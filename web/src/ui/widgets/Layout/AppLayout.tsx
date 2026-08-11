

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  Bot,
  BrainCircuit,
  FolderOpen,
  Gauge,
  Library,
  LogOut,
  Menu,
  MessageSquare,
  Network,
  Share2,
  ShieldCheck,
  Sparkles,
  Users,
  Wallet,
  X,
} from 'lucide-react'

import { api } from '@/client/services/client'
import { useAuthStore, checkPermission } from '@/application/state/authStore'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/ui/widgets/ui/dropdown-menu'
import BrandMark, { BrandHeader, useBrandVariant } from './BrandMark'
import { cn } from '@/shared/foundation/utils'

interface NavItem {
  to: string
  label: string
  desc: string
  icon: React.ComponentType<{ className?: string }>

  perm: string

  feature?: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/chat', label: '对话工作台', icon: MessageSquare, desc: '链路 + token 计费', perm: 'menu.chat' },
  { to: '/projects', label: '项目', icon: FolderOpen, desc: '工作区 + 记忆', perm: 'menu.projects' },
  { to: '/market', label: '共享市场', icon: Share2, desc: '发布 / 申请 / 审批', perm: 'menu.market', feature: 'project_sharing' },
  { to: '/agents', label: '智能体', icon: Bot, desc: 'soul + 人格库', perm: 'menu.agents' },
  { to: '/skills', label: '技能库', icon: Library, desc: 'SKILL.md 生态 / 拖拽上传', perm: 'menu.skills' },
  { to: '/memory', label: '记忆库', icon: BrainCircuit, desc: '项目 / 经验簿', perm: 'menu.memory' },
  { to: '/credits', label: '我的额度', icon: Wallet, desc: '积分余额 / 账单', perm: 'menu.credits' },
]

const ADMIN_NAV_ITEMS: NavItem[] = [
  { to: '/providers', label: '模型供应商', icon: Network, desc: '路由 + API key', perm: 'menu.providers' },
  { to: '/admin/users', label: '用户管理', icon: Users, desc: '多用户 / 项目授权', perm: 'menu.users' },
  { to: '/admin/roles', label: '角色管理', icon: ShieldCheck, desc: 'RBAC 角色 / 权限分配', perm: 'menu.roles' },
  { to: '/admin/evolution', label: '进化审批', icon: Sparkles, desc: '自进化 Skill 草稿闸门', perm: 'menu.evolution' },
  { to: '/admin/monitor', label: '系统监控', icon: Gauge, desc: '实时资源 / 服务健康', perm: 'menu.monitor' },
]

function UserMenu() {
  const nav = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  const initials = (user?.display_name || user?.username || '?').slice(0, 1).toUpperCase()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 rounded-full border border-border bg-card py-1 pl-1 pr-2.5 text-[12px] transition-colors hover:bg-muted">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
            {initials}
          </span>
          <span className="max-w-[80px] truncate font-medium text-foreground sm:max-w-[120px]">
            {user?.display_name || user?.username || '未登录'}
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel>
          <div className="flex flex-col">
            <span className="font-semibold text-foreground">
              {user?.display_name || user?.username}
            </span>
            <span className="text-[11px] font-normal text-muted-foreground">
              {user?.role === 'admin' ? '管理员' : '普通用户'}
              {user?.email ? ` · ${user.email}` : ''}
            </span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onClick={() => {
            logout()
            nav('/login', { replace: true })
          }}
        >
          <LogOut className="h-4 w-4" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function HealthBadge() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.health(),
    refetchInterval: 30_000,
    retry: 0,
  })

  if (isLoading) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground/40" />
        <span className="hidden sm:inline">检查中…</span>
      </span>
    )
  }
  if (isError || !data) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/[0.06] px-2.5 py-1 text-[11px] font-medium text-destructive">
        <span className="h-1.5 w-1.5 rounded-full bg-destructive" />
        <span className="hidden sm:inline">后端未连接</span>
      </span>
    )
  }
  const ok = data.status === 'healthy'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium',
        ok
          ? 'border-emerald-500/30 bg-emerald-500/[0.08] text-emerald-700'
          : 'border-amber-500/30 bg-amber-500/[0.08] text-amber-700',
      )}
    >
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          ok ? 'bg-emerald-500' : 'bg-amber-500',
        )}
      />
      <span className="hidden sm:inline">{ok ? '后端在线' : '降级运行'}</span>
    </span>
  )
}

function CreditsBadge() {
  const nav = useNavigate()
  const { data } = useQuery({
    queryKey: ['my-credits'],
    queryFn: () => api.myCredits(),
    refetchInterval: 15_000,
    retry: 0,
  })
  if (!data) return null
  const low = data.balance <= 0
  return (
    <button
      onClick={() => nav('/credits')}
      title="我的积分余额"
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
        low
          ? 'border-destructive/30 bg-destructive/[0.06] text-destructive hover:bg-destructive/[0.1]'
          : 'border-border bg-card text-foreground hover:bg-muted',
      )}
    >
      <Wallet className={cn('h-3.5 w-3.5', low ? 'text-destructive' : 'text-muted-foreground')} />
      <span className="font-mono">{Math.round(data.balance).toLocaleString('zh-CN')}</span>
      <span className="hidden text-muted-foreground sm:inline">积分</span>
    </button>
  )
}

function NavRow({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
          isActive
            ? 'bg-sidebar-active-bg text-sidebar-active-fg'
            : 'text-sidebar-foreground hover:bg-muted',
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            className={cn(
              'h-[18px] w-[18px] shrink-0',
              isActive ? 'text-sidebar-active-fg' : 'text-sidebar-muted',
            )}
          />
          <div className="min-w-0 flex-1">
            <div
              className={cn(
                'text-[13px] leading-tight',
                isActive ? 'font-semibold' : 'font-medium',
              )}
            >
              {item.label}
            </div>
            <div
              className={cn(
                'mt-0.5 text-[10.5px] leading-tight',
                isActive ? 'text-sidebar-active-fg/70' : 'text-sidebar-muted',
              )}
            >
              {item.desc}
            </div>
          </div>
          {isActive && <span className="h-1.5 w-1.5 rounded-full bg-secondary" />}
        </>
      )}
    </NavLink>
  )
}

function SidebarBody({
  navItems,
  adminItems,
  onNavigate,
}: {
  navItems: NavItem[]
  adminItems: NavItem[]
  onNavigate?: () => void
}) {
  const brand = useBrandVariant()
  return (
    <>
      {}
      <div className="border-b border-sidebar-border px-4 py-4">
        <BrandHeader brand={brand} size={52} />
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
        {navItems.map((item) => (
          <NavRow key={item.to} item={item} onNavigate={onNavigate} />
        ))}

        {adminItems.length > 0 && (
          <div className="pt-3">
            <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-sidebar-muted">
              系统管理
            </div>
            {adminItems.map((item) => (
              <NavRow key={item.to} item={item} onNavigate={onNavigate} />
            ))}
          </div>
        )}
      </nav>

      <div className="border-t border-sidebar-border px-5 py-3">
        <div className="text-[11px] text-sidebar-muted">
          <span>v0.1.0</span>
        </div>
      </div>
    </>
  )
}

export default function AppLayout() {
  const loc = useLocation()
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  useEffect(() => {
    setMobileNavOpen(false)
  }, [loc.pathname])

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: () => api.me(),
    staleTime: 30_000,
    retry: 0,
  })
  useEffect(() => {
    if (me) setUser(me as never)

  }, [me])

  const { data: features } = useQuery({
    queryKey: ['features'],
    queryFn: () => api.getFeatures(),
    staleTime: 60_000,
    retry: 0,
  })

  const featureOn = (f?: string) =>
    !f || !!(features as Record<string, boolean> | undefined)?.[f]

  const navItems = NAV_ITEMS.filter(
    (i) => checkPermission(user, i.perm) && featureOn(i.feature),
  )
  const adminItems = ADMIN_NAV_ITEMS.filter(
    (i) => checkPermission(user, i.perm) && featureOn(i.feature),
  )
  const currentItem = [...navItems, ...adminItems].find((i) =>
    loc.pathname.startsWith(i.to),
  )

  return (
    <div className="flex h-screen min-h-0 bg-background">
      {}
      <aside className="hidden w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <SidebarBody navItems={navItems} adminItems={adminItems} />
      </aside>

      {}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/40"
            aria-label="关闭导航"
            onClick={() => setMobileNavOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-[min(20rem,88vw)] flex-col bg-sidebar shadow-xl">
            <div className="flex items-center justify-end border-b border-sidebar-border px-3 py-2">
              <button
                type="button"
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setMobileNavOpen(false)}
                aria-label="关闭"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <SidebarBody
              navItems={navItems}
              adminItems={adminItems}
              onNavigate={() => setMobileNavOpen(false)}
            />
          </aside>
        </div>
      )}

      {}
      <div className="flex min-w-0 flex-1 flex-col">
        {}
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-card/80 px-3 backdrop-blur sm:gap-3 sm:px-5 lg:px-6">
          <button
            type="button"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
            onClick={() => setMobileNavOpen(true)}
            aria-label="打开导航"
          >
            <Menu className="h-5 w-5" />
          </button>

          {}
          <div className="min-w-0 flex-1 lg:hidden">
            <BrandMark size={28} />
          </div>

          {currentItem && (
            <>
              <currentItem.icon className="hidden h-4 w-4 text-muted-foreground sm:block" />
              <div className="hidden min-w-0 items-baseline gap-2 md:flex">
                <h1 className="truncate text-[15px] font-semibold tracking-tight text-foreground">
                  {currentItem.label}
                </h1>
                <span className="hidden truncate text-[12px] text-muted-foreground xl:inline">
                  · {currentItem.desc}
                </span>
              </div>
            </>
          )}
          <div className="flex-1" />
          <CreditsBadge />
          <HealthBadge />
          <UserMenu />
        </header>

        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
