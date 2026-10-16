"""Orquestra um pedido de roteiro: pool por estilo -> matriz com hotel -> solver."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import httpx

from pipeline.city import _haversine_km
from pipeline.matrix import hotel_times, load_matrix, pool_travel
from pipeline.merge import load_places
from solver.benders import solve_decomposed
from solver.model import Result
from solver.scoring import PoolSpec, build_instance, select_pool

DATA = Path(__file__).resolve().parent.parent / "data" / "cities"


@dataclass
class Request:
    city: str
    preset: str
    hotel: tuple[float, float]  # (lat, lng)
    start_date: date
    n_days: int
    per_day: int
    mode: str = "walk"
    t_start: int = 540  # 09:00
    t_end: int = 1140  # 19:00
    exclude: set[str] = field(default_factory=set)
    mandatory: dict[str, int | None] = field(default_factory=dict)  # id -> dia fixo (0-based) ou None
    free_only: bool = False
    budget: float | None = None
    weights: dict[str, float] | None = None
    time_limit: float = 30.0


@dataclass
class Itinerary:
    result: Result
    pool: list[dict]
    dates: list[date]
    names: dict[str, str]
    pool_seconds: float = 0.0
    hotel_note: str | None = None  # preenchido quando o hotel é aproximado


def _proxy_hotel(hotel, places, ids, matrix, pool) -> tuple[list[int], list[int], str]:
    """Sem ORS: usa a linha/coluna do lugar da cidade mais próximo do hotel como aproximação."""
    near = min(places, key=lambda p: _haversine_km(hotel, (p["lat"], p["lng"])))
    i = ids.index(near["id"])
    col = {pid: k for k, pid in enumerate(ids)}
    to_p = [matrix[i][col[p["id"]]] for p in pool]
    from_p = [matrix[col[p["id"]]][i] for p in pool]
    km = _haversine_km(hotel, (near["lat"], near["lng"]))
    return to_p, from_p, f"hotel aproximado pelo lugar mais próximo: {near['name']} ({km:.1f} km)"


def plan_itinerary(req: Request, hotel_fn=hotel_times) -> Itinerary:
    city_dir = DATA / req.city
    places = load_places(city_dir)
    spec = PoolSpec(
        req.preset, req.per_day, req.n_days, exclude=set(req.exclude),
        mandatory=set(req.mandatory), free_only=req.free_only, weights=req.weights,
    )
    pool = select_pool(places, spec)
    ids, matrix = load_matrix(city_dir, req.mode)
    missing = [p["id"] for p in pool if p["id"] not in set(ids)]
    if missing:
        raise RuntimeError(f"matriz desatualizada, faltam {len(missing)} lugares: rode o merge e a matriz")
    note = None
    try:
        to_p, from_p = hotel_fn(req.hotel, [(p["lat"], p["lng"]) for p in pool], req.mode)
    except (RuntimeError, httpx.HTTPError):  # ORS sem cota ou sem rede
        to_p, from_p, note = _proxy_hotel(req.hotel, places, ids, matrix, pool)
    travel = pool_travel(ids, matrix, [p["id"] for p in pool], to_p, from_p)
    dates = [req.start_date + timedelta(days=i) for i in range(req.n_days)]
    inst = build_instance(
        pool, travel, [d.weekday() for d in dates], req.per_day,
        t_start=req.t_start, t_end=req.t_end,
        mandatory=dict(req.mandatory), budget=req.budget,
    )
    t = time.monotonic()
    result = solve_decomposed(inst, time_limit=req.time_limit)
    return Itinerary(result, pool, dates, {p["id"]: p["name"] for p in pool}, time.monotonic() - t, note)


def fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def render(it: Itinerary) -> str:
    r = it.result
    if r.status in ("INFEASIBLE", "UNKNOWN") or not r.days:
        return f"{r.status}: " + "; ".join(r.conflicts or ["sem solução no tempo limite"])
    by_id = {p["id"]: p for p in it.pool}
    lines = ([f"⚠ {it.hotel_note}"] if it.hotel_note else []) + [f"{r.status} · deslocamento total {r.travel_total} min · score {r.stage2} · término {r.stage3} · {r.elapsed:.1f}s"]
    for dp in r.days:
        lines.append(f"\nDia {dp.day + 1} ({it.dates[dp.day]:%a %d/%m}) · {dp.travel} min de deslocamento · volta {fmt(dp.back)}")
        for s in dp.stops:
            p = by_id[s.place_id]
            tag = " [REFEIÇÃO]" if p["features"]["is_dining"] else ""
            lines.append(f"  {fmt(s.arrive)}–{fmt(s.leave)}  {it.names[s.place_id][:44]:44} ({p['region'][:12]}){tag}")
    return "\n".join(lines)
