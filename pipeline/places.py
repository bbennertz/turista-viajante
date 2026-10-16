"""Cliente da Google Places API (New) com livro-caixa de chamadas por faixa de cobrança.

Cada chamada paga é registrada em data/ledger.json ANTES de ser feita e é bloqueada
(`BudgetExceeded`) quando a faixa do mês atinge o teto, abaixo da cota grátis de
1.000/mês de Text Search Enterprise e Place Details + Atmosphere.

ATENÇÃO: a página de preços do Google não mapeia campo -> faixa. A atribuição abaixo
(rating/horários na busca = Enterprise; reviews/editorialSummary nos detalhes =
Enterprise + Atmosphere) é a suposição conservadora; confira no relatório de uso do
Cloud Console e ajuste LIMITS se a cobrança divergir.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import httpx

from pipeline.env import ROOT, require

BASE = "https://places.googleapis.com/v1"

SEARCH_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
        "places.primaryType",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.regularOpeningHours",
        "places.businessStatus",
        "nextPageToken",
    ]
)
DETAILS_MASK = ",".join(
    [
        "id",
        "displayName",
        "rating",
        "userRatingCount",
        "priceLevel",
        "regularOpeningHours",
        "editorialSummary",
        "reviews",
        "types",
        "primaryType",
    ]
)

SEARCH_TIER = "search_enterprise"
DETAILS_TIER = "details_atmosphere"
LIMITS = {SEARCH_TIER: 800, DETAILS_TIER: 800}  # teto/mês, abaixo dos 1.000 grátis


class BudgetExceeded(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: Path | None = None, limits: dict[str, int] | None = None):
        self.path = path or ROOT / "data" / "ledger.json"
        self.limits = limits or LIMITS

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def used(self, tier: str) -> int:
        return self._load().get(date.today().strftime("%Y-%m"), {}).get(tier, 0)

    def charge(self, tier: str) -> None:
        data = self._load()
        month = data.setdefault(date.today().strftime("%Y-%m"), {})
        if month.get(tier, 0) >= self.limits[tier]:
            raise BudgetExceeded(f"{tier}: teto de {self.limits[tier]} chamadas/mês atingido")
        month[tier] = month.get(tier, 0) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))


class PlacesClient:
    def __init__(
        self,
        api_key: str | None = None,
        ledger: Ledger | None = None,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key or require("GOOGLE_PLACES_API_KEY")
        self.ledger = ledger or Ledger()
        self.http = client or httpx.Client(timeout=30)

    def _request(self, method: str, url: str, mask: str, **kwargs) -> dict:
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": mask}
        for attempt in range(4):
            resp = self.http.request(method, url, headers=headers, **kwargs)
            if resp.status_code in (429, 500, 503):
                time.sleep(2**attempt)
                continue
            if resp.status_code >= 400:
                # a mensagem do Google não contém a chave; o cabeçalho nunca é impresso
                raise RuntimeError(f"Places API {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        raise RuntimeError("Places API indisponível após 4 tentativas")

    def text_search(
        self,
        query: str,
        *,
        center: tuple[float, float],
        radius_m: float,
        language: str = "en",
        max_pages: int = 1,
    ) -> list[dict]:
        """Até 20 lugares por página, com viés de localização circular."""
        body: dict = {
            "textQuery": query,
            "languageCode": language,
            "pageSize": 20,
            "locationBias": {
                "circle": {
                    "center": {"latitude": center[0], "longitude": center[1]},
                    "radius": radius_m,
                }
            },
        }
        places: list[dict] = []
        for _ in range(max_pages):
            self.ledger.charge(SEARCH_TIER)
            data = self._request("POST", f"{BASE}/places:searchText", SEARCH_MASK, json=body)
            places += data.get("places", [])
            if not data.get("nextPageToken"):
                break
            body["pageToken"] = data["nextPageToken"]
        return places

    def details(self, place_id: str, language: str = "en") -> dict:
        self.ledger.charge(DETAILS_TIER)
        return self._request(
            "GET", f"{BASE}/places/{place_id}", DETAILS_MASK, params={"languageCode": language}
        )
