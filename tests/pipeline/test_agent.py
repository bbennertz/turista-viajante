from pathlib import Path

from pipeline.agent import CityConfig, Plan, Proposal, run_discovery

CITY = Path(__file__).resolve().parents[2] / "data" / "cities" / "florianopolis" / "city.json"


class FakeClient:
    """Cada busca devolve 3 lugares novos + 1 repetido + 1 hotel + 1 sem avaliações."""

    def __init__(self):
        self.calls = []

    def text_search(self, query, *, center, radius_m, language="en", max_pages=1):
        k = len(self.calls)
        self.calls.append(query)

        def mk(pid, **kw):
            return {"id": pid, "displayName": {"text": pid}, "types": ["restaurant"],
                    "location": {"latitude": center[0], "longitude": center[1]},
                    "userRatingCount": 100, **kw}

        return [mk(f"p{k}_{i}") for i in range(3)] + [
            mk("shared"), mk(f"hotel{k}", types=["lodging"]), mk(f"vazio{k}", userRatingCount=2)
        ]


def test_budget_dedup_and_filters(tmp_path):
    cfg = CityConfig.load(CITY)
    cfg.max_searches, cfg.target_candidates = 12, 10_000
    client = FakeClient()
    asked = []

    def planner(summary):
        asked.append(summary)
        n = len(asked)
        return Plan(queries=[
            Proposal(region=cfg.regions[0].name, query=f"busca {n}.{j}", why="teste") for j in range(4)
        ] + [Proposal(region="Região Inventada", query="x", why="inválida")][:0])

    final = run_discovery(cfg, client, tmp_path, planner=planner)
    assert final["searches_used"] == len(client.calls) <= cfg.max_searches
    assert len(client.calls) == 12  # 6 sementes + 6 do planejador, respeitando o teto
    ids = list(final["places"])
    assert len(ids) == len(set(ids))
    assert not any(i.startswith(("hotel", "vazio")) for i in ids)
    assert "shared" in ids and sum(i == "shared" for i in ids) == 1
    assert (tmp_path / "candidates.json").exists() and (tmp_path / "agent_trace.json").exists()


def test_invalid_and_repeated_proposals_are_dropped(tmp_path):
    cfg = CityConfig.load(CITY)
    cfg.max_searches = 50
    client = FakeClient()
    calls = {"n": 0}

    def planner(summary):
        calls["n"] += 1
        if calls["n"] == 1:
            return Plan(queries=[
                Proposal(region="Região Inventada", query="a", why=""),
                Proposal(region=cfg.regions[1].name, query="boa", why=""),
                Proposal(region=cfg.regions[1].name, query="BOA", why=""),  # duplicada
            ])
        return Plan(queries=[], stop=True)  # nada novo -> encerra

    final = run_discovery(cfg, client, tmp_path, planner=planner)
    assert client.calls.count("boa") == 1
    assert "a" not in client.calls
    assert final["stop"] is True


def test_llm_stop_respected_only_with_enough_coverage(tmp_path):
    cfg = CityConfig.load(CITY)
    cfg.target_candidates = 1000  # 60% = 600: o stop precoce do LLM deve ser ignorado
    cfg.max_searches = 10
    client = FakeClient()
    rounds = {"n": 0}

    def planner(summary):
        rounds["n"] += 1
        return Plan(queries=[Proposal(region=cfg.regions[0].name, query=f"q{rounds['n']}", why="")], stop=True)

    run_discovery(cfg, client, tmp_path, planner=planner)
    assert len(client.calls) == 10  # continuou até o teto apesar do stop=True


def test_total_target_does_not_stop_while_a_bucket_is_short(tmp_path):
    cfg = CityConfig.load(CITY)
    cfg.target_candidates, cfg.max_searches = 10, 14  # meta total é batida logo nas sementes
    client = FakeClient()  # só devolve restaurantes: natureza/cultura/icone nunca chegam a 30

    def planner(summary):
        assert "FALTAM" in summary and "natureza" in summary
        return Plan(queries=[Proposal(region=cfg.regions[0].name, query=f"q{len(client.calls)}", why="")], stop=True)

    final = run_discovery(cfg, client, tmp_path, planner=planner)
    assert len(final["places"]) >= cfg.target_candidates
    assert len(client.calls) > 6  # continuou além das sementes por causa dos mínimos


def test_stops_when_total_and_all_buckets_are_covered(tmp_path):
    cfg = CityConfig.load(CITY)
    cfg.target_candidates, cfg.max_searches = 10, 30
    cfg.min_per_bucket = {"comida": 5}  # só comida, que o FakeClient entrega
    client = FakeClient()
    final = run_discovery(cfg, client, tmp_path, planner=lambda s: Plan(queries=[]))
    assert final["stop"] and len(client.calls) == 6  # parou logo após as sementes


def test_icon_bucket_is_type_or_popularity_but_not_restaurants():
    from pipeline.agent import _bucket

    assert _bucket({"types": ["bridge", "scenic_spot"], "userRatingCount": 100}) == "icone"
    assert _bucket({"types": ["beach"], "userRatingCount": 9000}) == "icone"
    assert _bucket({"types": ["market", "food"], "userRatingCount": 97000}) == "comida"
    assert _bucket({"types": ["restaurant"], "userRatingCount": 10000}) == "comida"
    assert _bucket({"types": ["park"], "userRatingCount": 200}) == "natureza"
    assert _bucket({"types": ["museum"], "userRatingCount": 200}) == "cultura"


def test_noise_filter_uses_primary_type_only():
    from pipeline.agent import _keep

    cfg = CityConfig.load(CITY)
    base = {"location": {"latitude": -27.6, "longitude": -48.5}, "userRatingCount": 100}
    # padaria legítima que tem "store" na lista de tipos NÃO pode ser descartada
    assert _keep({**base, "primaryType": "bakery", "types": ["bakery", "store", "food"]}, cfg)
    assert not _keep({**base, "primaryType": "sports_school", "types": ["sports_school"]}, cfg)
    assert not _keep({**base, "primaryType": "hotel", "types": ["hotel", "lodging"]}, cfg)


def test_bbox_drops_places_outside_the_city():
    from pipeline.agent import _keep

    cfg = CityConfig.load(CITY)
    base = {"primaryType": "park", "types": ["park"], "userRatingCount": 100}
    inside = {**base, "location": {"latitude": -27.60, "longitude": -48.47}}
    garopaba = {**base, "location": {"latitude": -28.02, "longitude": -48.62}}
    assert _keep(inside, cfg) and not _keep(garopaba, cfg)
