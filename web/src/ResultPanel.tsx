import { MapsLinks } from "./MapsLinks";
import { Timeline } from "./Timeline";
import { duration, fmt } from "./time";
import type { LatLng, Mode, RouteResult } from "./types";

interface Props {
  result: RouteResult | null;
  error: string | null;
  loading: boolean;
  mode: Mode;
  hotel: LatLng;
  onOpenModal: () => void;
}

export function ResultPanel({ result, error, loading, mode, hotel, onOpenModal }: Props) {
  if (loading) {
    return (
      <section className="result" aria-live="polite">
        <h2>Roteiro</h2>
        <p className="muted">Calculando o melhor roteiro… pode levar até 30 segundos.</p>
      </section>
    );
  }
  if (error) {
    return (
      <section className="result" role="alert">
        <h2>Roteiro</h2>
        <div className="notice notice-bad">{error}</div>
      </section>
    );
  }
  if (!result) return null;

  if (result.status === "INFEASIBLE" || result.status === "UNKNOWN") {
    return (
      <section className="result" role="alert">
        <h2>Roteiro</h2>
        <div className="notice notice-bad">
          <strong>{result.status === "INFEASIBLE" ? "Não cabe no dia" : "Não encontrei uma solução a tempo"}</strong>
          {result.conflicts.length > 0 ? (
            <ul>
              {result.conflicts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            <p>
              A lista está no limite da janela e o solver não conseguiu decidir em 30 s. Tire um ou dois lugares ou
              alargue o horário do dia.
            </p>
          )}
        </div>
        {result.hotel_note && <p className="muted small">⚠ {result.hotel_note}</p>}
      </section>
    );
  }

  const how = mode === "walk" ? "a pé" : "de carro";
  return (
    <section className="result" aria-live="polite">
      <div className="card-head">
        <h2>Roteiro</h2>
        <span className={`status status-${result.status === "OPTIMAL" ? "ok" : "warn"}`}>
          {result.status === "OPTIMAL"
            ? "ótimo"
            : `bom (até ${Math.round((result.gap ?? 0) * 100)}% do ótimo)`}
        </span>
      </div>
      <p className="summary">
        {result.stops.length} lugares · <strong>{duration(result.travel_total ?? 0)}</strong> de deslocamento {how}
        {" · "}volta às <strong>{fmt(result.back ?? 0)}</strong>
      </p>

      <Timeline result={result} mode={mode} />
      <div className="actions">
        <button type="button" className="secondary" onClick={onOpenModal}>
          Ver em tela cheia
        </button>
        <MapsLinks hotel={hotel} stops={result.stops} mode={mode} />
      </div>
      {result.hotel_note && <p className="muted small">⚠ {result.hotel_note}</p>}
    </section>
  );
}
