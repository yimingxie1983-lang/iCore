

import { useEffect, useRef, useState } from 'react'

import MarkdownRenderer from './MarkdownRenderer'
import { useChatStore } from '@/application/state/chatStore'

export interface TypewriterMarkdownProps {
  text: string

  streaming?: boolean

  speed?: number

  compact?: boolean
  className?: string

  width?: number
  fontSize?: number
  fontWeight?: number
  lineHeight?: number

  enabled?: boolean
}

export default function TypewriterMarkdown({
  text,
  streaming,
  speed = 25,
  compact,
  className,
  enabled,

  width: _width,
  fontSize: _fontSize,
  fontWeight: _fontWeight,
  lineHeight: _lineHeight,
}: TypewriterMarkdownProps) {

  const globalStreaming = useChatStore((s) => s.streaming)
  const initialLive =
    enabled !== undefined
      ? enabled
      : streaming !== undefined
        ? streaming
        : globalStreaming

  const mountedAsLiveRef = useRef(initialLive)

  const [displayedLen, setDisplayedLen] = useState(
    mountedAsLiveRef.current ? 0 : text.length,
  )

  useEffect(() => {
    if (!mountedAsLiveRef.current) {
      setDisplayedLen(text.length)
      return
    }

    setDisplayedLen((d) => Math.min(d, text.length))
  }, [text])

  useEffect(() => {
    if (!mountedAsLiveRef.current) return
    if (displayedLen >= text.length) return

    const remaining = text.length - displayedLen

    let chunkSize: number
    if (remaining > 2000) chunkSize = 40
    else if (remaining > 500) chunkSize = 8
    else chunkSize = 2

    const t = setTimeout(() => {
      setDisplayedLen((d) => Math.min(text.length, d + chunkSize))
    }, speed)
    return () => clearTimeout(t)
  }, [displayedLen, text, speed])

  const displayed = text.slice(0, displayedLen)
  const showCursor =
    mountedAsLiveRef.current && displayedLen < text.length && displayedLen > 0

  return (
    <span className={className}>
      <MarkdownRenderer text={displayed} compact={compact} />
      {showCursor && (
        <span
          className="ml-0.5 inline-block h-3 w-[2px] animate-pulse bg-current opacity-70 align-middle"
          aria-hidden
        />
      )}
    </span>
  )
}
