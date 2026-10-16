"""Decomposição em duas fases (Benders lógico), com objetivo lexicográfico de 3 estágios.

Mestre (CP-SAT): escolhe QUAIS lugares vão em QUAL dia. Subproblema: para cada dia, a rota
ótima sobre os X lugares escolhidos (busca exata com poda): menor deslocamento e, em caso
de empate, a que volta ao hotel mais cedo.

Estágios (lexicográficos):
  1. min  Σ deslocamento                                  -> T̂
  2. max  Σ score                    s.a. Σ desl ≤ T̂                -> Ŝ
  3. min  Σ hora de volta ao hotel   s.a. Σ desl ≤ T̂, Σ score ≥ Ŝ   (desempate: termina mais cedo)
Cada estágio só roda se o anterior provou o ótimo (senão T̂/F̂ seriam só cotas).

Cortes:
  - conjunto inviável S  -> no-good   Σ_{i∈S} y_id ≤ |S|-1
  - deslocamento, custo C -> z_d ≥ C·(Σ_{i∈S} y_id − |S| + 1)   (vale p/ todo T ⊇ S)
  - término, F do conjunto exato S -> f_d ≥ F·(Σ_{i∈S} y_id − |S| + 1)   (SÓ conjunto exato:
    o término não é monótono em S)
A validade dos cortes de deslocamento (T ⊇ S ⇒ custo(T) ≥ custo(S); S inviável ⇒ T inviável)
exige desigualdade triangular, garantida pelo fecho métrico da matriz de tempos (passar por
um lugar sem visitá-lo é legítimo; esperar é grátis).
"""

from __future__ import annotations

import itertools
import os
import time
from dataclasses import replace

import numpy as np
from ortools.sat.python import cp_model

from solver.model import (
    PRICE_SCALE,
    SCORE_SCALE,
    DayPlan,
    Instance,
    Result,
    Stop,
    _validate,
    arrival_intervals,
    simulate_day,
)

DAY = 24 * 60


def metric_closure(travel: list[list[int]]) -> list[list[int]]:
    """Floyd–Warshall: menor tempo entre quaisquer dois nós (garante desigualdade triangular)."""
    d = np.array(travel, dtype=np.int64)
    for k in range(len(d)):
        d = np.minimum(d, d[:, k, None] + d[None, k, :])
    return d.tolist()


def best_route(inst: Instance, weekday: int, nodes) -> tuple[int, tuple[int, ...], int] | None:
    """Rota ótima hotel -> nodes -> hotel: (deslocamento, ordem, hora de volta), ou None.

    Lexicográfico: menor deslocamento; em empate, volta mais cedo."""
    c, places = inst.travel, inst.places
    doms = {i: arrival_intervals(places[i - 1], weekday, inst.lunch) for i in nodes}
    best: list = [None, None, None]  # custo, hora de volta, ordem

    def dfs(prev: int, t: int, cost: int, left: frozenset, order: list[int]) -> None:
        if best[0] is not None and cost > best[0]:
            return
        if not left:
            total, back = cost + c[prev][0], t + c[prev][0]
            if back <= inst.t_end and (best[0] is None or (total, back) < (best[0], best[1])):
                best[0], best[1], best[2] = total, back, tuple(order)
            return
        for i in left:
            arr = t + c[prev][i]
            for lo, hi in doms[i]:
                if arr <= hi:
                    arr = max(arr, lo)
                    break
            else:
                continue
            order.append(i)
            dfs(i, arr + places[i - 1].duration, cost + c[prev][i], left - {i}, order)
            order.pop()

    dfs(0, inst.t_start, 0, frozenset(nodes), [])
    return None if best[0] is None else (best[0], best[2], best[1])


