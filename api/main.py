"""API HTTP da v1: lista de lugares (checkbox) e roteiro de um dia (TSP com janelas de horário).

Em produção serve também o front buildado (web/dist). Em desenvolvimento o Vite faz proxy de /api.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from api.places import DATA, list_places
from api.route import RouteRequest, plan_route

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"

app = FastAPI(title="Turista Viajante", version="1.0")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class RouteIn(BaseModel):
    place_ids: list[str] = Field(min_length=1, max_length=60)
    hotel_lat: float = Field(ge=-90, le=90)
    hotel_lng: float = Field(ge=-180, le=180)
    day: date
    mode: Literal["walk", "car"] = "walk"
    t_start: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    t_end: str = Field(default="18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def _window(self):
        if _minutes(self.t_end) - _minutes(self.t_start) < 30:
            raise ValueError("a janela do dia precisa ter pelo menos 30 minutos")
        return self


def _city_dir(city: str) -> Path:
    path = (DATA / city).resolve()
    if DATA.resolve() not in path.parents or not (path / "places.json").exists():
        raise HTTPException(404, f"cidade desconhecida: {city}")
    return path


@app.get("/api/cities")
def cities() -> list[dict]:
    """Todas as cidades configuradas. `ready` = tem lugares E matrizes; as demais aparecem como 'em preparação'."""
    out = []
    for d in sorted(DATA.iterdir()):
        if not (d / "city.json").exists():
            continue
        cfg = json.loads((d / "city.json").read_text(encoding="utf-8"))
        n_places = len(list_places(d.name)) if (d / "places.json").exists() else 0
        cov_file = d / "coverage.json"
        cov = json.loads(cov_file.read_text()) if cov_file.exists() else None
        out.append(
            {
                "id": cfg["id"],
                "name": cfg["name"],
                "default_mode": cfg.get("default_mode", "walk"),
                "center": {"lat": cfg["regions"][0]["lat"], "lng": cfg["regions"][0]["lng"]},
                "regions": [r["name"] for r in cfg["regions"]],
                "ready": n_places > 0,
                "n_places": n_places,
                # cidade com lugares ainda sem classificar: a lista é só uma parte do que existe
                "partial": bool(cov) and cov["classified"] < cov["candidates"],
            }
        )
    return out


@app.get("/api/cities/{city}/places")
def places(city: str, include_food: bool = False) -> list[dict]:
    _city_dir(city)
    return list_places(city, include_food=include_food)


@app.post("/api/cities/{city}/route")
def route(city: str, body: RouteIn) -> dict:
    _city_dir(city)
    try:
        rr = plan_route(
            RouteRequest(
                city,
                body.place_ids,
                (body.hotel_lat, body.hotel_lng),
                body.day,
                body.mode,
                _minutes(body.t_start),
                _minutes(body.t_end),
            )
        )
    except ValueError as e:  # ids desconhecidos
        raise HTTPException(422, str(e)) from e
    r = rr.result
    by_id = {p["id"]: p for p in list_places(city, include_food=True)}
    stops = []
    for k, s in enumerate(r.stops):
        p = by_id[s.place_id]
        stops.append(
            {
                "place_id": s.place_id,
                "name": p["name"],
                "lat": p["lat"],
                "lng": p["lng"],
                "arrive": s.arrive,
                "leave": s.leave,
                "travel_min": rr.legs[k],
            }
        )
    return {
        "status": r.status,
        "stops": stops,
        "depart": r.depart,
        "back": r.back,
        "back_travel_min": rr.legs[-1] if rr.legs else None,
        "travel_total": r.travel_total,
        "gap": r.gap,
        "conflicts": r.conflicts,
        "hotel_note": rr.hotel_note,
        "elapsed": round(r.elapsed, 2),
    }


if DIST.exists():  # front buildado
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "rota da API inexistente")
        file = (DIST / path).resolve()
        return FileResponse(file if file.is_file() and DIST.resolve() in file.parents else DIST / "index.html")
