"""Classifica todos os candidatos de uma cidade (retomável). Uso: python scripts/classify_city.py <cidade>

Se o limite diário de tokens (TPD) da Groq estourar, tenta de novo a cada 10 min: a janela é
móvel e libera tokens aos poucos. Cada passada pula o que já foi classificado."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.classify import classify_all  # noqa: E402

city = Path(__file__).resolve().parent.parent / "data" / "cities" / sys.argv[1]
for attempt in range(1, 13):
    t = time.time()
    counts = classify_all(city)
    print(f"passada {attempt}: {counts} em {time.time() - t:.0f}s", flush=True)
    if counts["failed"] == 0:
        break
    time.sleep(600)
