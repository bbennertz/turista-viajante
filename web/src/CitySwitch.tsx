import type { City } from "./types";

interface Props {
  cities: City[];
  currentId: string | undefined;
  onChange: (city: City) => void;
}

/** Escolha da cidade. Só aparecem as que já têm dados (as demais ficam fora da interface até ficarem prontas). */
export function CitySwitch({ cities, currentId, onChange }: Props) {
  return (
    <div className="city-switch" role="radiogroup" aria-label="Cidade">
      {cities.filter((c) => c.ready).map((c) => (
        <button
          key={c.id}
          type="button"
          role="radio"
          aria-checked={c.id === currentId}
          className={c.id === currentId ? "seg-on" : ""}
          title={`${c.n_places} lugares${c.partial ? " (cobertura parcial)" : ""}`}
          onClick={() => onChange(c)}
        >
          <span>{c.name}</span>
          {c.partial && <span className="soon">parcial</span>}
        </button>
      ))}
    </div>
  );
}