class _Master:
    """Mestre: y[i,d], z[d] (cota do deslocamento) e f[d] (cota da hora de volta)."""

    def __init__(self, inst: Instance, day_cls: list[int]):
        self.inst, self.day_cls = inst, day_cls
        self.nogoods: list[tuple[int, frozenset]] = []
        self.opt_cuts: list[tuple[int, frozenset, int]] = []
        self.finish_cuts: list[tuple[int, frozenset, int]] = []

    def solve(self, *, mode: str, t_cap=None, s_cap=None, hint=None, time_limit: float):
        inst = self.inst
        m = cp_model.CpModel()
        n = len(inst.places)
        pool, days = range(1, n + 1), range(len(inst.weekdays))
        c, places = inst.travel, inst.places
        y = {(i, d): m.new_bool_var(f"y_{i}_{d}") for i in pool for d in days}
        z = {d: m.new_int_var(0, DAY * 10, f"z_{d}") for d in days}
        f = {d: m.new_int_var(0, DAY, f"f_{d}") for d in days}
        min_in = [min(c[j][i] for j in range(n + 1) if j != i) for i in range(n + 1)]
        min_out = [min(c[i][j] for j in range(n + 1) if j != i) for i in range(n + 1)]

        for d in days:
            m.add(sum(y[i, d] for i in pool) == inst.per_day)
            dining = [y[i, d] for i in pool if places[i - 1].is_dining]
            if dining:
                m.add(sum(dining) <= 1)
            for i in pool:
                p = places[i - 1]
                ivs = arrival_intervals(p, inst.weekdays[d], inst.lunch)
                if (p.windows is not None or p.is_dining) and not ivs:
                    m.add(y[i, d] == 0)
                    continue
                # a volta não ocorre antes de o lugar abrir + visita + retorno
                first = max(ivs[0][0] if ivs else 0, inst.t_start + c[0][i])
                m.add(f[d] >= (first + p.duration + c[i][0]) * y[i, d])
            m.add(z[d] >= min_in[0] + sum(min_in[i] * y[i, d] for i in pool))
            m.add(z[d] >= min_out[0] + sum(min_out[i] * y[i, d] for i in pool))
            # volta ≥ início + durações + deslocamento
            m.add(f[d] >= inst.t_start + sum(places[i - 1].duration * y[i, d] for i in pool) + z[d])
        for i in pool:
            m.add(sum(y[i, d] for d in days) <= 1)
        index = {p.id: k + 1 for k, p in enumerate(places)}
        for pid, fixed in inst.mandatory.items():
            i = index[pid]
            m.add(y[i, fixed] == 1) if fixed is not None else m.add(sum(y[i, d] for d in days) == 1)
        if inst.budget is not None:
            m.add(
                sum(round(places[i - 1].price * PRICE_SCALE) * y[i, d] for i in pool for d in days)
                <= int(inst.budget * PRICE_SCALE)
            )

        for cls, S in self.nogoods:
            for d in days:
                if self.day_cls[d] == cls:
                    m.add(sum(y[i, d] for i in S) <= len(S) - 1)
        for cls, S, cost in self.opt_cuts:
            for d in days:
                if self.day_cls[d] == cls:
                    m.add(z[d] >= cost * (sum(y[i, d] for i in S) - len(S) + 1))
        for cls, S, back in self.finish_cuts:
            for d in days:
                if self.day_cls[d] == cls:
                    m.add(f[d] >= back * (sum(y[i, d] for i in S) - len(S) + 1))

        if mode == "travel":
            m.minimize(sum(z.values()))
        else:
            score = sum(round(places[i - 1].score * SCORE_SCALE) * y[i, d] for i in pool for d in days)
            m.add(sum(z.values()) <= t_cap)
            if mode == "score":
                m.maximize(score)
            else:  # finish: termina mais cedo, sem perder o score ótimo
                m.add(score >= s_cap)
                m.minimize(sum(f.values()))
        for (i, d), v in (hint or {}).items():
            m.add_hint(y[i, d], v)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max(time_limit, 0.1)
        solver.parameters.num_workers = 8
        st = solver.solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return st, None, None, None, None
        sets = [frozenset(i for i in pool if solver.value(y[i, d])) for d in days]
        return (
            st, sets, [solver.value(z[d]) for d in days], [solver.value(f[d]) for d in days],
            (solver.best_objective_bound, solver.objective_value),
        )


