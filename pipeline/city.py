"""Configuração da cidade e geografia: sem dependências de LLM, para a API e o merge usarem."""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import BaseModel, Field


class Region(BaseModel):
    name: str
    lat: float
    lng: float
    radius_m: float


class CityConfig(BaseModel):
    id: str
    name: str
    language: str
    seed_query: str
    default_mode: str = "walk"
    max_searches: int = 30
    target_candidates: int = 250
    min_reviews: int = 20
    # mínimo de candidatos por tipo antes de a meta total valer
    min_per_bucket: dict[str, int] = Field(
        default_factory=lambda: {"comida": 30, "natureza": 30, "cultura": 30, "icone": 30}
    )
    # (lat_min, lat_max, lng_min, lng_max): descarta lugares fora da área turística da cidade.
    # O viés de localização do Google é só uma preferência e deixa passar outras cidades.
    bbox: tuple[float, float, float, float] | None = None
    regions: list[Region]

    def contains(self, lat: float, lng: float) -> bool:
        if self.bbox is None:
            return True
        lat_min, lat_max, lng_min, lng_max = self.bbox
        return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max

    @classmethod
    def load(cls, path: Path) -> "CityConfig":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi, dlmb = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _region_of(place: dict, cfg: CityConfig) -> str:
    loc = place["location"]
    here = (loc["latitude"], loc["longitude"])
    return min(cfg.regions, key=lambda r: _haversine_km(here, (r.lat, r.lng))).name
