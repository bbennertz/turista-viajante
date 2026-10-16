import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCities, getPlaces, planRoute } from "./api";
import { LogoMark, ThemeToggle } from "./Brand";
import { CitySwitch } from "./CitySwitch";
import { locate } from "./geo";
import { HotelRow, type HotelSource } from "./HotelRow";
import { MapView } from "./MapView";
import { PlaceList } from "./PlaceList";
import { ResultPanel } from "./ResultPanel";
import { RouteModal } from "./RouteModal";
import { useTheme } from "./theme";
import { duration, toMinutes, tomorrow } from "./time";
import type { City, LatLng, Mode, Place, RouteResult } from "./types";

type Tab = "places" | "route";

const BLOCKED =
  "Localização bloqueada: usando o centro da cidade. Libere a permissão no navegador ou arraste o H no mapa.";

/** Entradas usadas no último cálculo: o resultado exibido não muda se o usuário mexer nos controles depois. */
interface Snapshot {
  hotel: LatLng;
  mode: Mode;
  day: string;
}

export default function App() {
  const { theme, toggle: toggleTheme } = useTheme();
  const [cities, setCities] = useState<City[]>([]);
  const [city, setCity] = useState<City | null>(null);
  const [places, setPlaces] = useState<Place[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [hotel, setHotel] = useState<LatLng>({ lat: -27.59, lng: -48.55 });
  const [hotelSource, setHotelSource] = useState<HotelSource>("city");
  const [geoBusy, setGeoBusy] = useState(false);
  const [geoMessage, setGeoMessage] = useState<string | null>(null);
  const geoDenied = useRef(false); // se o usuário negou a permissão, não pergunta de novo sozinho
  const currentCityId = useRef<string | null>(null);
  const [day, setDay] = useState(tomorrow());
  const [tStart, setTStart] = useState("09:00");
  const [tEnd, setTEnd] = useState("18:00");
  const [mode, setMode] = useState<Mode>("walk");
  const [tab, setTab] = useState<Tab>("places");
  const [result, setResult] = useState<RouteResult | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [stale, setStale] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [placesLoading, setPlacesLoading] = useState(true);
  // Em telas grandes o formulário do dia começa aberto; em telas pequenas, resumido para dar espaço à lista.
  const [dayOpen, setDayOpen] = useState(() => window.matchMedia("(min-width: 821px) and (min-height: 761px)").matches);
  const [modalOpen, setModalOpen] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    getCities()
      .then((list) => {
        setCities(list);
        const first = list.find((c) => c.ready);
        if (first) chooseCity(first);
      })
      .catch((e: Error) => setLoadError(`Não consegui carregar as cidades: ${e.message}`));
  }, []);

  function chooseCity(c: City) {
    setCity(c);
    setHotel(c.center);
    setHotelSource("city");
    setGeoMessage(null);
    currentCityId.current = c.id;
    void useLocation(c, false);
    setMode(c.default_mode);
    setSelected(new Set());
    setResult(null);
    setSnapshot(null);
    setError(null);
    setStale(false);
    setTab("places");
    setPlaces([]);
    setPlacesLoading(true);
    getPlaces(c.id)
      .then(setPlaces)
      .catch((e: Error) => setLoadError(`Não consegui carregar os lugares: ${e.message}`))
      .finally(() => setPlacesLoading(false));
  }

  /** Usa a posição do navegador como partida. `manual`: clique no botão (pergunta mesmo após uma negação anterior). */
  async function useLocation(c: City | null, manual: boolean) {
    if (!c) return;
    if (!manual && geoDenied.current) {
      setGeoMessage(BLOCKED);
      return;
    }
    setGeoBusy(true);
    const r = await locate(c.center, c.name);
    if (currentCityId.current !== c.id) return; // o usuário já trocou de cidade: descarta a resposta
    setGeoBusy(false);
    if (r.ok) {
      geoDenied.current = false;
      setGeoMessage(null);
      setHotel(r.position);
      setHotelSource("geo");
      setStale(true);
    } else {
      if (r.reason === "denied") geoDenied.current = true;
      setGeoMessage(r.reason === "denied" && !manual ? BLOCKED : r.message);
    }
  }

  const touch = () => setStale(true); // qualquer mudança de entrada invalida o roteiro exibido

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
    setStale(true);
  }, []);

  const windowMin = toMinutes(tEnd) - toMinutes(tStart);
  const visitMin = useMemo(
    () => places.filter((p) => selected.has(p.id)).reduce((sum, p) => sum + p.duration_min, 0),
    [places, selected],
  );
  const windowOk = windowMin >= 30;
  const overVisits = windowOk && visitMin > windowMin;
  const canSubmit = selected.size > 0 && windowOk && !loading;

  async function submit() {
    if (!city || !canSubmit) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setTab("route"); // mostra o progresso onde o resultado vai aparecer
    try {
      const r = await planRoute({ city: city.id, placeIds: [...selected], hotel, day, mode, tStart, tEnd });
      if (id !== requestId.current) return; // chegou uma resposta mais nova
      setResult(r);
      setSnapshot({ hotel, mode, day });
      setStale(false);
      setModalOpen(r.status === "OPTIMAL" || r.status === "FEASIBLE");
    } catch (e) {
      if (id !== requestId.current) return;
      setResult(null);
      setSnapshot(null);
      setError((e as Error).message);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  const feasible = result !== null && (result.status === "OPTIMAL" || result.status === "FEASIBLE");
  const stops = feasible ? result.stops : [];
  const shown = snapshot ?? { hotel, mode, day };

  const [y, m, d] = day.split("-").map(Number);
  const daySummary = `${new Date(y, m - 1, d).toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" })} · ${tStart}–${tEnd} · ${mode === "walk" ? "a pé" : "de carro"}`;

  const meterText =
    selected.size === 0
      ? "Marque ao menos um lugar"
      : !windowOk
        ? "A janela do dia precisa ter ao menos 30 min"
        : `Visitas: ${duration(visitMin)} de ${duration(windowMin)} do dia, sem contar o deslocamento`;

  function onTabKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") setTab(tab === "places" ? "route" : "places");
  }

  return (
    <div className="app">
      <section className="panel" aria-label="Planejador">
        <header className="topbar">
          <div className="brand">
            <LogoMark />
            <h1>Turista Viajante</h1>
          </div>
          <CitySwitch cities={cities} currentId={city?.id} onChange={chooseCity} />
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          
        </header>

        {loadError && (
          <div className="notice notice-bad" role="alert">
            {loadError}
          </div>
        )}

        <section className="day" aria-label="Seu dia">
          <button
            type="button"
            className="day-summary"
            aria-expanded={dayOpen}
            aria-controls="day-fields"
            onClick={() => setDayOpen((o) => !o)}
          >
            <span className="day-summary-text">{daySummary}</span>
            <span className="day-toggle">{dayOpen ? "Ocultar" : "Alterar"}</span>
          </button>
          <div id="day-fields" hidden={!dayOpen}>
          <div className="day-row">
              <label className="field">
                Data
                <input type="date" value={day} onChange={(e) => { setDay(e.target.value); touch(); }} />
              </label>
              <label className="field">
                Saída
                <input type="time" value={tStart} onChange={(e) => { setTStart(e.target.value); touch(); }} />
              </label>
              <label className="field">
                Volta até
                <input type="time" value={tEnd} onChange={(e) => { setTEnd(e.target.value); touch(); }} />
              </label>
            </div>
            <div className="day-row2">
              <div className="segmented" role="radiogroup" aria-label="Como se desloca">
                {(["walk", "car"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={mode === m}
                    className={mode === m ? "seg-on" : ""}
                    onClick={() => { setMode(m); touch(); }}
                  >
                    {m === "walk" ? "A pé" : "De carro"}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        <HotelRow
          source={hotelSource}
          busy={geoBusy}
          message={geoMessage}
          disabled={!city}
          onLocate={() => void useLocation(city, true)}
          onReset={() => {
            if (city) {
              setHotel(city.center);
              setHotelSource("city");
              setGeoMessage(null);
              touch();
            }
          }}
        />

        <div className="tabs" role="tablist" aria-label="Etapas" onKeyDown={onTabKey}>
          <button
            type="button"
            role="tab"
            id="tab-places"
            aria-selected={tab === "places"}
            aria-controls="panel-places"
            tabIndex={tab === "places" ? 0 : -1}
            onClick={() => setTab("places")}
          >
            Lugares <span className="count">{selected.size}</span>
          </button>
          <button
            type="button"
            role="tab"
            id="tab-route"
            aria-selected={tab === "route"}
            aria-controls="panel-route"
            tabIndex={tab === "route" ? 0 : -1}
            onClick={() => setTab("route")}
          >
            Roteiro {stale && result && <span className="dot-stale" title="Desatualizado" />}
          </button>
        </div>

        <div className="tab-body" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          {tab === "places" ? (
            <>
              {city?.partial && (
                <div className="notice notice-warn" role="note">
                  Cobertura parcial: ainda estamos classificando os lugares de {city.name}, então esta lista é só uma
                  parte do que existe lá.
                </div>
              )}
              <PlaceList
              places={places}
              selected={selected}
              regions={city?.regions ?? []}
              onToggle={toggle}
              onClear={() => { setSelected(new Set()); touch(); }}
              loading={placesLoading}
            />
            </>
          ) : (
            <>
              {stale && result && !loading && (
                <div className="notice notice-warn">
                  Você mudou a lista ou o dia. Clique em “Montar roteiro” para recalcular.
                </div>
              )}
              {!result && !error && !loading ? (
                <div className="empty-state">
                  <p>
                    <strong>Seu roteiro aparece aqui.</strong>
                  </p>
                  <p className="muted">
                    Marque os lugares que quer visitar, ajuste o dia e clique em “Montar roteiro”. O app encontra a
                    ordem que gasta menos tempo andando, saindo e voltando ao hotel.
                  </p>
                  <button type="button" className="secondary" onClick={() => setTab("places")}>
                    Escolher lugares
                  </button>
                </div>
              ) : (
                <ResultPanel
                  result={result}
                  error={error}
                  loading={loading}
                  mode={shown.mode}
                  hotel={shown.hotel}
                  onOpenModal={() => setModalOpen(true)}
                />
              )}
            </>
          )}
        </div>

        <footer className="submit-bar">
          <div className={`meter ${overVisits ? "meter-bad" : ""}`} aria-live="polite">
            <div className="meter-track">
              <div
                className="meter-fill"
                style={{ width: `${Math.min(100, windowOk ? (visitMin / windowMin) * 100 : 0)}%` }}
              />
            </div>
            <span className="small">{meterText}</span>
          </div>
          <button type="button" className="primary" disabled={!canSubmit} onClick={submit}>
            {loading ? (
              <>
                <span className="spinner" aria-hidden="true" /> Calculando…
              </>
            ) : selected.size > 0 ? (
              `Montar roteiro · ${selected.size} ${selected.size === 1 ? "lugar" : "lugares"}`
            ) : (
              "Montar roteiro"
            )}
          </button>
        </footer>
      </section>

      {result && stops.length > 0 && (
        <RouteModal
          open={modalOpen}
          result={result}
          mode={shown.mode}
          hotel={shown.hotel}
          day={shown.day}
          cityName={city?.name ?? ""}
          onClose={() => setModalOpen(false)}
        />
      )}

      <main className="map-col">
        <div className="map-wrap">
          <MapView
            theme={theme}
            cityId={city?.id}
            places={places}
            selected={selected}
            hotel={hotel}
            stops={stops}
            onHotelChange={(p) => {
              setHotel(p);
              setHotelSource("map");
              touch();
            }}
            onToggle={toggle}
          />
        </div>
        <p className="map-caption small muted">
          <span><i className="legend-dot legend-on" /> marcado</span>
          <span><i className="legend-dot" /> disponível</span>
          <span>Clique num ponto para marcar · arraste o <span className="dot-h">H</span> para mudar o hotel · a linha mostra a ordem, não as ruas.</span>
        </p>
      </main>
    </div>
  );
}
