"""v1: TSP com janelas de tempo para UM dia, sobre os lugares que o usuário marcou.

Todos os lugares marcados são obrigatórios. Sai do hotel (nó 0) na hora de início, visita
todos respeitando o horário de funcionamento do dia da semana e volta ao hotel até o fim da
janela do dia. Se não couber, o resultado é INFEASIBLE com uma explicação.

Objetivo lexicográfico em uma única resolução: menor deslocamento total e, em empate, volta
ao hotel mais cedo:  min  2048·Σ c_ij x_ij + volta   (volta ≤ 1440 < 2048).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

from ortools.sat.python import cp_model

from solver.benders import metric_closure
from solver.model import DAY_MINUTES, Place, Stop, arrival_intervals

TRAVEL_WEIGHT = 2048  # > DAY_MINUTES: deslocamento tem prioridade estrita sobre o término


@dataclass
class TspInstance:
    places: list[Place]  # todos obrigatórios; no modelo o lugar k é o nó k+1
    travel: list[list[int]]  # (n+1)x(n+1) minutos; índice 0 = hotel
    weekday: int  # 0 = segunda
    t_start: int = 540
    t_end: int = 1080


@dataclass
class TspResult:
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN
    stops: list[Stop] = field(default_factory=list)
    depart: int | None = None
    back: int | None = None
    travel_total: int | None = None
    gap: float | None = None
    conflicts: list[str] = field(default_factory=list)
    elapsed: float = 0.0


def _arrival_domains(inst: TspInstance) -> list[list[tuple[int, int]]]:
    """Dom_i: chegadas permitidas (união dos horários do dia da semana, já descontada a visita)."""
    out = []
    for p in inst.places:
        plain = replace(p, is_dining=False)  # v1 não tem janela de almoço
        out.append(arrival_intervals(plain, inst.weekday, (0, DAY_MINUTES)))
    return out


def _solve_cp(inst: TspInstance, doms, time_limit: float, workers: int):
    n = len(inst.places)
    c, dur = inst.travel, [0] + [p.duration for p in inst.places]
    m = cp_model.CpModel()
    x = {(i, j): m.new_bool_var(f"x_{i}_{j}") for i in range(n + 1) for j in range(n + 1) if i != j}
    m.add_circuit([(i, j, lit) for (i, j), lit in x.items()])
    t = {i: m.new_int_var(0, DAY_MINUTES, f"t_{i}") for i in range(1, n + 1)}
    back = m.new_int_var(0, inst.t_end, "back")
    for j in range(1, n + 1):
        m.add(t[j] >= inst.t_start + c[0][j]).only_enforce_if(x[0, j])
        m.add(back >= t[j] + dur[j] + c[j][0]).only_enforce_if(x[j, 0])
        m.add_linear_expression_in_domain(
            t[j], cp_model.Domain.from_intervals([[lo, hi] for lo, hi in doms[j - 1]])
        )
        for i in range(1, n + 1):
            if i != j:
                m.add(t[j] >= t[i] + dur[i] + c[i][j]).only_enforce_if(x[i, j])
    travel = sum(c[i][j] * lit for (i, j), lit in x.items())
    m.minimize(TRAVEL_WEIGHT * travel + back)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(time_limit, 0.1)
    solver.parameters.num_workers = workers
    status = solver.solve(m)
    return solver, status, x, t, back


def _min_tour(inst: TspInstance, time_limit: float = 5.0) -> int:
    """Cota inferior do deslocamento: TSP puro (sem horários nem janela do dia). É fácil de resolver
    e vale como certificado: dia ≥ Σ visitas + deslocamento."""
    n = len(inst.places)
    c = inst.travel
    m = cp_model.CpModel()
    x = {(i, j): m.new_bool_var(f"x_{i}_{j}") for i in range(n + 1) for j in range(n + 1) if i != j}
    m.add_circuit([(i, j, lit) for (i, j), lit in x.items()])
    m.minimize(sum(c[i][j] * lit for (i, j), lit in x.items()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    status = solver.solve(m)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return max(0, int(solver.best_objective_bound))
    return 0


def _quick_conflicts(inst: TspInstance, doms) -> list[str]:
    """Causas óbvias de inviabilidade, sem resolver nada."""
    window = inst.t_end - inst.t_start
    out = []
    for k, p in enumerate(inst.places, 1):
        if not doms[k - 1]:
            out.append(f"'{p.id}' não abre neste dia da semana (ou o horário não comporta a visita).")
        elif inst.t_start + inst.travel[0][k] + p.duration + inst.travel[k][0] > inst.t_end:
            out.append(f"'{p.id}' sozinho já não cabe: ida e volta do hotel + visita passam da janela do dia.")
    if not out:
        need = sum(p.duration for p in inst.places)
        if need > window:
            out.append(
                f"As visitas somam {need} min, mais que a janela do dia ({window} min), "
                "mesmo sem contar o deslocamento."
            )
        else:
            tour = _min_tour(inst)
            if need + tour > window:
                out.append(
                    f"As visitas somam {need} min e o menor deslocamento possível entre elas é "
                    f"{tour} min: {need + tour} min no total, mais que a janela do dia ({window} min)."
                )
    return out


def _minimal_conflict(inst: TspInstance, doms, budget_s: float = 20.0) -> list[str]:
    """Menor subconjunto de lugares que já é inviável (filtro de remoção; valido pelo fecho métrico)."""
    deadline = time.monotonic() + budget_s
    keep = list(range(len(inst.places)))

    def feasible(idx: list[int]) -> bool | None:
        sub = TspInstance(
            [inst.places[k] for k in idx],
            [[inst.travel[a][b] for b in [0] + [k + 1 for k in idx]] for a in [0] + [k + 1 for k in idx]],
            inst.weekday, inst.t_start, inst.t_end,
        )
        _, st, *_ = _solve_cp(sub, [doms[k] for k in idx], 3.0, 4)
        return None if st == cp_model.UNKNOWN else st in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    for k in list(keep):
        if time.monotonic() > deadline or len(keep) == 1:
            break
        rest = [q for q in keep if q != k]
        if feasible(rest) is False:  # sem k continua inviável: k é dispensável
            keep = rest
    return [inst.places[k].id for k in keep]


def solve_tsp(inst: TspInstance, time_limit: float = 30.0, workers: int = 8) -> TspResult:
    started = time.monotonic()
    if not inst.places:
        return TspResult("OPTIMAL", [], inst.t_start, inst.t_start, 0)
    inst = replace(inst, travel=metric_closure(inst.travel))
    doms = _arrival_domains(inst)

    conflicts = _quick_conflicts(inst, doms)
    if conflicts:
        return TspResult("INFEASIBLE", conflicts=conflicts, elapsed=time.monotonic() - started)

    solver, status, x, t, back = _solve_cp(inst, doms, time_limit, workers)
    if status == cp_model.INFEASIBLE:
        subset = _minimal_conflict(inst, doms)
        msg = (
            "Não cabe na janela do dia: "
            + (f"o conjunto mínimo em conflito é {subset}. " if len(subset) < len(inst.places) else "")
            + "Remova algum lugar, alargue o horário do dia ou escolha outro dia."
        )
        return TspResult("INFEASIBLE", conflicts=[msg], elapsed=time.monotonic() - started)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return TspResult("UNKNOWN", elapsed=time.monotonic() - started)

    n = len(inst.places)
    order, node = [], 0
    while True:
        node = next(j for j in range(n + 1) if j != node and solver.value(x[node, j]))
        if node == 0:
            break
        order.append(node)
    # reagenda no mais cedo (o solver só garante t >= ...)
    clock, prev, stops = inst.t_start, 0, []
    for i in order:
        arr = clock + inst.travel[prev][i]
        for lo, hi in doms[i - 1]:
            if arr <= hi:
                arr = max(arr, lo)
                break
        stops.append(Stop(inst.places[i - 1].id, arr, arr + inst.places[i - 1].duration))
        clock, prev = stops[-1].leave, i
    legs = [0, *order, 0]
    travel_total = sum(inst.travel[a][b] for a, b in zip(legs, legs[1:]))
    obj, bound = solver.objective_value, solver.best_objective_bound
    return TspResult(
        status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        stops=stops,
        depart=inst.t_start,
        back=clock + inst.travel[prev][0],
        travel_total=travel_total,
        gap=0.0 if status == cp_model.OPTIMAL else max(0.0, (obj - bound) / obj) if obj else 0.0,
        elapsed=time.monotonic() - started,
    )
