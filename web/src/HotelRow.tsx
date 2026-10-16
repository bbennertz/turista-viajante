export type HotelSource = "city" | "geo" | "map";

interface Props {
  source: HotelSource;
  busy: boolean;
  message: string | null;
  disabled: boolean;
  onLocate: () => void;
  onReset: () => void;
}

const LABEL: Record<HotelSource, string> = {
  city: "centro da cidade",
  geo: "sua localização",
  map: "ponto escolhido no mapa",
};

/** Ponto de partida. A localização é tentada sozinha ao abrir/trocar de cidade; o botão refaz a tentativa. */
export function HotelRow({ source, busy, message, disabled, onLocate, onReset }: Props) {
  return (
    <div className="hotel-row">
      <div className="hotel-main">
        <button type="button" className="secondary locate-btn" onClick={onLocate} disabled={busy || disabled}>
          {busy ? (
            <span className="spinner" aria-hidden="true" />
          ) : (
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <circle cx="12" cy="12" r="3.5" />
              <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
            </svg>
          )}
          {busy ? "Localizando…" : "Usar minha localização"}
        </button>
        <p className="hotel-status small muted" aria-live="polite">
          Partida: <strong>{LABEL[source]}</strong>
          {source !== "city" && (
            <>
              {" · "}
              <button type="button" className="link" onClick={onReset}>
                voltar ao centro
              </button>
            </>
          )}
        </p>
      </div>
      {message && (
        <p className="hotel-msg small" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
