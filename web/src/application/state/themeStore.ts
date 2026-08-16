import { create } from 'zustand'

const THEME_KEY = 'icore-theme'

export type ThemeMode = 'light' | 'dark'

function readTheme(): ThemeMode {
  try {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

function applyTheme(theme: ThemeMode) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
}

applyTheme(readTheme())

interface ThemeState {
  theme: ThemeMode
  toggleTheme: () => void
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readTheme(),
  toggleTheme: () => {
    const next: ThemeMode = get().theme === 'dark' ? 'light' : 'dark'
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      // 忽略存储不可用
    }
    applyTheme(next)
    set({ theme: next })
  },
}))
