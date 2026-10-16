"""Modelo CP-SAT: seleção + roteamento multi-dia com janelas de tempo.

Formulação (ver plano): min tempo de deslocamento, exatamente X lugares por dia,
saindo e voltando ao hotel (nó 0). Estágio 2 (lexicográfico): com o tempo fixado
em T̂, maximiza o score dos lugares escolhidos.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

DAY_MINUTES = 24 * 60
SCORE_SCALE = 1000
PRICE_SCALE = 100


@dataclass(frozen=True)
class Place:
    id: str
    duration: int  # minutos de visita
    score: float = 0.0
    price: float = 0.0
    is_dining: bool = False
    # weekday (0=seg) -> intervalos (abre, fecha) em minutos. None = sempre aberto.
    # Dia ausente do dict = fechado nesse dia.
    windows: dict[int, tuple[tuple[int, int], ...]] | None = None


@dataclass
class Instance:
    places: list[Place]  # pool P; no modelo o lugar k ocupa o nó k+1
    travel: list[list[int]]  # (n+1)x(n+1) em minutos; índice 0 = hotel
    weekdays: list[int]  # dia da semana de cada dia da viagem
    per_day: int  # X
    t_start: int = 540
    t_end: int = 1140
    mandatory: dict[str, int | None] = field(default_factory=dict)  # id -> dia fixo ou None
    budget: float | None = None
    lunch: tuple[int, int] = (720, 840)


@dataclass
class Stop:
    place_id: str
    arrive: int
    leave: int


@dataclass
class DayPlan:
    day: int
    weekday: int
    stops: list[Stop]
    depart: int
    back: int
    travel: int


@dataclass
class Result:
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN
    gap: float | None = None
    travel_total: int | None = None
    score_total: float | None = None
    days: list[DayPlan] = field(default_factory=list)
    stage2: str | None = None  # score (None = não rodou)
    stage3: str | None = None  # decomposição: desempate, termina mais cedo
    conflicts: list[str] = field(default_factory=list)
    elapsed: float = 0.0


def arrival_intervals(
    p: Place, weekday: int, lunch: tuple[int, int]
) -> list[tuple[int, int]]:
    """Domínio de chegada Dom_i^d: união de [abre, fecha - duração], ∩ almoço se dining."""
    raw = [(0, DAY_MINUTES)] if p.windows is None else list(p.windows.get(weekday, ()))
    out = []
    for a, b in raw:
        lo, hi = a, b - p.duration
        if p.is_dining:
            lo, hi = max(lo, lunch[0]), min(hi, lunch[1])
        if lo <= hi:
            out.append((lo, hi))
    return sorted(out)


def simulate_day(
    inst: Instance, d: int, order: tuple[int, ...] | list[int]
) -> tuple[list[int], int, int] | None:
    """Agenda mais cedo possível (espera permitida) de uma rota; nós 1-based.

    Devolve (chegadas, saída do hotel, volta) ou None se violar janelas/horizonte.
    """
    t = inst.t_start
    prev = 0
    arrivals = []
    for i in order:
        p = inst.places[i - 1]
        arr = t + inst.travel[prev][i]
        for lo, hi in arrival_intervals(p, inst.weekdays[d], inst.lunch):
            if arr <= hi:
                arr = max(arr, lo)
                break
        else:
            return None
        arrivals.append(arr)
        t = arr + p.duration
        prev = i
    back = t + inst.travel[prev][0]
    if back > inst.t_end:
        return None
    return arrivals, inst.t_start, back


@dataclass
class _Built:
    model: cp_model.CpModel
    y: dict
    x: dict
    travel: cp_model.LinearExpr
    score: cp_model.LinearExpr
    guards: dict[str, cp_model.IntVar]


def _validate(inst: Instance) -> None:
    n = len(inst.places)
    if inst.per_day < 1:
        raise ValueError("per_day deve ser >= 1")
    if len(inst.travel) != n + 1 or any(len(r) != n + 1 for r in inst.travel):
        raise ValueError("travel deve ser (n+1)x(n+1), com o hotel no índice 0")
    ids = {p.id for p in inst.places}
    if len(ids) != n:
        raise ValueError("ids de lugares duplicados")
    for pid, fixed in inst.mandatory.items():
        if pid not in ids:
            raise ValueError(f"obrigatório fora do pool: {pid}")
        if fixed is not None and not 0 <= fixed < len(inst.weekdays):
            raise ValueError(f"dia fixo inválido para {pid}: {fixed}")


def _build(
    inst: Instance,
    *,
    guarded: bool,
    max_travel: int | None = None,
    maximize_score: bool = False,
) -> _Built:
    _validate(inst)
    m = cp_model.CpModel()
    places = inst.places
    n = len(places)
    nodes = range(n + 1)
    pool = range(1, n + 1)
    days = range(len(inst.weekdays))
    dur = [0] + [p.duration for p in places]
    c = inst.travel
    guards: dict[str, cp_model.IntVar] = {}

    def enforce(constraint, name: str) -> None:
        # No modo diagnóstico, cada grupo ganha um literal de assunção.
        if guarded:
            lit = guards.setdefault(name, m.new_bool_var(name))
            constraint.only_enforce_if(lit)

    y = {(i, d): m.new_bool_var(f"y_{i}_{d}") for i in pool for d in days}
    t = {(i, d): m.new_int_var(0, DAY_MINUTES, f"t_{i}_{d}") for i in pool for d in days}
    t0 = {d: m.new_int_var(0, DAY_MINUTES, f"t0_{d}") for d in days}
    tau = {d: m.new_int_var(0, DAY_MINUTES, f"tau_{d}") for d in days}
    x = {}

    for d in days:
        arcs = []
        for i in nodes:
            for j in nodes:
                if i != j:
                    x[i, j, d] = m.new_bool_var(f"x_{i}_{j}_{d}")
                    arcs.append((i, j, x[i, j, d]))
        for i in pool:
            arcs.append((i, i, ~y[i, d]))  # (4) lugar não visitado = self-loop
        m.add_circuit(arcs)

        # (5)(6) propagação de tempo, espera permitida
        for j in pool:
            m.add(t[j, d] >= t0[d] + c[0][j]).only_enforce_if(x[0, j, d])
            m.add(tau[d] >= t[j, d] + dur[j] + c[j][0]).only_enforce_if(x[j, 0, d])
            for i in pool:
                if i != j:
                    m.add(t[j, d] >= t[i, d] + dur[i] + c[i][j]).only_enforce_if(x[i, j, d])

        # (7) horizonte do dia
        enforce(m.add(t0[d] >= inst.t_start), f"horizon:{d}")
        enforce(m.add(tau[d] <= inst.t_end), f"horizon:{d}")

        # (3) exatamente X por dia
        enforce(m.add(sum(y[i, d] for i in pool) == inst.per_day), f"count:{d}")

        # (8) horário de funcionamento como domínio de chegada (não convexo)
        for i in pool:
            p = places[i - 1]
            if p.windows is not None or p.is_dining:
                ivs = arrival_intervals(p, inst.weekdays[d], inst.lunch)
                if not ivs:
                    m.add(y[i, d] == 0)
                else:
                    dom = cp_model.Domain.from_intervals([[lo, hi] for lo, hi in ivs])
                    m.add_linear_expression_in_domain(t[i, d], dom).only_enforce_if(y[i, d])

        # (9) no máximo 1 dining por dia
        dining = [y[i, d] for i in pool if places[i - 1].is_dining]
        if dining:
            m.add(sum(dining) <= 1)

    # (1) cada lugar no máximo uma vez
    for i in pool:
        m.add(sum(y[i, d] for d in days) <= 1)

    # (2) obrigatórios (com dia fixo opcional)
    index = {p.id: k + 1 for k, p in enumerate(places)}
    for pid, fixed in inst.mandatory.items():
        i = index[pid]
        if fixed is None:
            con = m.add(sum(y[i, d] for d in days) == 1)
        else:
            con = m.add(y[i, fixed] == 1)
        enforce(con, f"mandatory:{pid}")

    # (10) orçamento
    if inst.budget is not None:
        spend = sum(
            round(places[i - 1].price * PRICE_SCALE) * y[i, d] for i in pool for d in days
        )
        enforce(m.add(spend <= int(inst.budget * PRICE_SCALE)), "budget")

    travel = sum(c[i][j] * x[i, j, d] for (i, j, d) in x)
    score = sum(
        round(places[i - 1].score * SCORE_SCALE) * y[i, d] for i in pool for d in days
    )
    if max_travel is not None:
        m.add(travel <= max_travel)
    if maximize_score:
        m.maximize(score)
    else:
        m.minimize(travel)
    if guarded:
        m.add_assumptions(list(guards.values()))
    return _Built(m, y, x, travel, score, guards)


def _run(model: cp_model.CpModel, time_limit: float, workers: int):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(time_limit, 0.1)
    solver.parameters.num_workers = workers
    return solver, solver.solve(model)


def _extract(inst: Instance, solver: cp_model.CpSolver, b: _Built) -> list[DayPlan]:
    n = len(inst.places)
    plans = []
    for d in range(len(inst.weekdays)):
        order, node = [], 0
        while True:
            node = next(j for j in range(n + 1) if j != node and solver.value(b.x[node, j, d]))
            if node == 0:
                break
            order.append(node)
        # re-agenda no mais cedo: o solver só garante t >= ..., não t apertado
        sim = simulate_day(inst, d, order)
        assert sim is not None, "solução do CP-SAT violou o simulador"
        arrivals, depart, back = sim
        stops = [
            Stop(inst.places[i - 1].id, a, a + inst.places[i - 1].duration)
            for i, a in zip(order, arrivals)
        ]
        legs = [0, *order, 0]
        travel = sum(inst.travel[a][b_] for a, b_ in zip(legs, legs[1:]))
        plans.append(DayPlan(d, inst.weekdays[d], stops, depart, back, travel))
    return plans


def solve(inst: Instance, time_limit: float = 30.0, workers: int = 8) -> Result:
    started = time.monotonic()
    b1 = _build(inst, guarded=False)
    solver1, st1 = _run(b1.model, time_limit, workers)
    name1 = solver1.status_name(st1)

    if st1 == cp_model.INFEASIBLE:
        from solver.diagnose import explain

        return Result(
            "INFEASIBLE",
            conflicts=explain(inst),
            elapsed=time.monotonic() - started,
        )
    if st1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Result("UNKNOWN", elapsed=time.monotonic() - started)

    t_hat = round(solver1.objective_value)
    bound = solver1.best_objective_bound
    gap = 0.0 if st1 == cp_model.OPTIMAL else (
        (t_hat - bound) / t_hat if t_hat > 0 else 0.0
    )
    solver, b = solver1, b1
    stage2 = None

    # Estágio 2 só se o estágio 1 provou o ótimo (T̂ é o ótimo, não só uma cota)
    if st1 == cp_model.OPTIMAL:
        b2 = _build(inst, guarded=False, max_travel=t_hat, maximize_score=True)
        for key, var in b1.y.items():
            b2.model.add_hint(b2.y[key], solver1.value(var))
        for key, var in b1.x.items():
            b2.model.add_hint(b2.x[key], solver1.value(var))
        remaining = max(time_limit - (time.monotonic() - started), 1.0)
        solver2, st2 = _run(b2.model, remaining, workers)
        if st2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver, b, stage2 = solver2, b2, solver2.status_name(st2)

    days = _extract(inst, solver, b)
    chosen = {s.place_id for dp in days for s in dp.stops}
    return Result(
        status=name1,
        gap=gap,
        travel_total=sum(dp.travel for dp in days),
        score_total=sum(p.score for p in inst.places if p.id in chosen),
        days=days,
        stage2=stage2,
        elapsed=time.monotonic() - started,
    )
