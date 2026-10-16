export type Mode = "walk" | "car";

export interface City {
  id: string;
  name: string;
  default_mode: Mode;
  center: { lat: number; lng: number };
  regions: string[];
  ready: boolean; // tem lugares e matrizes
  n_places: number;
  partial: boolean; // ainda há lugares sem classificar
}

export interface Place {
  id: string;
  name: string;
  lat: number;
  lng: number;
  region: string;
  rating: number | null;
  n_reviews: number;
  duration_min: number;
  tags: string[];
  open_hours_known: boolean;
}

export interface Stop {
  place_id: string;
  name: string;
  lat: number;
  lng: number;
  arrive: number;
  leave: number;
  travel_min: number;
}

export interface RouteResult {
  status: "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN";
  stops: Stop[];
  depart: number | null;
  back: number | null;
  back_travel_min: number | null;
  travel_total: number | null;
  gap: number | null;
  conflicts: string[];
  hotel_note: string | null;
  elapsed: number;
}

export interface LatLng {
  lat: number;
  lng: number;
}
