"""Agente de descoberta (LangGraph): decide QUAIS buscas fazer no Google Places.

Grafo:  seed ─► plan ─► search ─► plan ─► … ─► END
- seed:   uma busca genérica por região (cobertura mínima garantida).
- plan:   o LLM vê o que já foi coletado (por região, por tipo, cauda longa) e propõe
          as próximas buscas, ou decide parar. Nó determinístico impõe os limites.
- search: executa as buscas, deduplica por place_id e filtra lixo.
O LLM decide O QUÊ buscar; o orçamento (max_searches), a deduplicação e a regra de
parada mínima são código, para o custo ser previsível.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from pipeline.city import CityConfig, Region, _haversine_km, _region_of  # noqa: F401
from pipeline.llm import AGENT_MODEL, ask_json, get_llm

MAX_PER_ROUND = 4
MAX_ROUNDS = 15
LONG_TAIL_REVIEWS = 300  # abaixo disso o lugar conta como "cauda longa" (pouco turístico)

BLOCKED_TYPES = {
    "lodging", "real_estate_agency", "insurance_agency", "car_dealer", "car_repair",
    "car_rental", "gas_station", "parking", "atm", "bank", "doctor", "dentist", "hospital",
    "pharmacy", "school", "lawyer", "moving_company", "storage", "funeral_home",
    "travel_agency", "accounting", "electrician", "plumber", "locksmith",
}
# Ruído de buscas fora de foco. Vale só para o tipo PRINCIPAL: "store"/"school"/"service"
# aparecem na lista de tipos de padarias e mercados legítimos, então não dá para bloquear por lista.
NOISE_PRIMARY_TYPES = {
    "sports_school", "association_or_organization", "educational_institution", "consultant",
    "corporate_office", "research_institute", "television_studio", "service", "store",
    "gift_shop", "book_store", "school", "university",
}
BUCKETS = {
    "comida": {"restaurant", "cafe", "bar", "bakery", "meal_takeaway", "food", "market", "pub",
               "brazilian_restaurant", "seafood_restaurant", "ice_cream_shop", "coffee_shop"},
    "natureza": {"park", "beach", "natural_feature", "hiking_area", "campground", "scenic_spot",
                 "national_park", "garden", "marina", "wildlife_park"},
    "cultura": {"museum", "church", "historical_landmark", "art_gallery", "cultural_landmark",
                "monument", "place_of_worship", "library", "performing_arts_theater",
                "cultural_center", "philharmonic_hall", "event_venue"},
}
# "Ícone" = marco turístico pelo tipo OU muito popular (e não restaurante). É um proxy só para
# guiar a cobertura da busca; a classificação de verdade (feature `landmark`) é feita pelo LLM.
ICON_TYPES = {"tourist_attraction", "bridge", "amusement_park", "zoo", "aquarium", "observation_deck"}
ICON_MIN_REVIEWS = 3000


class Proposal(BaseModel):
    region: str = Field(description="Nome EXATO de uma das regiões listadas")
    query: str = Field(description="Texto da busca no Google Maps, no idioma local")
    why: str = Field(description="Que lacuna de cobertura esta busca preenche")


class Plan(BaseModel):
    queries: list[Proposal] = Field(default_factory=list, max_length=MAX_PER_ROUND)
    stop: bool = False
    reason: str = ""


class State(TypedDict):
    places: dict[str, dict]
    done: list[tuple[str, str]]  # (região, query) já executadas
    log: list[dict]
    pending: list[Proposal]
    searches_used: int
    rounds: int
    stop: bool


def _bucket(place: dict) -> str:
    types = set(place.get("types", [])) | {place.get("primaryType")}
    popular = place.get("userRatingCount", 0) >= ICON_MIN_REVIEWS
    if types & ICON_TYPES or (popular and not types & BUCKETS["comida"]):
        return "icone"
    for name, members in BUCKETS.items():
        if types & members:
            return name
    return "outros"


def shortfalls(state: State, cfg: CityConfig) -> dict[str, int]:
    """Quanto falta para cada tipo atingir o mínimo (só os que faltam)."""
    have = Counter(_bucket(p) for p in state["places"].values())
    return {k: m - have.get(k, 0) for k, m in cfg.min_per_bucket.items() if have.get(k, 0) < m}


def summarize(state: State, cfg: CityConfig) -> str:
    places = list(state["places"].values())
    by_region = Counter(_region_of(p, cfg) for p in places)
    by_bucket = Counter(_bucket(p) for p in places)
    tail = [p for p in places if p.get("userRatingCount", 0) < LONG_TAIL_REVIEWS]
    obscure = sorted(tail, key=lambda p: p.get("userRatingCount", 0))[:12]
    lines = [
        f"Candidatos únicos: {len(places)} (meta {cfg.target_candidates}); "
        f"cauda longa (<{LONG_TAIL_REVIEWS} avaliações): {len(tail)}",
        "Por região: " + "; ".join(f"{r.name}: {by_region.get(r.name, 0)}" for r in cfg.regions),
        "Por tipo: " + "; ".join(f"{k}: {v}" for k, v in sorted(by_bucket.items())),
        f"(tipo 'icone' = marco turístico ou lugar não-restaurante com {ICON_MIN_REVIEWS}+ avaliações: "
        "ícones são por definição conhecidos, não busque 'ícones pouco conhecidos')",
        "Mínimo por tipo: " + "; ".join(f"{k} ≥ {m}" for k, m in cfg.min_per_bucket.items()),
        "FALTAM (priorize estes tipos): "
        + ("; ".join(f"{k}: {n}" for k, n in shortfalls(state, cfg).items()) or "nada, cobertura mínima ok"),
        f"Buscas usadas: {state['searches_used']}/{cfg.max_searches}",
        "Buscas já feitas: " + " | ".join(f"{q} @ {r}" for r, q in state["done"][-30:]),
        "Alguns lugares pouco conhecidos já achados: "
        + ", ".join(p["displayName"]["text"] for p in obscure),
    ]
    return "\n".join(lines)


SYSTEM = (
    "Você coordena a coleta de lugares de {city} para um roteirizador turístico com três "
    "estilos: 'Primeira vez' (ícones e cartões-postais), 'Como um local' (lugares autênticos, "
    "mercados, bares e padarias de bairro, comida como experiência, sem turistão) e 'Ar livre' "
    "(praias, trilhas, parques, mirantes). Você escolhe as próximas buscas no Google Maps para "
    "cobrir TODAS as regiões e os três estilos, com atenção especial a lugares pouco turísticos, "
    "que a busca por popularidade não mostra. Regiões válidas: {regions}. "
    "Escreva as buscas no idioma local ({lang}). Proponha no máximo {k} buscas NOVAS por rodada, "
    "cada uma ligada a uma região e a uma lacuna concreta de cobertura. "
    "Marque stop=true apenas quando a cobertura por região e por estilo estiver boa."
)


def _default_planner(cfg: CityConfig, model: str) -> Callable[[str], Plan]:
    llm = get_llm(model)
    system = SYSTEM.format(
        city=cfg.name, regions="; ".join(r.name for r in cfg.regions), lang=cfg.language, k=MAX_PER_ROUND
    )
    return lambda summary: ask_json(llm, Plan, system, summary)


def build_graph(cfg: CityConfig, client, planner: Callable[[str], Plan]):
    regions = {r.name: r for r in cfg.regions}

    def execute(state: State, proposals: list[tuple[str, str, str]]) -> dict:
        places, done, log, used = dict(state["places"]), list(state["done"]), list(state["log"]), state["searches_used"]
        for region_name, query, why in proposals:
            r = regions[region_name]
            found = client.text_search(
                query, center=(r.lat, r.lng), radius_m=r.radius_m, language=cfg.language
            )
            used += 1
            done.append((region_name, query))
            new = 0
            for p in found:
                if p["id"] in places or not _keep(p, cfg):
                    continue
                p["found_by"] = {"query": query, "region": region_name}
                places[p["id"]] = p
                new += 1
            log.append({"round": state["rounds"], "region": region_name, "query": query,
                        "why": why, "returned": len(found), "new": new, "total": len(places)})
        return {"places": places, "done": done, "log": log, "searches_used": used}

    def seed(state: State) -> dict:
        seeds = [(r.name, cfg.seed_query.format(region=r.name), "cobertura mínima da região")
                 for r in cfg.regions]
        return execute(state, seeds)

    def plan(state: State) -> dict:
        left = cfg.max_searches - state["searches_used"]
        covered = not shortfalls(state, cfg)
        if left <= 0 or state["rounds"] >= MAX_ROUNDS:
            return {"stop": True, "pending": []}
        if len(state["places"]) >= cfg.target_candidates and covered:
            return {"stop": True, "pending": []}
        proposal = planner(summarize(state, cfg))
        seen = set(state["done"])
        pending, taken = [], set()
        for p in proposal.queries:  # o código, não o LLM, impõe validade e orçamento
            key = (p.region, p.query.strip().lower())
            if p.region in regions and key not in taken and (p.region, p.query) not in seen:
                pending.append(p)
                taken.add(key)
        pending = pending[: min(left, MAX_PER_ROUND)]
        stop = (
            proposal.stop and covered and len(state["places"]) >= cfg.target_candidates * 0.6
        ) or not pending
        return {"pending": pending, "stop": stop, "rounds": state["rounds"] + 1}

    def search(state: State) -> dict:
        return execute(state, [(p.region, p.query, p.why) for p in state["pending"]]) | {"pending": []}

    g = StateGraph(State)
    g.add_node("seed", seed)
    g.add_node("plan", plan)
    g.add_node("search", search)
    g.add_edge(START, "seed")
    g.add_edge("seed", "plan")
    g.add_conditional_edges("plan", lambda s: END if s["stop"] else "search")
    g.add_edge("search", "plan")
    return g.compile()


def _keep(place: dict, cfg: CityConfig) -> bool:
    if "location" not in place or place.get("businessStatus", "OPERATIONAL") != "OPERATIONAL":
        return False
    if place.get("userRatingCount", 0) < cfg.min_reviews:
        return False
    if place.get("primaryType") in NOISE_PRIMARY_TYPES:
        return False
    if not cfg.contains(place["location"]["latitude"], place["location"]["longitude"]):
        return False
    return not (set(place.get("types", [])) & BLOCKED_TYPES)


def run_discovery(cfg: CityConfig, client, out_dir: Path, planner=None, model: str = AGENT_MODEL) -> State:
    graph = build_graph(cfg, client, planner or _default_planner(cfg, model))
    final = graph.invoke(
        {"places": {}, "done": [], "log": [], "pending": [], "searches_used": 0, "rounds": 0, "stop": False},
        {"recursion_limit": 100},
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidates.json").write_text(
        json.dumps(list(final["places"].values()), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out_dir / "agent_trace.json").write_text(
        json.dumps(final["log"], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return final
