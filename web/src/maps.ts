import type { LatLng, Mode, Stop } from "./types";

// A URL de direções do Google Maps aceita no máximo 9 paradas intermediárias por link.
export const MAX_WAYPOINTS = 9;

const pt = (p: LatLng) => `${p.lat.toFixed(6)},${p.lng.toFixed(6)}`;

/**
 * Links do Google Maps para o dia: hotel -> paradas na ordem do solver -> hotel.
 * Com mais de 9 paradas, divide em partes encadeadas (cada parte começa onde a anterior termina).
 */
export function googleMapsLinks(hotel: LatLng, stops: Pick<Stop, "lat" | "lng">[], mode: Mode): string[] {
  if (stops.length === 0) return [];
  const points: LatLng[] = [hotel, ...stops, hotel];
  const travelmode = mode === "walk" ? "walking" : "driving";
  const links: string[] = [];
  for (let start = 0; start < points.length - 1; start += MAX_WAYPOINTS + 1) {
    const end = Math.min(start + MAX_WAYPOINTS + 1, points.length - 1);
    const middle = points.slice(start + 1, end);
    const params = new URLSearchParams({
      api: "1",
      origin: pt(points[start]),
      destination: pt(points[end]),
      travelmode,
    });
    if (middle.length > 0) params.set("waypoints", middle.map(pt).join("|"));
    links.push(`https://www.google.com/maps/dir/?${params.toString()}`);
  }
  return links;
}
