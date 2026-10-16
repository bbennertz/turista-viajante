import { duration, fmt } from "./time";
import type { Mode, RouteResult } from "./types";

const WAIT_THRESHOLD = 5; // min: abaixo disso não vale destacar a espera

interface Props {
  result: RouteResult;
  mode: Mode;
  large?: boolean;
}

/** Linha do tempo do dia: saída do hotel, cada parada com a hora de chegada, e a volta. */
export function Timeline({ result, mode, large = false }: Props) {
  const how = mode === "walk" ? "a pé" : "de carro";
  return (
    <ol className={`timeline ${large ? "timeline-large" : ""}`}>
      <li className="tl-hotel">
        <span className="tl-time">{fmt(result.depart ?? 0)}</span>
        <span className="tl-name">Saída do hotel</span>
      </li>
      {result.stops.map((s, i) => {
        const prevLeave = i === 0 ? (result.depart ?? 0) : result.stops[i - 1].leave;
        const wait = s.arrive - prevLeave - s.travel_min;
        return (
          <li key={s.place_id}>
            <div className="tl-leg">
              {s.travel_min} min {how}
              {wait >= WAIT_THRESHOLD && (
                <span className="wait"> · espera {duration(wait)} (abre às {fmt(s.arrive)})</span>
              )}
            </div>
            <span className="tl-time">{fmt(s.arrive)}</span>
            <span className="tl-num">{i + 1}</span>
            <span className="tl-name">
              {s.name}
              <span className="muted small">
                {" "}
                · {duration(s.leave - s.arrive)} (sai às {fmt(s.leave)})
              </span>
            </span>
          </li>
        );
      })}
      <li className="tl-hotel">
        <div className="tl-leg">
          {result.back_travel_min} min {how}
        </div>
        <span className="tl-time">{fmt(result.back ?? 0)}</span>
        <span className="tl-name">Volta ao hotel</span>
      </li>
    </ol>
  );
}
