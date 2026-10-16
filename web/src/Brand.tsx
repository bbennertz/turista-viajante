import type { Theme } from "./theme";

/** Marca: um pino de destino ligado por uma rota tracejada ao ponto de partida. */
export function LogoMark() {
  return (
    <svg className="logo" viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
      <defs>
        <linearGradient id="logo-grad" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="var(--sun)" />
          <stop offset="1" stopColor="var(--accent)" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="15" fill="url(#logo-grad)" />
      <path d="M7 23 C 11 23, 11 17, 15 17 S 19 12, 22 11" fill="none" stroke="#fff" strokeWidth="1.8" strokeDasharray="2.2 2.2" strokeLinecap="round" />
      <path d="M22 5.5c-2.6 0-4.5 2-4.5 4.5 0 3.2 4.5 7 4.5 7s4.5-3.8 4.5-7c0-2.5-1.9-4.5-4.5-4.5z" fill="#fff" />
      <circle cx="22" cy="10" r="1.7" fill="var(--accent)" />
    </svg>
  );
}

export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const toLight = theme === "dark";
  return (
    <button
      type="button"
      className="icon-btn theme-toggle"
      onClick={onToggle}
      aria-label={toLight ? "Mudar para o tema claro" : "Mudar para o tema escuro"}
      title={toLight ? "Tema claro" : "Tema escuro"}
    >
      {toLight ? (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}
