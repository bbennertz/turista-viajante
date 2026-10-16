"""Junta candidatos + detalhes + classificação + horários em data/cities/<id>/places.json.

Só entram locais JÁ classificados; o resto é reportado e entra numa próxima execução.
Janelas: chaves de weekday viram str no JSON (0=segunda); `null` = sempre aberto.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.city import CityConfig, _region_of
from pipeline.hours import parse_windows


def merge_city(city_dir: Path) -> dict:
    cfg = CityConfig.load(city_dir / "city.json")
    candidates = json.loads((city_dir / "candidates.json").read_text(encoding="utf-8"))
    places, missing, outside = [], [], []
    for c in candidates:
        if not cfg.contains(c["location"]["latitude"], c["location"]["longitude"]):
            outside.append(c["displayName"]["text"])
            continue
        feat_file = city_dir / "classified" / f"{c['id']}.json"
        det_file = city_dir / "details" / f"{c['id']}.json"
        if not feat_file.exists() or not det_file.exists():
            missing.append(c["id"])
            continue
        feats = json.loads(feat_file.read_text(encoding="utf-8"))
        # `evidence` = trechos de reviews do Google: fica só nos arquivos locais de classificação,
        # nunca em places.json (que vai no repositório público e na imagem Docker)
        feats.pop("evidence", None)
        details = json.loads(det_file.read_text(encoding="utf-8"))
        windows = parse_windows(details.get("regularOpeningHours") or c.get("regularOpeningHours"))
        places.append(
            {
                "id": c["id"],
                "name": c["displayName"]["text"],
                "lat": c["location"]["latitude"],
                "lng": c["location"]["longitude"],
                "region": _region_of(c, cfg),
                "primary_type": c.get("primaryType"),
                "rating": c.get("rating"),
                "n_reviews": c.get("userRatingCount", 0),
                "price_level": c.get("priceLevel"),
                "windows": None
                if windows is None
                else {str(d): [list(iv) for iv in ivs] for d, ivs in windows.items()},
                "features": feats,
            }
        )
    # cobertura: quantos candidatos já foram classificados (o app avisa quando a cidade está parcial)
    classified = sum((city_dir / "classified" / f"{c['id']}.json").exists() for c in candidates)
    (city_dir / "coverage.json").write_text(json.dumps({"candidates": len(candidates), "classified": classified}))
    (city_dir / "places.json").write_text(
        json.dumps(places, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return {"merged": len(places), "missing": len(missing), "outside_bbox": outside, "no_hours": sum(p["windows"] is None for p in places)}


def load_places(city_dir: Path) -> list[dict]:
    return json.loads((city_dir / "places.json").read_text(encoding="utf-8"))
