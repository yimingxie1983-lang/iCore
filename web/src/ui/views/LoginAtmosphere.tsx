import { useMemo } from 'react'

const STAR_COUNT = 56

function seeded(i: number, salt: number) {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

/** 深空科研氛围：星点 + 青蓝极光，服务 iCore 医学 AI 舞台 */
export default function LoginAtmosphere() {
  const stars = useMemo(
    () =>
      Array.from({ length: STAR_COUNT }, (_, i) => ({
        left: `${seeded(i, 1) * 100}%`,
        top: `${seeded(i, 2) * 100}%`,
        size: 1 + seeded(i, 3) * 2,
        delay: `${seeded(i, 4) * 6}s`,
        duration: `${2.6 + seeded(i, 5) * 3}s`,
        opacity: 0.2 + seeded(i, 6) * 0.65,
      })),
    [],
  )

  return (
    <div className="login-atmosphere pointer-events-none" aria-hidden>
      <div className="login-veil" />
      <div className="login-aurora login-aurora-a" />
      <div className="login-aurora login-aurora-b" />
      <div className="login-aurora login-aurora-c" />
      <div className="login-grid" />
      {stars.map((s, i) => (
        <span
          key={`star-${i}`}
          className="login-star"
          style={{
            left: s.left,
            top: s.top,
            width: s.size,
            height: s.size,
            animationDelay: s.delay,
            animationDuration: s.duration,
            opacity: s.opacity,
          }}
        />
      ))}
    </div>
  )
}
