// 日 / 夜模式切换。state 优先级：localStorage > prefers-color-scheme > 默认 dark。
//
// 主题变化时把 .dark class 写在 <html> 上（match Tailwind v4 的 @custom-variant dark
// (&:is(.dark *))）。配合 index.html `<head>` 里的 inline script 在 React mount 前
// 就把 class 设好，避免首屏一闪 light 再切 dark 的 FOUC。

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";
const STORAGE_KEY = "theme";

function detectInitial(): Theme {
  if (typeof localStorage !== "undefined") {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  }
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "dark";
}

interface Ctx {
  theme:    Theme;
  setTheme: (t: Theme) => void;
  toggle:   () => void;
}

const ThemeContext = createContext<Ctx>({
  theme: "dark",
  setTheme: () => {},
  toggle: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(detectInitial);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* ignore quota / private mode */ }
  }, [theme]);

  return (
    <ThemeContext.Provider value={{
      theme,
      setTheme,
      toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
