

import { prepare, layout } from '@chenglou/pretext'
import { useEffect, useMemo, useRef, useState } from 'react'

export interface MeasureOpts {

  font: string

  width: number

  lineHeight: number
}

export function estimateHeight(text: string, opts: MeasureOpts): {
  height: number
  lineCount: number
} {
  if (!text) return { height: 0, lineCount: 0 }
  try {
    const handle = prepare(text, opts.font)
    const r = layout(handle, opts.width, opts.lineHeight)
    return { height: r.height, lineCount: r.lineCount }
  } catch (e) {

    const charsPerLine = Math.max(1, Math.floor(opts.width / 8))
    const lineCount = Math.max(1, Math.ceil(text.length / charsPerLine))
    return { height: lineCount * opts.lineHeight, lineCount }
  }
}

export function useMeasuredHeight(
  text: string,
  opts: MeasureOpts,
): { height: number; lineCount: number } {
  const [result, setResult] = useState<{ height: number; lineCount: number }>({
    height: 0,
    lineCount: 0,
  })

  const handleRef = useRef<unknown>(null)
  const lastTextRef = useRef<string>('')
  const lastFontRef = useRef<string>('')

  useEffect(() => {
    try {

      if (text !== lastTextRef.current || opts.font !== lastFontRef.current) {
        handleRef.current = prepare(text, opts.font)
        lastTextRef.current = text
        lastFontRef.current = opts.font
      }
      if (handleRef.current) {
        const r = layout(handleRef.current as any, opts.width, opts.lineHeight)
        setResult({ height: r.height, lineCount: r.lineCount })
      } else {
        setResult(estimateHeight(text, opts))
      }
    } catch {
      setResult(estimateHeight(text, opts))
    }
  }, [text, opts.font, opts.width, opts.lineHeight])

  return result
}

export function buildFontShorthand(args: {
  size: number
  family: string
  weight?: number | string
  style?: 'normal' | 'italic'
}): string {
  const parts: string[] = []
  if (args.style && args.style !== 'normal') parts.push(args.style)
  if (args.weight) parts.push(String(args.weight))
  parts.push(`${args.size}px`)
  parts.push(args.family)
  return parts.join(' ')
}

export const PRETEXT_AVAILABLE: boolean = (() => {
  if (typeof window === 'undefined') return false
  if (typeof document === 'undefined') return false
  try {
    const canvas = document.createElement('canvas')
    return !!canvas.getContext('2d')
  } catch {
    return false
  }
})()

export function fallbackHeight(
  text: string,
  width: number,
  lineHeight: number,
  avgCharPx = 8,
): number {
  if (!text) return 0
  const charsPerLine = Math.max(1, Math.floor(width / avgCharPx))
  const lines = text.split('\n').reduce((acc, line) => {
    return acc + Math.max(1, Math.ceil(line.length / charsPerLine))
  }, 0)
  return lines * lineHeight
}