def solve_decomposed(inst: Instance, time_limit: float = 30.0) -> Result:
    started = time.monotonic()
    _validate(inst)
    inst = replace(inst, travel=metric_closure(inst.travel))
    days = range(len(inst.weekdays))
    pool = range(1, len(inst.places) + 1)

    # Dias com os mesmos horários para todo o pool compartilham cortes e cache.
    sigs = [
        tuple(tuple(arrival_intervals(p, wd, inst.lunch)) for p in inst.places)
        for wd in inst.weekdays
    ]
    ids = {s: k for k, s in enumerate(dict.fromkeys(sigs))}
    day_cls = [ids[s] for s in sigs]
    rep_weekday = {cls: inst.weekdays[day_cls.index(cls)] for cls in set(day_cls)}

    master = _Master(inst, day_cls)
    cache: dict = {}

    def route(cls: int, S):
        key = (cls, frozenset(S))
        if key not in cache:
            cache[key] = best_route(inst, rep_weekday[cls], key[1])
        return cache[key]

    def minimal_infeasible(cls: int, S: frozenset) -> frozenset:
        S = set(S)
        for i in sorted(S):
            if len(S) > 1 and route(cls, S - {i}) is None:
                S.discard(i)
        return frozenset(S)

    seen_cuts: set = set()

    def add_cut(cls: int, S: frozenset) -> None:
        """Corte de deslocamento para S (vale para todo T ⊇ S, por monotonia)."""
        if (cls, S) in seen_cuts:
            return
        seen_cuts.add((cls, S))
        r = route(cls, S)
        if r is None:
            master.nogoods.append((cls, S))
        else:
            master.opt_cuts.append((cls, S, r[0]))

    def add_subset_cuts(cls: int, S: frozenset) -> None:
        for size in range(2, len(S)):
            for sub in itertools.combinations(sorted(S), size):
                add_cut(cls, frozenset(sub))

    for cls in set(day_cls):
        for i in pool:
            add_cut(cls, frozenset({i}))
        for pair in itertools.combinations(pool, 2):
            add_cut(cls, frozenset(pair))
        if os.environ.get("BENDERS_TRIPLES"):
            for tri in itertools.combinations(pool, 3):
                add_cut(cls, frozenset(tri))

    log_it = [0]

    def run(mode: str, t_cap, s_cap, hint, budget_s: float):
        """Laço de Benders. Devolve (status, melhor, cota) com 'melhor' = (valor, sets)."""
        end = time.monotonic() + budget_s
        best, bound = None, None
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return "TIMEOUT", best, bound
            t_m = time.monotonic()
            st, sets, zs, fs, info = master.solve(
                mode=mode, t_cap=t_cap, s_cap=s_cap, hint=hint, time_limit=left
            )
            if os.environ.get("BENDERS_DEBUG"):
                print(
                    f"  [{mode}] it={log_it[0]} master={time.monotonic() - t_m:.1f}s "
                    f"obj={info and info[1]} bound={info and info[0]} left={left:.1f}s", flush=True,
                )
                log_it[0] += 1
            if sets is None:
                return ("INFEASIBLE" if st == cp_model.INFEASIBLE else "TIMEOUT"), best, bound
            if mode != "score":  # no score a cota é superior; nos outros, inferior
                bound = max(bound or 0, info[0])
            routes = [route(day_cls[d], sets[d]) for d in days]
            progress = False
            for d in days:
                r = routes[d]
                if r is None:
                    master.nogoods.append((day_cls[d], minimal_infeasible(day_cls[d], sets[d])))
                    progress = True
                    continue
                if r[0] > zs[d]:
                    add_cut(day_cls[d], sets[d])
                    add_subset_cuts(day_cls[d], sets[d])
                    progress = True
                if mode == "finish" and r[2] > fs[d]:
                    master.finish_cuts.append((day_cls[d], sets[d], r[2]))
                    progress = True
            if all(r is not None for r in routes):
                tot, fin = sum(r[0] for r in routes), sum(r[2] for r in routes)
                if mode == "travel":
                    if best is None or tot < best[0]:
                        best = (tot, sets)
                    if best[0] <= bound:
                        return "OPTIMAL", best, bound
                elif mode == "score":
                    if tot <= t_cap:
                        return "OPTIMAL", (round(info[1]), sets), bound
                elif tot <= t_cap:  # finish: o score ≥ Ŝ já é restrição exata do mestre
                    if best is None or fin < best[0]:
                        best = (fin, sets)
                    if best[0] <= bound:
                        return "OPTIMAL", best, bound
            if not progress:  # o mestre repetiu uma solução sem corte novo
                return "TIMEOUT", best, bound

    def hint_of(sets):
        return {(i, d): int(i in sets[d]) for d in days for i in pool}

    def remaining() -> float:
        return max(time_limit - (time.monotonic() - started), 1.0)

    # ---- Estágio 1: menor deslocamento ----
    st1, best1, lb = run("travel", None, None, None, time_limit)
    if st1 == "INFEASIBLE":
        from solver.diagnose import explain

        return Result("INFEASIBLE", conflicts=explain(inst), elapsed=time.monotonic() - started)
    if best1 is None:
        return Result("UNKNOWN", elapsed=time.monotonic() - started)
    t_hat, sets = best1
    status = "OPTIMAL" if st1 == "OPTIMAL" else "FEASIBLE"
    gap = 0.0 if status == "OPTIMAL" else (t_hat - (lb or 0)) / t_hat if t_hat > 0 else 0.0

    # ---- Estágio 2: maior score; Estágio 3: desempate, termina mais cedo ----
    stage2 = stage3 = None
    if status == "OPTIMAL":
        st2, best2, _ = run("score", t_hat, None, hint_of(sets), remaining())
        if best2 is not None and st2 == "OPTIMAL":
            s_hat, sets = best2
            stage2 = "OPTIMAL"
            st3, best3, _ = run("finish", t_hat, s_hat, hint_of(sets), remaining())
            if best3 is not None:
                sets, stage3 = best3[1], "OPTIMAL"

    plans, chosen = [], set()
    for d in days:
        cost, order, _ = route(day_cls[d], sets[d])
        arrivals, depart, back = simulate_day(inst, d, order)
        stops = [
            Stop(inst.places[i - 1].id, a, a + inst.places[i - 1].duration)
            for i, a in zip(order, arrivals)
        ]
        plans.append(DayPlan(d, inst.weekdays[d], stops, depart, back, cost))
        chosen.update(inst.places[i - 1].id for i in order)
    return Result(
        status=status,
        gap=gap,
        travel_total=sum(p.travel for p in plans),
        score_total=sum(p.score for p in inst.places if p.id in chosen),
        days=plans,
        stage2=stage2,
        stage3=stage3,
        elapsed=time.monotonic() - started,
    )
