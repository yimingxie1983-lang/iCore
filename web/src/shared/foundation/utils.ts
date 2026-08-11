

import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

const TZ_SUFFIX_RE = /(Z|[+-]\d{2}(:?\d{2})?)$/

export function parseBackendTime(
  raw: string | number | null | undefined,
): number | null {
  if (raw == null) return null

  if (typeof raw === 'number') {
    if (!Number.isFinite(raw) || raw <= 0) return null
    return raw < 1e12 ? raw * 1000 : raw
  }

  const s = String(raw).trim()
  if (!s) return null

  if (/^\d+(\.\d+)?$/.test(s)) {
    const n = Number(s)
    if (Number.isFinite(n) && n > 0) return n < 1e12 ? n * 1000 : n
  }

  let iso = s.includes('T') ? s : s.replace(' ', 'T')

  const hasTimePart = /\d:\d/.test(iso)

  const tz = hasTimePart ? iso.match(TZ_SUFFIX_RE)?.[0] : undefined
  if (tz) {
    if (tz !== 'Z') {
      const sign = tz[0]
      const digits = tz.slice(1).replace(':', '')
      const hh = digits.slice(0, 2)
      const mm = digits.length >= 4 ? digits.slice(2, 4) : '00'
      iso = iso.slice(0, iso.length - tz.length) + `${sign}${hh}:${mm}`
    }
    const ms = Date.parse(iso)
    if (!Number.isNaN(ms)) return ms
  } else {

    const ms = Date.parse(iso + 'Z')
    if (!Number.isNaN(ms)) return ms
  }

  const fallback = Date.parse(s)
  return Number.isNaN(fallback) ? null : fallback
}
