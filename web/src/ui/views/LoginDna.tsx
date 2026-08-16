import { useEffect, useRef } from 'react'

type Vec = { x: number; y: number; z: number }

function project(p: Vec, cx: number, cy: number, fl: number) {
  const s = fl / (fl + p.z + 160)
  return { x: cx + p.x * s, y: cy + p.y * s, s, z: p.z }
}

function hexToRgb(hex: string) {
  const n = parseInt(hex.slice(1), 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

function rgba(hex: string, a: number) {
  const { r, g, b } = hexToRgb(hex)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

export default function LoginDna() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let width = 0
    let height = 0
    let raf = 0
    let t = 0
    let alive = true
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const applySize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      canvas.width = Math.floor(width * dpr)
      canvas.height = Math.floor(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const drawDot = (x: number, y: number, r: number, color: string, glow: number) => {
      ctx.save()
      ctx.shadowBlur = glow
      ctx.shadowColor = color
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
      ctx.fillStyle = 'rgba(255,255,255,0.85)'
      ctx.beginPath()
      ctx.arc(x - r * 0.25, y - r * 0.25, r * 0.28, 0, Math.PI * 2)
      ctx.fill()
    }

    const draw = () => {
      if (!alive) return
      if (!reduced) t += 0.018
      ctx.clearRect(0, 0, width, height)

      const cx = width * 0.46
      const cy = height * 0.5
      const radius = Math.min(width, height) * 0.16
      const helixH = Math.hypot(width, height) * 1.28
      const pairs = 72
      const turns = 4.2
      const fl = 720
      const rot = t
      const tilt = -Math.PI / 5.2

      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(tilt)

      type Node = ReturnType<typeof project> & { color: string }
      const nodesA: Node[] = []
      const nodesB: Node[] = []

      for (let i = 0; i < pairs; i++) {
        const p = i / (pairs - 1)
        const y = (p - 0.5) * helixH
        const angle = p * Math.PI * 2 * turns + rot
        const a: Vec = { x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius }
        const b: Vec = {
          x: Math.cos(angle + Math.PI) * radius,
          y,
          z: Math.sin(angle + Math.PI) * radius,
        }
        const at = i % 2 === 0
        nodesA.push({
          ...project(a, 0, 0, fl),
          color: at ? '#22d3ee' : '#38bdf8',
        })
        nodesB.push({
          ...project(b, 0, 0, fl),
          color: at ? '#fbbf24' : '#c084fc',
        })
      }

      type Layer =
        | { kind: 'seg'; z: number; x1: number; y1: number; x2: number; y2: number; w: number; color: string }
        | { kind: 'rung'; z: number; x1: number; y1: number; x2: number; y2: number; w: number }
        | { kind: 'dot'; z: number; x: number; y: number; r: number; color: string }

      const layers: Layer[] = []
      const pushSeg = (n0: Node, n1: Node, color: string) => {
        layers.push({
          kind: 'seg',
          z: (n0.z + n1.z) / 2,
          x1: n0.x,
          y1: n0.y,
          x2: n1.x,
          y2: n1.y,
          w: 8.6 * ((n0.s + n1.s) / 2),
          color,
        })
      }
      for (let i = 0; i < pairs; i++) {
        if (i < pairs - 1) {
          pushSeg(nodesA[i], nodesA[i + 1], '#22d3ee')
          pushSeg(nodesB[i], nodesB[i + 1], '#a78bfa')
        }
        layers.push({
          kind: 'rung',
          z: (nodesA[i].z + nodesB[i].z) / 2,
          x1: nodesA[i].x,
          y1: nodesA[i].y,
          x2: nodesB[i].x,
          y2: nodesB[i].y,
          w: 2.2 * ((nodesA[i].s + nodesB[i].s) / 2),
        })
        layers.push({
          kind: 'dot',
          z: nodesA[i].z,
          x: nodesA[i].x,
          y: nodesA[i].y,
          r: 8.4 * nodesA[i].s,
          color: nodesA[i].color,
        })
        layers.push({
          kind: 'dot',
          z: nodesB[i].z,
          x: nodesB[i].x,
          y: nodesB[i].y,
          r: 8.4 * nodesB[i].s,
          color: nodesB[i].color,
        })
      }

      layers.sort((a, b) => a.z - b.z)
      for (const item of layers) {
        if (item.kind === 'seg') {
          ctx.save()
          ctx.lineCap = 'round'
          ctx.beginPath()
          ctx.moveTo(item.x1, item.y1)
          ctx.lineTo(item.x2, item.y2)
          ctx.strokeStyle = rgba(item.color, 0.28)
          ctx.lineWidth = item.w * 2.2
          ctx.shadowBlur = 22
          ctx.shadowColor = rgba(item.color, 0.7)
          ctx.stroke()
          ctx.strokeStyle = rgba(item.color, 0.98)
          ctx.lineWidth = item.w
          ctx.stroke()
          ctx.restore()
        } else if (item.kind === 'rung') {
          const depth = (item.z / radius + 1) / 2
          ctx.save()
          ctx.beginPath()
          ctx.moveTo(item.x1, item.y1)
          ctx.lineTo(item.x2, item.y2)
          ctx.strokeStyle = `rgba(250, 204, 21, ${0.16 + depth * 0.5})`
          ctx.lineWidth = item.w
          ctx.shadowBlur = 8
          ctx.shadowColor = 'rgba(250, 204, 21, 0.5)'
          ctx.stroke()
          ctx.restore()
        } else {
          drawDot(item.x, item.y, item.r, item.color, 18)
        }
      }

      const particleCount = 14
      for (let k = 0; k < particleCount; k++) {
        const onA = k % 2 === 0
        const nodes = onA ? nodesA : nodesB
        const u = (t * 0.35 + k / particleCount) % 1
        const idx = u * (nodes.length - 1)
        const i0 = Math.floor(idx)
        const i1 = Math.min(nodes.length - 1, i0 + 1)
        const f = idx - i0
        const n0 = nodes[i0]
        const n1 = nodes[i1]
        const x = n0.x + (n1.x - n0.x) * f
        const y = n0.y + (n1.y - n0.y) * f
        const s = n0.s + (n1.s - n0.s) * f
        drawDot(x, y, 3.4 * s, onA ? '#e0f2fe' : '#fde68a', 22)
      }

      ctx.restore()
      raf = requestAnimationFrame(draw)
    }

    applySize()
    const ro = new ResizeObserver(applySize)
    ro.observe(canvas)
    raf = requestAnimationFrame(draw)

    return () => {
      alive = false
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [])

  return (
    <div className="login-dna-panel" aria-hidden>
      <div className="login-dna-glow" />
      <canvas ref={canvasRef} className="relative h-full w-full" />
    </div>
  )
}
