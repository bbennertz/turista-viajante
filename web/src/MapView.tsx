import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// O Vite empacota o worker do MapLibre e entrega a URL final; sem isso o worker não carrega,
// e os pontos e a linha do roteiro (fontes GeoJSON) nunca são desenhados.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { LatLng, Place, Stop } from "./types";

interface Props {
  cityId?: string;
  places: Place[];
  selected: Set<string>;
  hotel: LatLng;
  stops: Stop[];
  onHotelChange: (p: LatLng) => void;
  onToggle: (id: string) => void;
}

maplibregl.setWorkerUrl(workerUrl);

const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function markerElement(className: string, text: string, title: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  el.textContent = text;
  el.title = title;
  return el;
}

export function MapView({ cityId, places, selected, hotel, stops, onHotelChange, onToggle }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const hotelMarker = useRef<maplibregl.Marker | null>(null);
  const stopMarkers = useRef<maplibregl.Marker[]>([]);
  const fitted = useRef(false);
  const lastCity = useRef<string | undefined>(undefined);
  const [ready, setReady] = useState(false);

  // Callbacks sempre atuais, sem recriar o mapa.
  const handlers = useRef({ onToggle, onHotelChange });
  handlers.current = { onToggle, onHotelChange };

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: OSM_STYLE,
      center: [hotel.lng, hotel.lat],
      zoom: 11,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });

    map.on("load", () => {
      map.addSource("places", { type: "geojson", data: EMPTY });
      map.addSource("route", { type: "geojson", data: EMPTY });
      map.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        paint: { "line-color": "#2563eb", "line-width": 4, "line-opacity": 0.85, "line-dasharray": [2, 1.5] },
      });
      map.addLayer({
        id: "places",
        type: "circle",
        source: "places",
        paint: {
          "circle-color": ["case", ["get", "selected"], "#2563eb", "#64748b"],
          "circle-radius": ["case", ["get", "selected"], 8, 5],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
          "circle-opacity": ["case", ["get", "selected"], 1, 0.75],
        },
      });
      map.on("click", "places", (e) => {
        const id = e.features?.[0]?.properties?.id as string | undefined;
        if (id) handlers.current.onToggle(id);
      });
      map.on("mousemove", "places", (e) => {
        map.getCanvas().style.cursor = "pointer";
        const f = e.features?.[0];
        if (!f || f.geometry.type !== "Point") return;
        popup
          .setLngLat(f.geometry.coordinates as [number, number])
          .setText(String(f.properties?.name))
          .addTo(map);
      });
      map.on("mouseleave", "places", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      setReady(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
    // O mapa é criado uma vez; o centro inicial vem do hotel na montagem.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Pontos dos lugares (cor/tamanho conforme marcados).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const data: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: places.map((p) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [p.lng, p.lat] },
        properties: { id: p.id, name: p.name, selected: selected.has(p.id) },
      })),
    };
    (map.getSource("places") as maplibregl.GeoJSONSource).setData(data);
    if (lastCity.current !== cityId && places.length > 0) {
      lastCity.current = cityId;
      fitted.current = false; // trocou de cidade: reenquadra o mapa nos lugares novos
    }
    if (!fitted.current && places.length > 0) {
      const b = new maplibregl.LngLatBounds();
      places.forEach((p) => b.extend([p.lng, p.lat]));
      map.fitBounds(b, { padding: 50, duration: 0 });
      fitted.current = true;
    }
  }, [ready, cityId, places, selected]);

  // Marcador do hotel, arrastável.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!hotelMarker.current) {
      const marker = new maplibregl.Marker({
        element: markerElement("marker marker-hotel", "H", "Hotel: arraste para mudar"),
        draggable: true,
      })
        .setLngLat([hotel.lng, hotel.lat])
        .addTo(map);
      marker.on("dragend", () => {
        const { lat, lng } = marker.getLngLat();
        handlers.current.onHotelChange({ lat, lng });
      });
      hotelMarker.current = marker;
    } else {
      const cur = hotelMarker.current.getLngLat();
      const moved = Math.abs(cur.lng - hotel.lng) > 1e-7 || Math.abs(cur.lat - hotel.lat) > 1e-7;
      hotelMarker.current.setLngLat([hotel.lng, hotel.lat]);
      // Mudança vinda de fora (localização, "voltar ao centro"): leva o mapa até o hotel.
      // No arraste o marcador já está na posição nova, então não mexe no mapa.
      if (moved) map.easeTo({ center: [hotel.lng, hotel.lat], zoom: Math.max(map.getZoom(), 13), duration: 600 });
    }
  }, [ready, hotel]);

  // Roteiro: linha hotel -> paradas -> hotel e marcadores numerados.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    stopMarkers.current.forEach((m) => m.remove());
    stopMarkers.current = [];
    const line: GeoJSON.FeatureCollection =
      stops.length === 0
        ? EMPTY
        : {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: {},
                geometry: {
                  type: "LineString",
                  coordinates: [
                    [hotel.lng, hotel.lat],
                    ...stops.map((s) => [s.lng, s.lat]),
                    [hotel.lng, hotel.lat],
                  ],
                },
              },
            ],
          };
    (map.getSource("route") as maplibregl.GeoJSONSource).setData(line);
    stops.forEach((s, i) => {
      stopMarkers.current.push(
        new maplibregl.Marker({ element: markerElement("marker marker-stop", String(i + 1), s.name) })
          .setLngLat([s.lng, s.lat])
          .addTo(map),
      );
    });
    if (stops.length > 0) {
      const b = new maplibregl.LngLatBounds([hotel.lng, hotel.lat], [hotel.lng, hotel.lat]);
      stops.forEach((s) => b.extend([s.lng, s.lat]));
      map.fitBounds(b, { padding: { top: 70, bottom: 70, left: 70, right: 70 }, duration: 600, maxZoom: 15 });
    }
    // O hotel muda a linha só quando o roteiro é recalculado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, stops]);

  return <div ref={container} className="map" role="application" aria-label="Mapa dos lugares" />;
}
