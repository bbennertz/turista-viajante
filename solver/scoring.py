"""Presets de estilo, pontuação e seleção do pool top-K que alimenta o solver.

O estilo decide O QUE pode entrar (pool); o solver decide a ordem e o tempo.
score_i = w_preset · features_i + w_pop · popularidade_i, normalizado para [0, 1] na cidade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from solver.model import Instance, Place

FEATURES = ("authenticity", "touristy", "gastronomy", "culture", "nature", "landmark")

# Pesos por estilo. `pop` pesa a popularidade (nota × log do nº de avaliações).
PRESETS: dict[str, dict[str, float]] = {
    "primeira_vez": {"landmark": 1.0, "culture": 0.3, "nature": 0.2, "touristy": 0.2, "pop": 0.6},
    "ar_livre": {"nature": 1.0, "landmark": 0.3, "authenticity": 0.2, "touristy": -0.2, "pop": 0.2},
}

# Fora desta versão (sem restaurantes, o estilo "Bourdain" perde o centro): guardado para a v2.
DISABLED_PRESETS: dict[str, dict[str, float]] = {
    "como_um_local": {
        "authenticity": 1.0, "touristy": -0.8, "gastronomy": 0.4, "culture": 0.2,
        "landmark": -0.2, "pop": 0.05,
    },
}

# Categorias de comida/bebida: ficam fora do roteiro nesta versão.
FOOD_CATEGORIES = {"restaurante", "cafe_padaria", "bar"}


def is_food(place: dict) -> bool:
    f = place["features"]
    return bool(f["is_dining"]) or f.get("category") in FOOD_CATEGORIES


def popularity(places: list[dict]) -> dict[str, float]:
    """rating × log(1 + n_reviews), normalizado em [0, 1] dentro da cidade."""
    raw = {p["id"]: (p.get("rating") or 0) * math.log1p(p.get("n_reviews", 0)) for p in places}
    hi = max(raw.values(), default=1) or 1
    return {k: v / hi for k, v in raw.items()}


def score_places(places: list[dict], preset: str, weights: dict[str, float] | None = None) -> dict[str, float]:
    w = weights or PRESETS[preset]
    pop = popularity(places)
    raw = {
        p["id"]: sum(w.get(f, 0.0) * p["features"][f] for f in FEATURES) + w.get("pop", 0.0) * pop[p["id"]]
        for p in places
    }
    lo, hi = min(raw.values(), default=0), max(raw.values(), default=1)
    span = (hi - lo) or 1.0
    return {k: (v - lo) / span for k, v in raw.items()}


@dataclass
class PoolSpec:
    preset: str
    per_day: int
    n_days: int
    exclude: set[str] = field(default_factory=set)  # "já visitei"
    mandatory: set[str] = field(default_factory=set)
    free_only: bool = False
    allow_food: bool = False  # restaurantes/cafés/bares fora do pool (obrigatórios continuam valendo)
    max_dining_share: float = 0.25  # o solver só aceita 1 refeição/dia: não deixar comida dominar
    k_cap: int = 60
    weights: dict[str, float] | None = None


def select_pool(places: list[dict], spec: PoolSpec) -> list[dict]:
    """Top-K por score, com teto de refeições e obrigatórios garantidos (fora da cota)."""
    scores = score_places(places, spec.preset, spec.weights)
    k = min(3 * spec.per_day * spec.n_days, spec.k_cap)
    eligible = [
        p for p in places
        if p["id"] not in spec.exclude
        and not (spec.free_only and p["features"]["is_paid"])
        and (spec.allow_food or p["id"] in spec.mandatory or not is_food(p))
    ]
    pool = [p for p in eligible if p["id"] in spec.mandatory]
    taken = {p["id"] for p in pool}
    dining_cap = math.ceil(spec.max_dining_share * k)
    dining = sum(p["features"]["is_dining"] for p in pool)
    for p in sorted(eligible, key=lambda p: -scores[p["id"]]):
        if len(pool) >= k:
            break
        if p["id"] in taken:
            continue
        if p["features"]["is_dining"]:
            if dining >= dining_cap:
                continue
            dining += 1
        pool.append(p)
        taken.add(p["id"])
    for p in pool:
        p["_score"] = scores[p["id"]]
    return pool


def to_solver_places(pool: list[dict]) -> list[Place]:
    out = []
    for p in pool:
        f = p["features"]
        windows = None if p["windows"] is None else {
            int(d): tuple((lo, hi) for lo, hi in ivs) for d, ivs in p["windows"].items()
        }
        out.append(
            Place(
                id=p["id"],
                duration=int(f["duration_min"]),
                score=float(p["_score"]),
                price=float(f.get("est_price_brl") or 0.0),
                is_dining=bool(f["is_dining"]),
                windows=windows,
            )
        )
    return out


def build_instance(
    pool: list[dict],
    travel: list[list[int]],
    weekdays: list[int],
    per_day: int,
    **kwargs,
) -> Instance:
    return Instance(to_solver_places(pool), travel, weekdays, per_day, **kwargs)
