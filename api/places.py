"""Lista de lugares para a UI (checkbox). As tags vêm da classificação por LLM e ficam nos lugares;
a v1 não usa estilos nem pontuação: o usuário escolhe os lugares e o solver só roteia."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.merge import load_places

DATA = Path(__file__).resolve().parent.parent / "data" / "cities"
FOOD_CATEGORIES = {"restaurante", "cafe_padaria", "bar"}
TAG_THRESHOLD = 0.7
FEATURE_TAGS = {
    "landmark": "cartão-postal", "nature": "natureza", "culture": "cultura",
    "authenticity": "autêntico", "touristy": "turístico",
}


def is_food(place: dict) -> bool:
    f = place["features"]
    return bool(f["is_dining"]) or f.get("category") in FOOD_CATEGORIES


def tags_of(place: dict) -> list[str]:
    f = place["features"]
    tags = [f["category"].replace("_", " ")]
    tags += [label for key, label in FEATURE_TAGS.items() if f[key] >= TAG_THRESHOLD]
    tags.append("pago" if f["is_paid"] else "gratuito")
    tags.append({"indoor": "interno", "outdoor": "ao ar livre", "mixed": "misto"}[f["setting"]])
    return tags


def routable_ids(city: str) -> set[str]:
    """Lugares cobertos por TODAS as matrizes existentes. Um lugar novo (já no places.json) só
    aparece na lista depois que as matrizes são refeitas, senão o roteiro dele daria erro."""
    sets = []
    for mode in ("walk", "car"):
        file = DATA / city / f"matrix_{mode}.json"
        if file.exists():
            sets.append(set(json.loads(file.read_text())["ids"]))
    return set.intersection(*sets) if sets else set()


def list_places(city: str, include_food: bool = False) -> list[dict]:
    rows = []
    ok = routable_ids(city)
    for p in load_places(DATA / city):
        if p["id"] not in ok or (not include_food and is_food(p)):
            continue
        f = p["features"]
        rows.append(
            {
                "id": p["id"], "name": p["name"], "lat": p["lat"], "lng": p["lng"],
                "region": p["region"], "rating": p["rating"], "n_reviews": p["n_reviews"],
                "duration_min": f["duration_min"], "tags": tags_of(p), "open_hours_known": p["windows"] is not None,
            }
        )
    return sorted(rows, key=lambda r: -r["n_reviews"])
