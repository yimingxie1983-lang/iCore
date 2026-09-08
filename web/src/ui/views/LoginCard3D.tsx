import { useEffect, useRef, type ReactNode } from 'react'

type Props = { children: ReactNode }

/**
 * 登录台外壳：流光描边 + 高光跟随。
 * 注意：不对表单容器做 3D rotate，避免输入框点击热区与视觉错位。
 */
export default function LoginCard3D({ children }: Props) {
  const shellRef = useRef<HTMLDivElement>(null)
  const glowRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const shell = shellRef.current
    if (!shell) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return

    const onMove = (e: PointerEvent) => {
      const rect = shell.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) return
      const px = (e.clientX - rect.left) / rect.width
      const py = (e.clientY - rect.top) / rect.height
      if (glowRef.current) {
        glowRef.current.style.setProperty('--mx', `${px * 100}%`)
        glowRef.current.style.setProperty('--my', `${py * 100}%`)
      }
    }

    shell.addEventListener('pointermove', onMove)
    return () => shell.removeEventListener('pointermove', onMove)
  }, [])

  return (
    <div className="login-card-stage">
      <div ref={shellRef} className="login-card-shell">
        <div ref={glowRef} className="login-card-shine" aria-hidden />
        <div className="login-card">{children}</div>
      </div>
    </div>
  )
}
