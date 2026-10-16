import type { City } from "./types";

interface Props {
  cities: City[];
  currentId: string | undefined;
  onChange: (city: City) => void;
}

/** Escolha da cidade: todas visíveis; as que ainda não têm dados aparecem desabilitadas, com o motivo. */
export function CitySwitch({ cities, currentId, onChange }: Props) {
  return (
    <div className="city-switch" role="radiogroup" aria-label="Cidade">
      {cities.map((c) => (
        <button
          key={c.id}
          type="button"
          role="radio"
          aria-checked={c.id === currentId}
          disabled={!c.ready}
          className={c.id === currentId ? "seg-on" : ""}
          title={c.ready ? `${c.n_places} lugares${c.partial ? " (cobertura parcial)" : ""}` : "Em preparação"}
          onClick={() => onChange(c)}
        >
          <span>{c.name}</span>
          {!c.ready && <span className="soon">em breve</span>}
          {c.ready && c.partial && <span className="soon">parcial</span>}
        </button>
      ))}
    </div>
  );
}
