import { useEffect, useRef, useState } from "react";
import { MapsLinks } from "./MapsLinks";
import { Timeline } from "./Timeline";
import { duration, fmt } from "./time";
import type { LatLng, Mode, RouteResult } from "./types";

interface Props {
  open: boolean;
  result: RouteResult;
  mode: Mode;
  hotel: LatLng;
  day: string; // YYYY-MM-DD
  cityName: string;
  onClose: () => void;
}

function longDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" });
}

function asText(result: RouteResult, mode: Mode, day: string, cityName: string): string {
  const how = mode === "walk" ? "a pé" : "de carro";
  const lines = [`Roteiro em ${cityName} · ${longDate(day)}`, `Saída do hotel: ${fmt(result.depart ?? 0)}`];
  result.stops.forEach((s, i) => {
    lines.push(`${fmt(s.arrive)}  ${i + 1}. ${s.name} (${s.travel_min} min ${how}; fica ${duration(s.leave - s.arrive)})`);
  });
  lines.push(`${fmt(result.back ?? 0)}  Volta ao hotel (${result.back_travel_min} min ${how})`);
  return lines.join("\n");
}

export function RouteModal({ open, result, mode, hotel, day, cityName, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    if (!open) setCopied(null);
  }, [open]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(asText(result, mode, day, cityName));
      setCopied("ok");
    } catch {
      setCopied("fail"); // sem permissão de área de transferência (ex.: http fora de localhost)
    }
  }

  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // clique no fundo escurecido
      }}
    >
      <div className="modal-body">
        <header className="modal-head">
          <div>
            <h2 id="modal-title">Seu roteiro</h2>
            <p className="muted">
              {cityName} · {longDate(day)}
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </header>

        <p className="summary">
          {result.stops.length} lugares · <strong>{duration(result.travel_total ?? 0)}</strong> de deslocamento ·
          volta às <strong>{fmt(result.back ?? 0)}</strong>
          {result.status === "FEASIBLE" && (
            <span className="status status-warn"> bom (até {Math.round((result.gap ?? 0) * 100)}% do ótimo)</span>
          )}
        </p>

        <Timeline result={result} mode={mode} large />

        {result.hotel_note && <p className="muted small">⚠ {result.hotel_note}</p>}

        <footer className="modal-foot">
          <MapsLinks hotel={hotel} stops={result.stops} mode={mode} />
          <button type="button" className="secondary" onClick={copy}>
            {copied === "ok" ? "Copiado ✓" : copied === "fail" ? "Não consegui copiar" : "Copiar como texto"}
          </button>
          <button type="button" className="primary" onClick={onClose}>
            Ver no mapa
          </button>
        </footer>
      </div>
    </dialog>
  );
}
