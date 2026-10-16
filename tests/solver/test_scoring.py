import json
from pathlib import Path

from pipeline.merge import merge_city
from solver.scoring import DISABLED_PRESETS, PRESETS, PoolSpec, score_places, select_pool, to_solver_places

CITY = Path(__file__).resolve().parents[2] / "data" / "cities" / "florianopolis"


def mk(pid, *, dining=False, paid=False, category="outro", **f):
    feats = dict(authenticity=0.5, touristy=0.5, gastronomy=0.0, culture=0.0, nature=0.0, landmark=0.0)
    feats.update(f)
    feats.update(is_dining=dining, is_paid=paid, duration_min=60, est_price_brl=None, category=category)
    return {"id": pid, "rating": 4.5, "n_reviews": 100, "windows": None, "features": feats}


def test_styles_rank_the_expected_places_first():
    icon = mk("icon", landmark=0.95, touristy=0.9, authenticity=0.3)
    beach = mk("beach", nature=0.95, authenticity=0.5)
    ps = [icon, beach]
    best = lambda preset: max(score_places(ps, preset).items(), key=lambda kv: kv[1])[0]  # noqa: E731
    assert best("primeira_vez") == "icon"
    assert best("ar_livre") == "beach"
    assert all(0 <= s <= 1 for s in score_places(ps, "primeira_vez").values())


def test_pool_caps_dining_share_and_respects_exclude_mandatory_free():
    foods = [mk(f"f{i}", dining=True, authenticity=0.95, touristy=0.05, gastronomy=0.9) for i in range(30)]
    others = [mk(f"o{i}", authenticity=0.6, touristy=0.3) for i in range(40)]
    spec = PoolSpec("primeira_vez", per_day=5, n_days=3, exclude={"o0"}, mandatory={"o39"}, allow_food=True)
    pool = select_pool(foods + others, spec)
    ids = [p["id"] for p in pool]
    assert len(pool) == 45  # 3·5·3
    assert sum(p["features"]["is_dining"] for p in pool) <= 12  # 25% de 45, arredondado p/ cima
    assert "o0" not in ids and "o39" in ids  # excluído fora, obrigatório dentro
    paid = mk("paid", paid=True, authenticity=1.0, touristy=0.0)
    free_pool = select_pool(others + [paid], PoolSpec("primeira_vez", 2, 2, free_only=True))
    assert "paid" not in [p["id"] for p in free_pool]


def test_solver_places_convert_windows_and_scores():
    p = mk("a")
    p["windows"] = {"0": [[540, 720], [840, 1080]]}
    p["_score"] = 0.7
    sp = to_solver_places([p])[0]
    assert sp.windows == {0: ((540, 720), (840, 1080))} and sp.score == 0.7 and sp.duration == 60


def test_merge_real_florianopolis_data(tmp_path):
    import shutil

    if not (CITY / "classified").exists() or not list((CITY / "classified").glob("*.json")):
        return  # dados reais ainda não gerados
    work = tmp_path / "c"
    shutil.copytree(CITY, work, ignore=shutil.ignore_patterns("places.json"))
    stats = merge_city(work)
    assert stats["merged"] > 100
    places = json.loads((work / "places.json").read_text(encoding="utf-8"))
    assert {"lat", "lng", "region", "features"} <= set(places[0])
    assert set(PRESETS) and all(p["features"]["duration_min"] >= 10 for p in places)


def test_food_is_out_of_the_pool_by_default_but_mandatory_food_stays():
    ps = (
        [mk(f"f{i}", dining=True, category="restaurante") for i in range(3)]
        + [mk("padaria", category="cafe_padaria"), mk("bar1", category="bar")]
        + [mk(f"m{i}", landmark=0.9) for i in range(10)]
    )
    ids = [p["id"] for p in select_pool(ps, PoolSpec("primeira_vez", 2, 2))]
    assert not any(i.startswith(("f", "padaria", "bar")) for i in ids)
    with_must = [p["id"] for p in select_pool(ps, PoolSpec("primeira_vez", 2, 2, mandatory={"f0"}))]
    assert "f0" in with_must  # o usuário pediu explicitamente
    assert "como_um_local" not in PRESETS and "como_um_local" in DISABLED_PRESETS
