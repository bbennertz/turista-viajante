import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "tv-theme";
const query = typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: dark)") : null;

function readPreference(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null; // armazenamento bloqueado (janela privada etc.): segue o sistema
  }
}

/** Tema efetivo: a escolha do usuário (guardada no navegador) ou, sem escolha, a do sistema. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [pref, setPref] = useState<Theme | null>(readPreference);
  const [systemDark, setSystemDark] = useState(query?.matches ?? false);

  useEffect(() => {
    if (!query) return;
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const theme: Theme = pref ?? (systemDark ? "dark" : "light");

  // O CSS usa data-theme quando há escolha explícita; sem ela vale a media query do sistema.
  useEffect(() => {
    const el = document.documentElement;
    if (pref) el.dataset.theme = pref;
    else delete el.dataset.theme;
  }, [pref]);

  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setPref(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* sem armazenamento: vale só nesta sessão */
    }
  }, [theme]);

  return { theme, toggle };
}
