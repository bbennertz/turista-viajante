import type { LatLng } from "./types";

/** Distância em km entre dois pontos (fórmula de haversine). */
export function distanceKm(a: LatLng, b: LatLng): number {
  const rad = (d: number) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}

/** Acima disso, a pessoa claramente não está na cidade escolhida (ilha de Floripa tem ~50 km). */
export const MAX_KM_FROM_CITY = 60;

export type GeoResult =
  | { ok: true; position: LatLng; distance: number }
  | { ok: false; reason: "unsupported" | "denied" | "unavailable" | "timeout" | "far"; message: string; distance?: number };

const MESSAGES = {
  unsupported: "Este navegador não oferece localização. Arraste o marcador H no mapa.",
  denied: "A permissão de localização foi negada. Libere no navegador ou arraste o marcador H no mapa.",
  unavailable: "Não consegui descobrir onde você está. Arraste o marcador H no mapa.",
  timeout: "A localização demorou demais. Tente de novo ou arraste o marcador H no mapa.",
} as const;

/** Pede a posição ao navegador (só quando chamado, nunca sozinho) e valida que ela está perto da cidade. */
export function locate(
  cityCenter: LatLng,
  cityName: string,
  geo: Pick<Geolocation, "getCurrentPosition"> | undefined = typeof navigator !== "undefined" ? navigator.geolocation : undefined,
): Promise<GeoResult> {
  return new Promise((resolve) => {
    if (!geo) return resolve({ ok: false, reason: "unsupported", message: MESSAGES.unsupported });
    geo.getCurrentPosition(
      (p) => {
        const position = { lat: p.coords.latitude, lng: p.coords.longitude };
        const distance = distanceKm(cityCenter, position);
        if (distance > MAX_KM_FROM_CITY) {
          resolve({
            ok: false,
            reason: "far",
            distance,
            message: `Você está a ${Math.round(distance)} km de ${cityName}, longe demais para ser a partida. Arraste o H no mapa para escolher um ponto na cidade.`,
          });
        } else {
          resolve({ ok: true, position, distance });
        }
      },
      (e) => {
        const reason = e.code === 1 ? "denied" : e.code === 3 ? "timeout" : "unavailable";
        resolve({ ok: false, reason, message: MESSAGES[reason] });
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
  });
}
