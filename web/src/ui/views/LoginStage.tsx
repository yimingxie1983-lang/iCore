import { useEffect, useRef } from 'react'

type V3 = { x: number; y: number; z: number }

function rx(p: V3, a: number): V3 {
  const c = Math.cos(a)
  const s = Math.sin(a)
  return { x: p.x, y: p.y * c - p.z * s, z: p.y * s + p.z * c }
}

function ry(p: V3, a: number): V3 {
  const c = Math.cos(a)
  const s = Math.sin(a)
  return { x: p.x * c + p.z * s, y: p.y, z: -p.x * s + p.z * c }
}

function project(p: V3, cx: number, cy: number, fl: number) {
  const s = fl / Math.max(48, fl + p.z)
  return { x: cx + p.x * s, y: cy + p.y * s, s, z: p.z }
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function rgba(r: number, g: number, b: number, a: number) {
  return `rgba(${r},${g},${b},${a})`
}

/** iCore 登录舞台：医学 DNA × 智能体神经网络 × 协作核心 */
export default function LoginStage() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let w = 0
    let h = 0
    let raf = 0
    let t = 0
    let alive = true
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 }
    const cam = { yaw: 0, pitch: 0 }

    const agents = Array.from({ length: 18 }, (_, i) => {
      const a = (i / 18) * Math.PI * 2
      const r = 150 + (i % 5) * 28
      return {
        base: a,
        r,
        y: ((i % 7) - 3) * 28,
        hue: i % 3,
        phase: i * 0.7,
      }
    })

    const applySize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const rect = canvas.getBoundingClientRect()
      w = Math.max(1, rect.width)
      h = Math.max(1, rect.height)
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const onMove = (e: PointerEvent) => {
      pointer.tx = (e.clientX / window.innerWidth) * 2 - 1
      pointer.ty = (e.clientY / window.innerHeight) * 2 - 1
    }

    const glowDot = (
      x: number,
      y: number,
      r: number,
      color: [number, number, number],
      a: number,
      blur = 14,
    ) => {
      if (r < 0.4 || a < 0.03) return
      const [cr, cg, cb] = color
      const g = ctx.createRadialGradient(x - r * 0.3, y - r * 0.35, 0, x, y, r)
      g.addColorStop(0, rgba(255, 255, 255, Math.min(0.95, a + 0.2)))
      g.addColorStop(0.4, rgba(cr, cg, cb, a))
      g.addColorStop(1, rgba(cr, cg, cb, 0))
      ctx.save()
      ctx.shadowBlur = blur
      ctx.shadowColor = rgba(cr, cg, cb, a * 0.8)
      ctx.fillStyle = g
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    }

    const draw = () => {
      if (!alive) return
      if (!reduced) t += 0.015
      pointer.x = lerp(pointer.x, pointer.tx, 0.05)
      pointer.y = lerp(pointer.y, pointer.ty, 0.05)
      cam.yaw = lerp(cam.yaw, pointer.x * 0.48 + (reduced ? 0 : Math.sin(t * 0.2) * 0.1), 0.08)
      cam.pitch = lerp(cam.pitch, -0.28 + pointer.y * 0.22, 0.08)

      ctx.clearRect(0, 0, w, h)

      // 舞台偏左偏中，夹在品牌与表单之间
      const cx = w < 960 ? w * 0.5 : w * 0.42
      const cy = h * 0.5
      const fl = 720
      const scale = Math.min(w, h) / 780

      const tf = (p: V3) => {
        let q = rx(p, cam.pitch)
        q = ry(q, cam.yaw + (reduced ? 0 : t * 0.18))
        return q
      }

      type Layer =
        | { kind: 'line'; z: number; a: { x: number; y: number }; b: { x: number; y: number }; color: [number, number, number]; alpha: number; width: number }
        | { kind: 'dot'; z: number; x: number; y: number; r: number; color: [number, number, number]; alpha: number; blur?: number }
        | { kind: 'ring'; z: number; pts: { x: number; y: number }[]; color: [number, number, number]; alpha: number }

      const layers: Layer[] = []
      const cyan: [number, number, number] = [34, 211, 238]
      const teal: [number, number, number] = [45, 212, 191]
      const gold: [number, number, number] = [251, 191, 36]
      const blue: [number, number, number] = [56, 189, 248]
      const violet: [number, number, number] = [167, 139, 250]

      // —— 协作核心光晕 ——
      {
        const pulse = 0.55 + Math.sin(t * 1.4) * 0.12
        const core = project(tf({ x: 0, y: 0, z: 0 }), cx, cy, fl)
        const R = 78 * scale * core.s * (1.05 + pulse * 0.15)
        const g = ctx.createRadialGradient(core.x, core.y, 0, core.x, core.y, R * 2.4)
        g.addColorStop(0, rgba(34, 211, 238, 0.35 * pulse))
        g.addColorStop(0.35, rgba(14, 165, 164, 0.16))
        g.addColorStop(0.7, rgba(11, 58, 90, 0.08))
        g.addColorStop(1, 'transparent')
        ctx.fillStyle = g
        ctx.beginPath()
        ctx.arc(core.x, core.y, R * 2.4, 0, Math.PI * 2)
        ctx.fill()

        // 核心环
        for (let i = 0; i < 3; i++) {
          const rr = R * (0.55 + i * 0.28)
          ctx.beginPath()
          ctx.arc(core.x, core.y, rr, 0, Math.PI * 2)
          ctx.strokeStyle = rgba(34, 211, 238, 0.18 - i * 0.04)
          ctx.lineWidth = 1.2
          ctx.stroke()
        }
        glowDot(core.x, core.y, 10 * scale * core.s, cyan, 0.95, 28)
      }

      // —— DNA 双螺旋（医学基因）——
      const helixR = 68 * scale
      const helixH = 420 * scale
      const pairs = 56
      const turns = 3.4
      type Node = ReturnType<typeof project> & { color: [number, number, number] }
      const strandA: Node[] = []
      const strandB: Node[] = []
      for (let i = 0; i < pairs; i++) {
        const p = i / (pairs - 1)
        const y = (p - 0.5) * helixH
        const ang = p * Math.PI * 2 * turns
        const a0 = tf({ x: Math.cos(ang) * helixR, y, z: Math.sin(ang) * helixR })
        const b0 = tf({
          x: Math.cos(ang + Math.PI) * helixR,
          y,
          z: Math.sin(ang + Math.PI) * helixR,
        })
        strandA.push({ ...project(a0, cx, cy, fl), color: i % 2 ? cyan : blue })
        strandB.push({ ...project(b0, cx, cy, fl), color: i % 2 ? gold : teal })
      }
      for (let i = 0; i < pairs; i++) {
        if (i < pairs - 1) {
          layers.push({
            kind: 'line',
            z: (strandA[i].z + strandA[i + 1].z) / 2,
            a: strandA[i],
            b: strandA[i + 1],
            color: cyan,
            alpha: 0.78,
            width: 3.4 * ((strandA[i].s + strandA[i + 1].s) / 2),
          })
          layers.push({
            kind: 'line',
            z: (strandB[i].z + strandB[i + 1].z) / 2,
            a: strandB[i],
            b: strandB[i + 1],
            color: violet,
            alpha: 0.62,
            width: 3.2 * ((strandB[i].s + strandB[i + 1].s) / 2),
          })
        }
        if (i % 2 === 0) {
          layers.push({
            kind: 'line',
            z: (strandA[i].z + strandB[i].z) / 2,
            a: strandA[i],
            b: strandB[i],
            color: gold,
            alpha: 0.48,
            width: 1.8 * ((strandA[i].s + strandB[i].s) / 2),
          })
        }
        layers.push({
          kind: 'dot',
          z: strandA[i].z,
          x: strandA[i].x,
          y: strandA[i].y,
          r: 5.4 * strandA[i].s,
          color: strandA[i].color,
          alpha: 0.95,
        })
        layers.push({
          kind: 'dot',
          z: strandB[i].z,
          x: strandB[i].x,
          y: strandB[i].y,
          r: 5.4 * strandB[i].s,
          color: strandB[i].color,
          alpha: 0.95,
        })
      }

      // —— 智能体节点网络 ——
      const agentPts: { x: number; y: number; z: number; s: number; hue: number }[] = []
      for (const ag of agents) {
        const ang = ag.base + t * 0.35
        const local: V3 = {
          x: Math.cos(ang) * ag.r * scale,
          y: ag.y * scale + Math.sin(t * 0.6 + ag.phase) * 10 * scale,
          z: Math.sin(ang) * ag.r * scale * 0.85,
        }
        const p = project(tf(local), cx, cy, fl)
        agentPts.push({ ...p, hue: ag.hue })
      }
      // 连线：靠近核心的节点连向核心，邻近节点互连
      const coreP = project(tf({ x: 0, y: 0, z: 0 }), cx, cy, fl)
      for (let i = 0; i < agentPts.length; i++) {
        const a = agentPts[i]
        if (i % 2 === 0) {
          layers.push({
            kind: 'line',
            z: (a.z + coreP.z) / 2,
            a: { x: a.x, y: a.y },
            b: { x: coreP.x, y: coreP.y },
            color: a.hue === 0 ? cyan : a.hue === 1 ? teal : gold,
            alpha: 0.12 + ((Math.sin(t * 2 + i) + 1) / 2) * 0.18,
            width: 1,
          })
        }
        const j = (i + 3) % agentPts.length
        const b = agentPts[j]
        layers.push({
          kind: 'line',
          z: (a.z + b.z) / 2,
          a: { x: a.x, y: a.y },
          b: { x: b.x, y: b.y },
          color: cyan,
          alpha: 0.08,
          width: 0.8,
        })
        const color = a.hue === 0 ? cyan : a.hue === 1 ? teal : gold
        layers.push({
          kind: 'dot',
          z: a.z,
          x: a.x,
          y: a.y,
          r: (3.2 + (i % 3)) * a.s,
          color,
          alpha: 0.7 + ((Math.sin(t * 1.8 + i) + 1) / 2) * 0.3,
          blur: 18,
        })
      }

      // —— 三大场景轨道 ——
      const orbits = [
        { r: 175 * scale, tilt: 0.7, color: cyan, speed: 0.42 },
        { r: 215 * scale, tilt: 1.05, color: teal, speed: 0.31 },
        { r: 255 * scale, tilt: 1.35, color: gold, speed: 0.24 },
      ]
      for (let oi = 0; oi < orbits.length; oi++) {
        const o = orbits[oi]
        const pts: { x: number; y: number; z: number }[] = []
        const steps = 72
        for (let i = 0; i <= steps; i++) {
          const a = (i / steps) * Math.PI * 2 + t * o.speed
          const local: V3 = {
            x: Math.cos(a) * o.r,
            y: Math.sin(a) * o.r * Math.sin(o.tilt) * 0.28,
            z: Math.sin(a) * o.r * Math.cos(o.tilt),
          }
          const p = project(tf(local), cx, cy, fl)
          pts.push({ x: p.x, y: p.y, z: p.z })
        }
        const avgZ = pts.reduce((s, p) => s + p.z, 0) / pts.length
        layers.push({
          kind: 'ring',
          z: avgZ,
          pts,
          color: o.color,
          alpha: 0.2,
        })
        // 轨道卫星（场景节点）
        for (let k = 0; k < 2; k++) {
          const a = t * o.speed + (k / 2) * Math.PI * 2 + oi
          const local: V3 = {
            x: Math.cos(a) * o.r,
            y: Math.sin(a) * o.r * Math.sin(o.tilt) * 0.28,
            z: Math.sin(a) * o.r * Math.cos(o.tilt),
          }
          const p = project(tf(local), cx, cy, fl)
          layers.push({
            kind: 'dot',
            z: p.z,
            x: p.x,
            y: p.y,
            r: 5.5 * p.s,
            color: o.color,
            alpha: 0.95,
            blur: 22,
          })
        }
      }

      // —— 数据流粒子 ——
      for (let k = 0; k < 20; k++) {
        const u = (t * 0.22 + k / 20) % 1
        const idx = u * (strandA.length - 1)
        const i0 = Math.floor(idx)
        const i1 = Math.min(strandA.length - 1, i0 + 1)
        const f = idx - i0
        const n0 = k % 2 === 0 ? strandA[i0] : strandB[i0]
        const n1 = k % 2 === 0 ? strandA[i1] : strandB[i1]
        layers.push({
          kind: 'dot',
          z: n0.z + (n1.z - n0.z) * f,
          x: n0.x + (n1.x - n0.x) * f,
          y: n0.y + (n1.y - n0.y) * f,
          r: 2.6 * (n0.s + (n1.s - n0.s) * f),
          color: k % 2 === 0 ? [224, 242, 254] : [254, 243, 199],
          alpha: 0.9,
          blur: 16,
        })
      }

      layers.sort((a, b) => a.z - b.z)
      for (const item of layers) {
        if (item.kind === 'line') {
          ctx.save()
          ctx.beginPath()
          ctx.moveTo(item.a.x, item.a.y)
          ctx.lineTo(item.b.x, item.b.y)
          ctx.strokeStyle = rgba(item.color[0], item.color[1], item.color[2], item.alpha)
          ctx.lineWidth = item.width
          ctx.lineCap = 'round'
          ctx.shadowBlur = 10
          ctx.shadowColor = rgba(item.color[0], item.color[1], item.color[2], item.alpha * 0.7)
          ctx.stroke()
          ctx.restore()
        } else if (item.kind === 'ring') {
          ctx.save()
          ctx.beginPath()
          item.pts.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)))
          ctx.strokeStyle = rgba(item.color[0], item.color[1], item.color[2], item.alpha)
          ctx.lineWidth = 1.2
          ctx.stroke()
          ctx.restore()
        } else {
          glowDot(item.x, item.y, item.r, item.color, item.alpha, item.blur ?? 14)
        }
      }

      // HUD 扫描线（轻量）
      if (!reduced) {
        const scanY = ((t * 40) % (h + 80)) - 40
        const sg = ctx.createLinearGradient(0, scanY - 30, 0, scanY + 30)
        sg.addColorStop(0, 'transparent')
        sg.addColorStop(0.5, rgba(34, 211, 238, 0.06))
        sg.addColorStop(1, 'transparent')
        ctx.fillStyle = sg
        ctx.fillRect(0, scanY - 30, w * 0.62, 60)
      }

      raf = requestAnimationFrame(draw)
    }

    applySize()
    const ro = new ResizeObserver(applySize)
    ro.observe(canvas)
    window.addEventListener('pointermove', onMove, { passive: true })
    raf = requestAnimationFrame(draw)
    return () => {
      alive = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('pointermove', onMove)
    }
  }, [])

  return (
    <div className="login-stage" aria-hidden>
      <div className="login-stage-glow" />
      <canvas ref={canvasRef} className="login-stage-canvas" />
    </div>
  )
}
