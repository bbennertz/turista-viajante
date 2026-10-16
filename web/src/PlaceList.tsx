import { useMemo, useState } from "react";
import { duration } from "./time";
import type { Place } from "./types";

interface Props {
  places: Place[];
  selected: Set<string>;
  regions: string[];
  onToggle: (id: string) => void;
  onClear: () => void;
  loading: boolean;
}

export function PlaceList({ places, selected, regions, onToggle, onClear, loading }: Props) {
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState("");
  const [tag, setTag] = useState("");
  const [onlySelected, setOnlySelected] = useState(false);

  const topTags = useMemo(() => {
    const counts = new Map<string, number>();
    places.forEach((p) => p.tags.forEach((t) => counts.set(t, (counts.get(t) ?? 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).map(([t]) => t);
  }, [places]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return places.filter(
      (p) =>
        (!q || p.name.toLowerCase().includes(q)) &&
        (!region || p.region === region) &&
        (!tag || p.tags.includes(tag)) &&
        (!onlySelected || selected.has(p.id)),
    );
  }, [places, query, region, tag, onlySelected, selected]);

  const filtered = query !== "" || region !== "" || tag !== "" || onlySelected;
  const clearFilters = () => {
    setQuery("");
    setRegion("");
    setTag("");
    setOnlySelected(false);
  };

  return (
    <div className="places-pane">
      <div className="filters-sticky">
        <div className="filters">
          <input
            type="search"
            placeholder="Buscar por nome"
            aria-label="Buscar por nome"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select aria-label="Região" value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">Todas as regiões</option>
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div className="chips" role="group" aria-label="Filtrar por tag">
          {topTags.map((t) => (
            <button
              key={t}
              type="button"
              className={`chip ${tag === t ? "chip-on" : ""}`}
              aria-pressed={tag === t}
              onClick={() => setTag(tag === t ? "" : t)}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="list-tools small">
          <label className="inline">
            <input type="checkbox" checked={onlySelected} onChange={(e) => setOnlySelected(e.target.checked)} />
            só marcados
          </label>
          <span className="muted" aria-live="polite">
            {loading ? "carregando…" : filtered ? `${visible.length} de ${places.length} lugares` : `${places.length} lugares`}
          </span>
          <button type="button" className="link" onClick={onClear} disabled={selected.size === 0}>
            desmarcar todos
          </button>
        </div>
      </div>

      <ul className="places">
        {visible.map((p) => (
          <li key={p.id}>
            <label className={`place ${selected.has(p.id) ? "place-on" : ""}`}>
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => onToggle(p.id)} />
              <span className="place-body">
                <span className="place-name">{p.name}</span>
                <span className="muted small">
                  {p.region.split(" (")[0]}
                  {p.rating ? ` · ★ ${p.rating.toFixed(1)}` : ""} · {duration(p.duration_min)}
                  {p.open_hours_known ? "" : " · sempre aberto"}
                </span>
                <span className="tags">
                  {p.tags.slice(0, 3).map((t) => (
                    <span key={t} className="tag">
                      {t}
                    </span>
                  ))}
                </span>
              </span>
            </label>
          </li>
        ))}
        {loading && (
          <li className="empty" role="status">
            <span className="spinner" aria-hidden="true" /> Carregando lugares…
          </li>
        )}
        {!loading && visible.length === 0 && (
          <li className="empty">
            <p>Nenhum lugar com esses filtros.</p>
            <button type="button" className="secondary" onClick={clearFilters}>
              Limpar filtros
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}
