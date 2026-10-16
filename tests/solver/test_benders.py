import pytest
from test_model import brute_force, check_solution, make_instance

from solver.benders import best_route, metric_closure, solve_decomposed
from solver.model import Place, simulate_day


def closed(inst):
    inst.travel = metric_closure(inst.travel)
    return inst


def test_best_route_matches_permutations():
    import itertools

    inst = closed(make_instance(4, n=6))
    nodes = (1, 2, 3, 4)
    expected = None
    for order in itertools.permutations(nodes):
        if simulate_day(inst, 0, order):
            legs = (0, *order, 0)
            cost = sum(inst.travel[a][b] for a, b in zip(legs, legs[1:]))
            expected = cost if expected is None else min(expected, cost)
    got = best_route(inst, inst.weekdays[0], nodes)
    assert (got is None) == (expected is None)
    if got:
        assert got[0] == expected


@pytest.mark.parametrize("seed", range(8))
def test_matches_brute_force(seed):
    inst = closed(make_instance(seed))
    expected = brute_force(inst)
    res = solve_decomposed(inst, time_limit=30)
    if expected is None:
        assert res.status == "INFEASIBLE"
        return
    assert res.status == "OPTIMAL"
    check_solution(closed(inst), res)
    assert res.travel_total == expected[0]
    assert res.stage2 == "OPTIMAL"
    assert res.score_total == pytest.approx(expected[1], abs=1e-6)


def test_mandatory_fixed_day_and_budget():
    inst = closed(make_instance(3, n=7, mandatory={"p0": 1, "p5": None}, budget=55))
    expected = brute_force(inst)
    res = solve_decomposed(inst, time_limit=30)
    assert expected is not None and res.status == "OPTIMAL"
    check_solution(inst, res)
    assert res.travel_total == expected[0]
    assert res.score_total == pytest.approx(expected[1], abs=1e-6)


def test_infeasible_reports_mandatory_closed():
    inst = closed(make_instance(1))
    inst.places[1] = Place("p1", 30, windows={5: ((540, 1000),)})
    inst.mandatory = {"p1": None}
    res = solve_decomposed(inst, time_limit=10)
    assert res.status == "INFEASIBLE"
    assert any("p1" in c for c in res.conflicts), res.conflicts


def brute_force_lex(inst):
    """(Σ deslocamento, Σ score, Σ hora de volta) lexicográfico: min, max, min. Sem obrigatórios/orçamento."""
    import itertools

    n, D, X = len(inst.places), len(inst.weekdays), inst.per_day
    options = []
    for d in range(D):
        by_set = {}
        for order in itertools.permutations(range(1, n + 1), X):
            if sum(inst.places[i - 1].is_dining for i in order) > 1:
                continue
            sim = simulate_day(inst, d, order)
            if not sim:
                continue
            legs = (0, *order, 0)
            key = (sum(inst.travel[a][b] for a, b in zip(legs, legs[1:])), sim[2])
            s = frozenset(order)
            by_set[s] = min(by_set.get(s, key), key)
        options.append(by_set)

    best = None

    def rec(d, used, cost, back, score):
        nonlocal best
        if d == D:
            key = (cost, -round(score, 3), back)
            best = key if best is None or key < best else best
            return
        for s, (c, b) in options[d].items():
            if not used & s:
                rec(d + 1, used | s, cost + c, back + b, score + sum(inst.places[i - 1].score for i in s))

    rec(0, frozenset(), 0, 0, 0.0)
    return best


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("equal_scores", [False, True])
def test_lexicographic_travel_score_finish(seed, equal_scores):
    inst = closed(make_instance(seed))
    if equal_scores:  # todos os scores iguais: só o término desempata
        inst.places = [Place(p.id, p.duration, 0.5, p.price, p.is_dining, p.windows) for p in inst.places]
    expected = brute_force_lex(inst)
    res = solve_decomposed(inst, time_limit=30)
    if expected is None:
        assert res.status == "INFEASIBLE"
        return
    assert res.status == "OPTIMAL" and res.stage2 == "OPTIMAL" and res.stage3 == "OPTIMAL"
    assert res.travel_total == expected[0]
    assert res.score_total == pytest.approx(-expected[1], abs=1e-6)
    assert sum(dp.back for dp in res.days) == expected[2]
