// iCore Tailwind CSS 配置
// Author: OneKeyJune <onekeyjune@gmail.com>
//
// shadcn/ui 标准模板 + 医学工作台调色板：
//   - primary  深海蓝 #0b3a5a   严肃 / 主品牌
//   - accent   临床青 #0fa3b1   高亮 / 链接
//   - warning  警示橙 #ff8c42   提醒 / 风险
// 全部颜色统一走 CSS variable，方便后续做暗色主题。

import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '1rem',
      screens: { '2xl': '1400px' },
    },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar))',
          foreground: 'hsl(var(--sidebar-foreground))',
          muted: 'hsl(var(--sidebar-muted))',
          'active-bg': 'hsl(var(--sidebar-active-bg))',
          'active-fg': 'hsl(var(--sidebar-active-fg))',
          border: 'hsl(var(--sidebar-border))',
        },
        'card-muted': 'hsl(var(--card-muted))',
      },
      fontFamily: {
        // 西文走 Inter（细节圆润、x-height 高），中文走 Noto Sans SC（笔画柔和，明显比
        // PingFang/微软雅黑更"温润"）。两者一起用时浏览器会按字符自动选字体，避免老的
        // 系统 fallback（如默认 sans 在 Windows 下退到 Segoe UI/微软雅黑）让中文看起来生硬。
        sans: [
          '"Inter"',
          '"Noto Sans SC"',
          '"PingFang SC"',
          '"HarmonyOS Sans SC"',
          '"Source Han Sans SC"',
          '"Microsoft YaHei"',
          'system-ui',
          'sans-serif',
        ],
        mono: [
          '"JetBrains Mono"',
          '"Cascadia Code"',
          '"Fira Code"',
          'Consolas',
          'monospace',
        ],
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        'card-hover': 'var(--shadow-card-hover)',
        pop: 'var(--shadow-pop)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        'caret-blink': {
          '0%,70%,100%': { opacity: '1' },
          '20%,50%': { opacity: '0' },
        },
        // OneKey 风格：流式光标"淡入淡出"而非闪烁 —— 0.3 ↔ 0.9 透明度往复
        'stream-cursor-fade': {
          '0%, 100%': { opacity: '0.3' },
          '50%': { opacity: '0.9' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'caret-blink': 'caret-blink 1s ease-out infinite',
        'stream-cursor': 'stream-cursor-fade 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [animate],
}

export default config
