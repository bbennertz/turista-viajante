import itertools

import pytest
from test_model import make_instance

from solver.benders import metric_closure
from solver.model import Instance, Place, simulate_day
from solver.tsp import TspInstance, solve_tsp


def tsp_from(seed, n=6, weekday=0, t_end=1080):
    base = make_instance(seed, n=n, days=1, per_day=n)
    places = [Place(p.id, p.duration, windows=p.windows) for p in base.places]  # sem dining/score
    return TspInstance(places, metric_closure(base.travel), weekday, 540, t_end)


def brute_force(ti: TspInstance):
    """(deslocamento mínimo, volta mais cedo entre os de menor deslocamento) ou None."""
    inst = Instance(ti.places, ti.travel, [ti.weekday], len(ti.places), ti.t_start, ti.t_end)
    best = None
    for order in itertools.permutations(range(1, len(ti.places) + 1)):
        sim = simulate_day(inst, 0, order)
        if not sim:
            continue
        legs = (0, *order, 0)
        key = (sum(ti.travel[a][b] for a, b in zip(legs, legs[1:])), sim[2])
        best = key if best is None or key < best else best
    return best


@pytest.mark.parametrize("weekday", [0, 1, 5])
@pytest.mark.parametrize("seed", range(6))
def test_matches_brute_force_travel_then_finish(seed, weekday):
    ti = tsp_from(seed, weekday=weekday)
    expected = brute_force(ti)
    res = solve_tsp(ti, time_limit=20, workers=4)
    if expected is None:
        assert res.status == "INFEASIBLE" and res.conflicts
        return
    assert res.status == "OPTIMAL"
    assert (res.travel_total, res.back) == expected
    assert sorted(s.place_id for s in res.stops) == sorted(p.id for p in ti.places)  # visitou todos
    for a, b in zip(res.stops, res.stops[1:]):  # sem sobreposição de horários
        assert a.leave <= b.arrive
    assert res.back <= ti.t_end


def test_finish_tiebreak_picks_the_earlier_return():
    # dois lugares simétricos em deslocamento; só um deles abre tarde: o que abre cedo deve ir primeiro
    travel = [[0, 10, 10], [10, 0, 5], [10, 5, 0]]
    early = Place("cedo", 30, windows=None)
    late = Place("tarde", 30, windows={0: ((780, 1000),)})  # abre 13h
    for places in ([early, late], [late, early]):
        ti = TspInstance(places, travel, 0, 540, 1080)
        res = solve_tsp(ti, workers=2)
        assert res.status == "OPTIMAL" and [s.place_id for s in res.stops] == ["cedo", "tarde"]
        assert res.back == 780 + 30 + 10


def test_infeasible_when_closed_that_day():
    ti = tsp_from(1)
    ti.places[1] = Place("fechado", 30, windows={5: ((540, 1000),)})  # só sábado; weekday=0
    res = solve_tsp(ti, workers=2)
    assert res.status == "INFEASIBLE" and any("fechado" in c for c in res.conflicts)


def test_infeasible_when_visits_exceed_the_day_and_names_a_conflict():
    places = [Place(f"p{i}", 120) for i in range(6)]  # 720 min de visita
    n = len(places)
    travel = [[0 if i == j else 10 for j in range(n + 1)] for i in range(n + 1)]
    res = solve_tsp(TspInstance(places, travel, 0, 540, 1080), workers=2)  # janela de 540 min
    assert res.status == "INFEASIBLE"
    assert "somam" in res.conflicts[0]


def test_infeasible_by_combination_reports_minimal_subset():
    # cada um cabe sozinho, a soma das visitas cabe, mas o deslocamento entre eles estoura a janela
    places = [Place(f"p{i}", 60) for i in range(4)]
    n = len(places)
    travel = [[0 if i == j else 100 for j in range(n + 1)] for i in range(n + 1)]
    res = solve_tsp(TspInstance(places, travel, 0, 540, 1080), workers=2)
    assert res.status == "INFEASIBLE"
    # 240 min de visita + 500 min de deslocamento mínimo > 540 min de janela
    assert "menor deslocamento" in res.conflicts[0] and "740" in res.conflicts[0]


def test_incompatible_time_windows_report_the_minimal_conflicting_pair():
    # soma das visitas e deslocamento mínimo cabem na janela; mas A e B só abrem na mesma meia hora,
    # distantes 60 min entre si: não dá para visitar os dois
    a = Place("A", 20, windows={0: ((600, 630),)})
    b = Place("B", 20, windows={0: ((600, 630),)})
    c, d = Place("C", 30), Place("D", 30)
    n = 4
    travel = [[0 if i == j else 10 for j in range(n + 1)] for i in range(n + 1)]
    travel[1][2] = travel[2][1] = 60
    res = solve_tsp(TspInstance([a, b, c, d], travel, 0, 540, 1080), workers=2)
    assert res.status == "INFEASIBLE"
    assert "['A', 'B']" in res.conflicts[0] or "['B', 'A']" in res.conflicts[0], res.conflicts


def test_single_place_and_empty_list():
    ti = TspInstance([Place("a", 60)], [[0, 15], [20, 0]], 0, 540, 1080)
    res = solve_tsp(ti, workers=2)
    assert res.status == "OPTIMAL" and res.travel_total == 35 and res.back == 540 + 15 + 60 + 20
    assert solve_tsp(TspInstance([], [[0]], 0)).status == "OPTIMAL"
