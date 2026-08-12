import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { SlidersHorizontal } from 'lucide-react'

import { api } from '@/client/services/client'
import { Button } from '@/ui/widgets/ui/button'
import { Input } from '@/ui/widgets/ui/input'
import { Switch } from '@/ui/widgets/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/ui/widgets/ui/select'
import { toast } from '@/ui/widgets/ui/sonner'

export default function AdminBilling() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['billing-config'],
    queryFn: () => api.getBillingConfig(),
  })

  const [grant, setGrant] = useState('')
  const [markup, setMarkup] = useState('')
  const [flat, setFlat] = useState('')
  const [flatOut, setFlatOut] = useState('')
  const [busy, setBusy] = useState(false)

  const enforce = !!data?.enforce
  const grantVal = grant === '' ? String(data?.initial_grant ?? 0) : grant
  const markupVal = markup === '' ? String(data?.markup ?? 1) : markup
  const mode = data?.mode ?? 'split'
  const flatVal = flat === '' ? String(data?.flat_credits_per_1m ?? 6900) : flat
  const flatOutVal =
    flatOut === '' ? String(data?.flat_output_credits_per_1m ?? 27000) : flatOut

  const save = async (patch: Parameters<typeof api.setBillingConfig>[0]) => {
    setBusy(true)
    try {
      const next = await api.setBillingConfig(patch)
      qc.setQueryData(['billing-config'], next)
      toast.success('计费设置已更新')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-4 sm:p-6">
      <div className="mb-4 shrink-0">
        <h2 className="text-base font-semibold text-foreground">费用管理</h2>
        <p className="mt-0.5 text-[12px] text-muted-foreground">
          计费配置 / 定价规则：积分按 token 消耗实时扣减，人民币成本后台单独记录。
        </p>
      </div>

      <div className="rounded-xl border border-border bg-card px-4 py-3">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
            <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
          </div>
          <div>
            <div className="text-sm font-medium text-foreground">计费设置</div>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              积分按 token 消耗实时扣减；人民币成本后台单独记录。
            </p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          {/* 余额不足拦截 */}
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <div>
              <div className="text-[13px] font-medium text-foreground">余额不足拦截</div>
              <p className="text-[11px] text-muted-foreground">
                {enforce ? '余额≤0 时禁止发起对话' : '不拦截（允许欠费）'}
              </p>
            </div>
            <Switch
              checked={enforce}
              disabled={busy}
              onCheckedChange={(v) => save({ enforce: v })}
            />
          </div>

          {/* 新用户初始赠送 */}
          <div className="rounded-lg border border-border px-3 py-2">
            <div className="text-[13px] font-medium text-foreground">新用户初始赠送</div>
            <div className="mt-1.5 flex gap-2">
              <Input
                type="number"
                value={grantVal}
                onChange={(e) => setGrant(e.target.value)}
                className="h-8"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => save({ initial_grant: Math.max(0, parseInt(grantVal) || 0) })}
              >
                保存
              </Button>
            </div>
          </div>

          {/* 价格系数 */}
          <div className="rounded-lg border border-border px-3 py-2">
            <div className="text-[13px] font-medium text-foreground">价格系数（markup）</div>
            <div className="mt-1.5 flex gap-2">
              <Input
                type="number"
                step="0.1"
                value={markupVal}
                onChange={(e) => setMarkup(e.target.value)}
                className="h-8"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => save({ markup: Math.max(0, parseFloat(markupVal) || 0) })}
              >
                保存
              </Button>
            </div>
          </div>

          {/* 计费模式 */}
          <div className="rounded-lg border border-border px-3 py-2">
            <div className="text-[13px] font-medium text-foreground">计费模式</div>
            <div className="mt-1.5">
              <Select
                value={mode}
                disabled={busy}
                onValueChange={(v) => save({ mode: v as 'flat' | 'tiered' | 'split' })}
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="flat">拍平单价（对外统一口径）</SelectItem>
                  <SelectItem value="split">两口价（输入统一 + 输出单独）</SelectItem>
                  <SelectItem value="tiered">分档透明（输入/缓存/输出各费率）</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {mode === 'flat'
                ? '所有 token 统一单价，缓存差价即利润'
                : mode === 'split'
                  ? '输入不分缓存统一价、输出单独一个价，各算各的相加'
                  : '按真实成本比例分档计费'}
            </p>
          </div>

          {/* 输入/拍平单价 */}
          <div className="rounded-lg border border-border px-3 py-2">
            <div className="text-[13px] font-medium text-foreground">
              {mode === 'split' ? '输入单价（积分/百万 token）' : '拍平单价（积分/百万 token）'}
            </div>
            <div className="mt-1.5 flex gap-2">
              <Input
                type="number"
                step="100"
                value={flatVal}
                disabled={mode === 'tiered'}
                onChange={(e) => setFlat(e.target.value)}
                className="h-8"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={busy || mode === 'tiered'}
                onClick={() =>
                  save({ flat_credits_per_1m: Math.max(0, parseFloat(flatVal) || 0) })
                }
              >
                保存
              </Button>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              6900 ≈ ¥6.9/百万 token（1 积分≈¥0.001）
            </p>
          </div>

          {/* 输出单价 */}
          <div className="rounded-lg border border-border px-3 py-2">
            <div className="text-[13px] font-medium text-foreground">
              输出单价（积分/百万 token）
            </div>
            <div className="mt-1.5 flex gap-2">
              <Input
                type="number"
                step="100"
                value={flatOutVal}
                disabled={mode !== 'split'}
                onChange={(e) => setFlatOut(e.target.value)}
                className="h-8"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={busy || mode !== 'split'}
                onClick={() =>
                  save({
                    flat_output_credits_per_1m: Math.max(0, parseFloat(flatOutVal) || 0),
                  })
                }
              >
                保存
              </Button>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              27000 ≈ ¥27/百万 token（= Kimi 输出真实价，不亏输出）
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
