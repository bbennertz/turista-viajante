"""Busca Place Details (reviews, resumo editorial, horários) de cada candidato.

Retomável: cada local vira `details/<place_id>.json` assim que chega, e uma nova
execução pula os que já existem, então uma queda não gasta a cota duas vezes.
"""

from __future__ import annotations

import json
from pathlib import Path


def fetch_all(client, candidates: list[dict], out_dir: Path, language: str = "en") -> dict:
    """Devolve contagens {fetched, skipped, failed}. Erros de rede não interrompem o lote;
    `BudgetExceeded` interrompe (propaga) porque nenhuma chamada seguinte seria permitida."""
    from pipeline.places import BudgetExceeded

    details_dir = out_dir / "details"
    details_dir.mkdir(parents=True, exist_ok=True)
    counts = {"fetched": 0, "skipped": 0, "failed": 0}
    for place in candidates:
        target = details_dir / f"{place['id']}.json"
        if target.exists():
            counts["skipped"] += 1
            continue
        try:
            data = client.details(place["id"], language)
        except BudgetExceeded:
            raise
        except RuntimeError as e:
            counts["failed"] += 1
            print(f"falhou {place['id']}: {e}")
            continue
        target.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        counts["fetched"] += 1
    return counts
