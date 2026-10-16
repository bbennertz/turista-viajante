import itertools
import math
import random

import pytest

from solver.model import Instance, Place, simulate_day, solve


def make_instance(seed: int, n: int = 6, days: int = 2, per_day: int = 2, **kw) -> Instance:
    rng = random.Random(seed)
    pts = [(rng.uniform(0, 30), rng.uniform(0, 30)) for _ in range(n + 1)]
    travel = [[round(math.dist(a, b)) for b in pts] for a in pts]
    places = []
    for k in range(n):
        windows = None
        if k == 1:  # horário partido, fechado em um dos dias
            windows = {0: ((540, 720), (840, 1080))}
        elif k == 2:  # abre tarde
            windows = {0: ((780, 1080),), 1: ((600, 1080),)}
        places.append(
            Place(
                id=f"p{k}",
                duration=rng.choice([30, 45, 60, 90]),
                score=round(rng.random(), 2),
                price=rng.choice([0, 0, 10, 25]),
                is_dining=(k in (3, 4)),
                windows=windows,
            )
        )
    return Instance(places, travel, weekdays=[0, 1, 2][:days], per_day=per_day, **kw)


def brute_force(inst: Instance):
    """Enumera tudo; devolve (min tempo, max score com esse tempo) ou None."""
    n, D, X = len(inst.places), len(inst.weekdays), inst.per_day
    options = []
    for d in range(D):
        opts = []
        for order in itertools.permutations(range(1, n + 1), X):
            if sum(inst.places[i - 1].is_dining for i in order) > 1:
                continue
            if simulate_day(inst, d, order):
                legs = (0, *order, 0)
                opts.append((order, sum(inst.travel[a][b] for a, b in zip(legs, legs[1:]))))
        options.append(opts)

    ids = [p.id for p in inst.places]
    best = None

    def rec(d, chosen):
        nonlocal best
        if d == D:
            flat = [i for o in chosen for i in o]
            if len(set(flat)) != len(flat):
                return
            for pid, fixed in inst.mandatory.items():
                i = ids.index(pid) + 1
                if i not in flat or (fixed is not None and i not in chosen[fixed]):
                    return
            if inst.budget is not None and sum(inst.places[i - 1].price for i in flat) > inst.budget:
                return
            cost = sum(c for _, c in costs)
            score = sum(inst.places[i - 1].score for i in flat)
            key = (cost, -round(score, 3))
            if best is None or key < best:
                best = key
            return
        for order, cost in options[d]:
            costs.append((order, cost))
            rec(d + 1, [*chosen, order])
            costs.pop()

    costs: list = []
    rec(0, [])
    return None if best is None else (best[0], -best[1])


def check_solution(inst: Instance, res):
    seen = []
    for dp in res.days:
        assert len(dp.stops) == inst.per_day
        assert dp.depart >= inst.t_start and dp.back <= inst.t_end
        idx = [next(k + 1 for k, p in enumerate(inst.places) if p.id == s.place_id) for s in dp.stops]
        assert simulate_day(inst, dp.day, idx) is not None
        assert sum(inst.places[i - 1].is_dining for i in idx) <= 1
        seen += [s.place_id for s in dp.stops]
    assert len(seen) == len(set(seen))
    for pid, fixed in inst.mandatory.items():
        assert pid in seen
        if fixed is not None:
            assert pid in [s.place_id for s in res.days[fixed].stops]
    if inst.budget is not None:
        spent = sum(p.price for p in inst.places if p.id in seen)
        assert spent <= inst.budget


@pytest.mark.parametrize("seed", range(6))
def test_matches_brute_force(seed):
    inst = make_instance(seed)
    expected = brute_force(inst)
    res = solve(inst, time_limit=20, workers=4)
    if expected is None:
        assert res.status == "INFEASIBLE"
        return
    assert res.status == "OPTIMAL"
    check_solution(inst, res)
    assert res.travel_total == expected[0]
    assert res.stage2 == "OPTIMAL"
    assert res.score_total == pytest.approx(expected[1], abs=1e-6)


def test_mandatory_fixed_day_and_budget():
    inst = make_instance(3, n=7, per_day=2, mandatory={"p0": 1, "p5": None}, budget=55)
    expected = brute_force(inst)
    res = solve(inst, time_limit=20, workers=4)
    assert expected is not None and res.status == "OPTIMAL"
    check_solution(inst, res)
    assert res.travel_total == expected[0]


def test_infeasible_reports_mandatory_closed():
    inst = make_instance(1)
    inst.places[1] = Place("p1", 30, windows={5: ((540, 1000),)})  # só abre no sábado
    inst.mandatory = {"p1": None}
    res = solve(inst, time_limit=10, workers=1)
    assert res.status == "INFEASIBLE"
    assert any("p1" in c for c in res.conflicts), res.conflicts


def test_infeasible_reports_day_window():
    inst = make_instance(2, per_day=3)
    inst.t_end = inst.t_start + 60  # 1h não cabe 3 lugares
    res = solve(inst, time_limit=10, workers=1)
    assert res.status == "INFEASIBLE"
    assert res.conflicts, "deveria apontar ao menos um grupo culpado"


def test_infeasible_reports_budget():
    inst = make_instance(3, n=7, per_day=2, mandatory={"p0": 1, "p5": None}, budget=40)
    assert brute_force(inst) is None  # 2 obrigatórios de 25 > 40
    res = solve(inst, time_limit=10, workers=1)
    assert res.status == "INFEASIBLE"
    assert any("rçamento" in c or "p0" in c or "p5" in c for c in res.conflicts), res.conflicts
