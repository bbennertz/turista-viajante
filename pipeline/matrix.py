"""Matriz de tempos de deslocamento (minutos inteiros).

Provedores (variável de ambiente ROUTING_PROVIDER; padrão "osrm"):
  - osrm: servidor público do OpenStreetMap (routing.openstreetmap.de), perfis a pé e de carro, sem chave.
          Uso justo: as matrizes das cidades são calculadas offline, uma vez, com ~1 pedido/s.
  - ors:  OpenRouteService (precisa de ORS_API_KEY; a cota da Matrix API é separada e pode esgotar).

A matriz da cidade é calculada em blocos. A linha/coluna do hotel é calculada ao vivo, pois o hotel
muda a cada viagem. Par sem rota (null) vira UNREACHABLE = 1 dia: o solver nunca o usa.
Tempos de provedores diferentes NÃO se misturam: cada arquivo registra seu provedor.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import httpx

from pipeline.env import load_env, require

ORS_URL = "https://api.openrouteservice.org/v2/matrix/{profile}"
ORS_PROFILES = {"walk": "foot-walking", "car": "driving-car"}
OSRM_URL = "https://routing.openstreetmap.de/{service}/table/v1/{profile}/{coords}"
OSRM_PROFILES = {"walk": ("routed-foot", "foot"), "car": ("routed-car", "car")}
USER_AGENT = "turista-viajante/1.0 (personal portfolio project)"
TILE = 50  # 50 origens + 50 destinos = 100 coordenadas por pedido (limite que o OSRM público aceitou)
UNREACHABLE = 24 * 60
PAUSE = {"osrm": 1.1, "ors": 1.6}  # segundos entre pedidos de bloco


def default_provider() -> str:
    load_env()
    provider = os.environ.get("ROUTING_PROVIDER", "osrm").strip().lower()
    if provider not in PAUSE:
        raise ValueError(f"ROUTING_PROVIDER inválido: {provider!r} (use 'osrm' ou 'ors')")
    return provider


def _setup(provider: str | None, key: str | None, pause: float | None):
    provider = provider or default_provider()
    if provider not in PAUSE:
        raise ValueError(f"provedor inválido: {provider!r}")
    if provider == "ors":
        key = key or require("ORS_API_KEY")
    return provider, key or "", PAUSE[provider] if pause is None else pause


def _ors_block(http: httpx.Client, key: str, mode: str, coords, sources, dests) -> list[list]:
    body = {
        "locations": [[lng, lat] for lat, lng in coords],
        "sources": sources,
        "destinations": dests,
        "metrics": ["duration"],
    }
    for attempt in range(5):
        r = http.post(
            ORS_URL.format(profile=ORS_PROFILES[mode]),
            json=body,
            headers={"Authorization": key, "Content-Type": "application/json"},
            timeout=60,
        )
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"ORS {r.status_code}: {r.text[:300]}")
        return r.json()["durations"]
    raise RuntimeError("ORS: limite de taxa persistente")


def _osrm_block(
    http: httpx.Client, _key: str, mode: str, coords, sources, dests, live: bool = False
) -> list[list]:
    """`live`: pedido feito enquanto o usuário espera -> limites curtos (15 s, 2 tentativas)."""
    timeout, attempts = (15, 2) if live else (90, 5)
    service, profile = OSRM_PROFILES[mode]
    url = OSRM_URL.format(
        service=service, profile=profile, coords=";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in coords)
    )
    params = {
        "annotations": "duration",
        "sources": ";".join(map(str, sources)),
        "destinations": ";".join(map(str, dests)),
    }
    last = ""
    for attempt in range(attempts):
        try:
            r = http.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        except httpx.TransportError as e:  # tempo esgotado, conexão derrubada pelo servidor, falha de rede
            last = type(e).__name__
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"OSRM {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM: {data.get('code')}: {data.get('message', '')[:200]}")
        return data["durations"]
    raise RuntimeError(f"OSRM indisponível após {attempts} tentativas ({last})")


def _block(provider: str, http, key: str, mode: str, coords, sources, dests, live: bool = False) -> list[list]:
    if provider == "osrm":
        return _osrm_block(http, key, mode, coords, sources, dests, live)
    return _ors_block(http, key, mode, coords, sources, dests)


def _minutes(seconds) -> int:
    return UNREACHABLE if seconds is None else max(0, math.ceil(seconds / 60))


def city_matrix(
    coords: list[tuple[float, float]], mode: str, http=None, key: str | None = None,
    pause: float | None = None, provider: str | None = None,
) -> list[list[int]]:
    """Matriz N×N em minutos, por blocos. `coords` = [(lat, lng), ...]."""
    provider, key, pause = _setup(provider, key, pause)
    http = http or httpx.Client()
    n = len(coords)
    out = [[0] * n for _ in range(n)]
    for i0 in range(0, n, TILE):
        for j0 in range(0, n, TILE):
            rows, cols = range(i0, min(i0 + TILE, n)), range(j0, min(j0 + TILE, n))
            sub = [coords[i] for i in rows] + [coords[j] for j in cols]
            block = _block(
                provider, http, key, mode, sub,
                list(range(len(rows))), list(range(len(rows), len(rows) + len(cols))),
            )
            for bi, i in enumerate(rows):
                for bj, j in enumerate(cols):
                    out[i][j] = 0 if i == j else _minutes(block[bi][bj])
            time.sleep(pause)
    return out


def save_matrix(
    city_dir: Path, mode: str, ids: list[str], matrix: list[list[int]], provider: str | None = None
) -> None:
    provider = provider or default_provider()
    (city_dir / f"matrix_{mode}.json").write_text(
        json.dumps({"provider": provider, "ids": ids, "minutes": matrix})
    )


def load_matrix(city_dir: Path, mode: str) -> tuple[list[str], list[list[int]]]:
    data = json.loads((city_dir / f"matrix_{mode}.json").read_text())
    return data["ids"], data["minutes"]


def matrix_provider(city_dir: Path, mode: str) -> str | None:
    """Provedor que gerou o arquivo; arquivos antigos, sem o campo, vieram do ORS. None se não existe."""
    file = city_dir / f"matrix_{mode}.json"
    return json.loads(file.read_text()).get("provider", "ors") if file.exists() else None


def hotel_times(
    hotel: tuple[float, float], coords: list[tuple[float, float]], mode: str, http=None,
    key: str | None = None, provider: str | None = None,
) -> tuple[list[int], list[int]]:
    """(hotel -> cada lugar, cada lugar -> hotel), ao vivo."""
    provider, key, _ = _setup(provider, key, None)
    http = http or httpx.Client()
    pts = [hotel, *coords]
    everyone = list(range(len(pts)))
    # UM pedido com a tabela completa (ida e volta de uma vez): o servidor público atrasa pedidos em
    # sequência, e para <= 60 lugares a tabela inteira continua pequena.
    table = _block(provider, http, key, mode, pts, everyone, everyone, live=True)
    return [_minutes(s) for s in table[0][1:]], [_minutes(row[0]) for row in table[1:]]


def pool_travel(
    ids: list[str], matrix: list[list[int]], pool_ids: list[str], to_places: list[int], from_places: list[int]
) -> list[list[int]]:
    """Matriz (n+1)×(n+1) do solver: nó 0 = hotel, nó k = k-ésimo lugar do pool."""
    idx = {pid: i for i, pid in enumerate(ids)}
    n = len(pool_ids)
    t = [[0] * (n + 1) for _ in range(n + 1)]
    for a, pa in enumerate(pool_ids, 1):
        t[0][a], t[a][0] = to_places[a - 1], from_places[a - 1]
        for b, pb in enumerate(pool_ids, 1):
            t[a][b] = matrix[idx[pa]][idx[pb]]
    return t


def proxy_hotel_times(hotel, places: list[dict], ids: list[str], matrix: list[list[int]], pool_ids: list[str]):
    """Sem serviço de rotas (cota/rede): usa a linha/coluna do lugar da cidade mais próximo do hotel.

    Devolve (hotel->lugares, lugares->hotel, nota) com `nota` descrevendo a aproximação."""
    near = min(places, key=lambda p: (p["lat"] - hotel[0]) ** 2 + (p["lng"] - hotel[1]) ** 2)
    col = {pid: k for k, pid in enumerate(ids)}
    i = col[near["id"]]
    to_p = [matrix[i][col[pid]] for pid in pool_ids]
    from_p = [matrix[col[pid]][i] for pid in pool_ids]
    note = (
        f"Tempos de/para o hotel estimados a partir de '{near['name']}', o lugar mais próximo "
        "(serviço de rotas indisponível no momento)."
    )
    return to_p, from_p, note


def _rect(coords_src, coords_dst, mode: str, http, key: str, pause: float, provider: str) -> list[list[int]]:
    """Minutos de cada origem para cada destino, em blocos (sem diagonal especial)."""
    out = [[0] * len(coords_dst) for _ in coords_src]
    for i0 in range(0, len(coords_src), TILE):
        for j0 in range(0, len(coords_dst), TILE):
            rows, cols = coords_src[i0 : i0 + TILE], coords_dst[j0 : j0 + TILE]
            block = _block(
                provider, http, key, mode, rows + cols,
                list(range(len(rows))), list(range(len(rows), len(rows) + len(cols))),
            )
            for bi in range(len(rows)):
                for bj in range(len(cols)):
                    out[i0 + bi][j0 + bj] = _minutes(block[bi][bj])
            time.sleep(pause)
    return out


def extend_matrix(
    old_ids: list[str], old: list[list[int]], ids: list[str], coords: list[tuple[float, float]],
    mode: str, http=None, key: str | None = None, pause: float | None = None, provider: str | None = None,
) -> list[list[int]]:
    """Matriz para `ids` reaproveitando `old`: só consulta o provedor para pares que envolvem lugares novos.

    `old` precisa ter vindo do MESMO provedor (use matrix_provider); lugares que saíram de `ids`
    são descartados; a ordem do resultado segue `ids`."""
    provider, key, pause = _setup(provider, key, pause)
    http = http or httpx.Client()
    known = {pid: k for k, pid in enumerate(old_ids)}
    new_idx = [k for k, pid in enumerate(ids) if pid not in known]
    n = len(ids)
    out = [[0] * n for _ in range(n)]
    for a, pa in enumerate(ids):
        for b, pb in enumerate(ids):
            if pa in known and pb in known:
                out[a][b] = old[known[pa]][known[pb]]
    if new_idx:
        new_coords = [coords[k] for k in new_idx]
        to_new = _rect(coords, new_coords, mode, http, key, pause, provider)  # todos -> novos
        from_new = _rect(new_coords, coords, mode, http, key, pause, provider)  # novos -> todos
        for r, k in enumerate(new_idx):
            for a in range(n):
                out[a][k] = 0 if a == k else to_new[a][r]
                out[k][a] = 0 if a == k else from_new[r][a]
    return out
