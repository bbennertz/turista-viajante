"""Pipeline completo de uma cidade, retomável: descoberta -> detalhes -> classificação -> merge.
Uso: python scripts/build_city.py <cidade> [collect]   (a cidade precisa de data/cities/<cidade>/city.json)

Cada etapa pula o que já existe em disco. A matriz de tempos fica de fora (depende da cota do ORS):
depois rode scripts/refresh_matrices.py <cidade>."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.agent import run_discovery  # noqa: E402
from pipeline.city import CityConfig  # noqa: E402
from pipeline.classify import classify_all  # noqa: E402
from pipeline.details import fetch_all  # noqa: E402
from pipeline.merge import merge_city  # noqa: E402
from pipeline.places import PlacesClient  # noqa: E402

city_dir = Path(__file__).resolve().parent.parent / "data" / "cities" / sys.argv[1]
cfg = CityConfig.load(city_dir / "city.json")
client = PlacesClient()

if not (city_dir / "candidates.json").exists():
    final = run_discovery(cfg, client, city_dir)
    print(f"descoberta: {len(final['places'])} candidatos em {final['searches_used']} buscas", flush=True)
else:
    print("descoberta: já feita", flush=True)

candidates = json.loads((city_dir / "candidates.json").read_text(encoding="utf-8"))
print("detalhes:", fetch_all(client, candidates, city_dir, cfg.language), flush=True)

if len(sys.argv) > 2 and sys.argv[2] == "collect":  # só coleta (Google); a classificação fica para depois
    print("coleta concluída; classificação adiada", flush=True)
    sys.exit(0)

for attempt in range(1, 13):  # a cota diária de tokens da Groq pode exigir esperar
    counts = classify_all(city_dir)
    print(f"classificação, passada {attempt}: {counts}", flush=True)
    if counts["failed"] == 0:
        break
    time.sleep(600)

print("merge:", {k: (len(v) if k == "outside_bbox" else v) for k, v in merge_city(city_dir).items()}, flush=True)
