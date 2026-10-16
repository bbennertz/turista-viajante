import type { City, LatLng, Mode, Place, RouteResult } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* corpo não é JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const getCities = () => request<City[]>("/api/cities");

export const getPlaces = (city: string) => request<Place[]>(`/api/cities/${city}/places`);

export interface RouteParams {
  city: string;
  placeIds: string[];
  hotel: LatLng;
  day: string; // YYYY-MM-DD
  mode: Mode;
  tStart: string; // HH:MM
  tEnd: string;
}

export const planRoute = (p: RouteParams) =>
  request<RouteResult>(`/api/cities/${p.city}/route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      place_ids: p.placeIds,
      hotel_lat: p.hotel.lat,
      hotel_lng: p.hotel.lng,
      day: p.day,
      mode: p.mode,
      t_start: p.tStart,
      t_end: p.tEnd,
    }),
  });
