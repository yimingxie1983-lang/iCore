

import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { cn } from '@/shared/foundation/utils'

export interface BrandVariant {
  id: 1 | 2 | 3
  src: string

  shortTitle: string

  fullTitle: string
  subtitle: string
  landscape?: boolean
}

export const BRAND_VARIANTS: BrandVariant[] = [
  {
    id: 1,
    src: '/logo/logo-fudan.jpg',
    shortTitle: '复旦大学上海医学科研数据中心',
    fullTitle: '复旦大学上海医学科研数据中心\niCore 智能体平台',
    subtitle: 'iCore 智能体平台',
    landscape: true,
  },
  {
    id: 2,
    src: '/logo/logo-nhdrc.jpg',
    shortTitle: '国家卫健委卫生发展中心',
    fullTitle: '国家卫健委卫生发展中心\n智能体平台',
    subtitle: '智能体平台',
  },
  {
    id: 3,
    src: '/logo/logo-zhongshan.jpg',
    shortTitle: '国家人工智能应用中试基地',
    fullTitle: '国家人工智能应用中试基地\niCore 智能体平台',
    subtitle: 'iCore 智能体平台',
  },
]

const STORAGE_KEY = 'icore-brand-variant'

export function resolveBrandId(param?: string | null): 1 | 2 | 3 {
  const raw =
    param ||
    (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(STORAGE_KEY) : null)
  const n = Number(raw)
  if (n === 1 || n === 2 || n === 3) return n
  return 1
}

export function getBrand(id: 1 | 2 | 3 = 1): BrandVariant {
  return BRAND_VARIANTS.find((b) => b.id === id) ?? BRAND_VARIANTS[0]
}

export function useBrandVariant(): BrandVariant {
  const [params] = useSearchParams()
  return useMemo(() => {
    const id = resolveBrandId(params.get('brand'))
    try {
      sessionStorage.setItem(STORAGE_KEY, String(id))
    } catch {

    }
    return getBrand(id)
  }, [params])
}

interface MarkProps {
  brand?: BrandVariant
  size?: number
  className?: string
}

export function BrandLogo({ brand, size = 40, className }: MarkProps) {
  const b = brand ?? BRAND_VARIANTS[0]
  return (
    <img
      src={b.src}
      alt={b.shortTitle}
      className={className}
      style={{
        height: size,
        width: b.landscape ? 'auto' : size,
        maxWidth: b.landscape ? Math.round(size * 2.4) : size,
        objectFit: 'contain',
        borderRadius: Math.max(4, Math.round(size * 0.08)),
        display: 'block',
        flexShrink: 0,
        background: '#fff',
      }}
    />
  )
}

export function BrandHeader({
  brand,
  size = 48,
  className,
}: {
  brand: BrandVariant
  size?: number
  className?: string
}) {
  return (
    <div className={cn('flex min-w-0 items-center gap-3', className)}>
      <BrandLogo brand={brand} size={size} />
      <div className="min-w-0 flex-1 text-left">
        <div className="truncate text-[13px] font-semibold leading-snug text-foreground" title={brand.shortTitle}>
          {brand.shortTitle}
        </div>
        <div className="mt-0.5 truncate text-[11px] leading-tight text-muted-foreground">
          {brand.subtitle}
        </div>
      </div>
    </div>
  )
}

export function BrandHero({
  brand,
  size = 88,
  className,
}: {
  brand: BrandVariant
  size?: number
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center gap-5 text-center', className)}>
      <BrandLogo brand={brand} size={size} />
      <div>
        <div className="whitespace-pre-line text-[20px] font-semibold leading-snug text-foreground sm:text-[22px]">
          {brand.fullTitle}
        </div>
        <div className="mt-2 text-[12px] text-muted-foreground">医学 AI 协作框架 · 多用户工作台</div>
      </div>
    </div>
  )
}

export default function BrandMark({
  size = 36,
  className,
}: {
  size?: number
  className?: string
  variant?: string
}) {
  const brand = useBrandVariant()
  return <BrandLogo brand={brand} size={size} className={className} />
}
