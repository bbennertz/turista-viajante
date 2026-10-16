"""v1: o usuário marca lugares numa lista e o solver ordena o dia (TSP com janelas de horário)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

from pipeline.matrix import hotel_times, load_matrix, pool_travel, proxy_hotel_times
from pipeline.merge import load_places
from solver.benders import metric_closure
from solver.model import Place
from solver.tsp import TspInstance, TspResult, solve_tsp

DATA = Path(__file__).resolve().parent.parent / "data" / "cities"


@dataclass
class RouteRequest:
    city: str
    place_ids: list[str]
    hotel: tuple[float, float]  # (lat, lng)
    day: date
    mode: str = "walk"  # "walk" | "car"
    t_start: int = 540  # 09:00
    t_end: int = 1080  # 18:00
    time_limit: float = 30.0


@dataclass
class RouteResult:
    result: TspResult
    names: dict[str, str]
    day: date
    hotel_note: str | None = None
    legs: list[int] = field(default_factory=list)  # min de deslocamento: hotel->1º, ..., último->hotel


def _solver_place(p: dict) -> Place:
    windows = None if p["windows"] is None else {
        int(d): tuple((lo, hi) for lo, hi in ivs) for d, ivs in p["windows"].items()
    }
    return Place(p["id"], int(p["features"]["duration_min"]), windows=windows)


def plan_route(req: RouteRequest, hotel_fn=None) -> RouteResult:
    hotel_fn = hotel_fn or hotel_times  # resolvido na chamada, para os testes poderem trocá-lo
    city_dir = DATA / req.city
    by_id = {p["id"]: p for p in load_places(city_dir)}
    unknown = [pid for pid in req.place_ids if pid not in by_id]
    if unknown:
        raise ValueError(f"lugares desconhecidos: {unknown}")
    chosen = [by_id[pid] for pid in dict.fromkeys(req.place_ids)]  # sem repetidos, mantém a ordem
    ids, matrix = load_matrix(city_dir, req.mode)
    missing = [p["id"] for p in chosen if p["id"] not in set(ids)]
    if missing:
        raise RuntimeError(f"matriz desatualizada, faltam {len(missing)} lugares: refaça o merge e a matriz")

    pool_ids = [p["id"] for p in chosen]
    note = None
    try:
        to_p, from_p = hotel_fn(req.hotel, [(p["lat"], p["lng"]) for p in chosen], req.mode)
    except (RuntimeError, httpx.HTTPError):  # ORS sem cota ou sem rede
        to_p, from_p, note = proxy_hotel_times(req.hotel, list(by_id.values()), ids, matrix, pool_ids)
    travel = pool_travel(ids, matrix, pool_ids, to_p, from_p)
    inst = TspInstance(
        [_solver_place(p) for p in chosen], travel, req.day.weekday(), req.t_start, req.t_end
    )
    names = {p["id"]: p["name"] for p in chosen}
    result = solve_tsp(inst, req.time_limit)
    for pid, name in names.items():  # mensagens do solver citam ids; mostrar nomes
        result.conflicts = [c.replace(f"'{pid}'", f"'{name}'") for c in result.conflicts]
    legs: list[int] = []
    if result.stops:  # os mesmos tempos que o solver usou (com fecho métrico)
        closed = metric_closure(travel)
        idx = {p.id: k for k, p in enumerate(inst.places, 1)}
        seq = [0, *(idx[s.place_id] for s in result.stops), 0]
        legs = [closed[a][b] for a, b in zip(seq, seq[1:])]
    return RouteResult(result, names, req.day, note, legs)


def fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def render(rr: RouteResult) -> str:
    r = rr.result
    head = [f"⚠ {rr.hotel_note}"] if rr.hotel_note else []
    if r.status in ("INFEASIBLE", "UNKNOWN"):
        return "\n".join(head + [f"{r.status}: " + " ".join(r.conflicts or ["sem solução no tempo limite"])])
    lines = head + [
        f"{r.status} · {len(r.stops)} lugares · {r.travel_total} min de deslocamento · "
        f"{fmt(r.depart)} → volta {fmt(r.back)} · {rr.day:%a %d/%m} · {r.elapsed:.1f}s"
    ]
    for s in r.stops:
        lines.append(f"  {fmt(s.arrive)}–{fmt(s.leave)}  {rr.names[s.place_id]}")
    return "\n".join(lines)
