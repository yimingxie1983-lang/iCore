import { useMemo } from 'react'

const STAR_COUNT = 72
const SPARK_COUNT = 14

function seeded(i: number, salt: number) {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453
  return x - Math.floor(x)
}

export default function LoginAtmosphere() {
  const stars = useMemo(
    () =>
      Array.from({ length: STAR_COUNT }, (_, i) => ({
        left: `${seeded(i, 1) * 100}%`,
        top: `${seeded(i, 2) * 100}%`,
        size: 1 + seeded(i, 3) * 2.2,
        delay: `${seeded(i, 4) * 6}s`,
        duration: `${2.4 + seeded(i, 5) * 3.2}s`,
        opacity: 0.25 + seeded(i, 6) * 0.7,
      })),
    [],
  )

  const sparks = useMemo(
    () =>
      Array.from({ length: SPARK_COUNT }, (_, i) => ({
        left: `${8 + seeded(i, 7) * 84}%`,
        top: `${6 + seeded(i, 8) * 88}%`,
        delay: `${seeded(i, 9) * 10}s`,
        duration: `${10 + seeded(i, 10) * 10}s`,
        scale: 0.55 + seeded(i, 11) * 0.8,
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
      {sparks.map((s, i) => (
        <span
          key={`spark-${i}`}
          className="login-spark"
          style={{
            left: s.left,
            top: s.top,
            animationDelay: s.delay,
            animationDuration: s.duration,
            transform: `scale(${s.scale})`,
          }}
        />
      ))}
    </div>
  )
}
