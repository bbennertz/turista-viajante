"""Atualiza as matrizes a pé e de carro de uma cidade.
Uso: python scripts/refresh_matrices.py <cidade> [full]

- Só consulta o provedor (ROUTING_PROVIDER, padrão osrm) para lugares novos.
- Se a matriz existente veio de OUTRO provedor, ou se passar "full", reconstrói tudo: tempos de provedores
  diferentes não se misturam na mesma cidade.
- Só grava as duas matrizes se AMBAS derem certo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.matrix import (  # noqa: E402
    city_matrix, default_provider, extend_matrix, load_matrix, matrix_provider, save_matrix,
)
from pipeline.merge import load_places  # noqa: E402

city = Path(__file__).resolve().parent.parent / "data" / "cities" / sys.argv[1]
force_full = len(sys.argv) > 2 and sys.argv[2] == "full"
provider = default_provider()
places = load_places(city)
ids, coords = [p["id"] for p in places], [(p["lat"], p["lng"]) for p in places]
done = {}
for mode in ("walk", "car"):
    old_provider = matrix_provider(city, mode)
    if force_full or old_provider != provider:
        why = "pedido" if force_full else f"provedor mudou ({old_provider} -> {provider})" if old_provider else "não existe"
        print(f"{mode}: reconstruindo {len(ids)} lugares ({why}), provedor {provider}", flush=True)
        done[mode] = city_matrix(coords, mode, provider=provider)
    else:
        old_ids, old = load_matrix(city, mode)
        new = [i for i in ids if i not in set(old_ids)]
        print(f"{mode}: {len(new)} lugares novos de {len(ids)}, provedor {provider}", flush=True)
        done[mode] = extend_matrix(old_ids, old, ids, coords, mode, provider=provider)
for mode, m in done.items():
    save_matrix(city, mode, ids, m, provider=provider)
print("matrizes atualizadas:", len(ids), "lugares, provedor", provider)
