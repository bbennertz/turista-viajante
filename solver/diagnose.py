"""Explicação de inviabilidade via núcleo de assunções do CP-SAT.

Cada grupo de restrições (contagem do dia, horizonte do dia, cada obrigatório,
orçamento) ganha um literal de assunção em `_build(guarded=True)`. Se o modelo é
infactível, `sufficient_assumptions_for_infeasibility` devolve um subconjunto de
grupos que já basta para a contradição.
"""

from __future__ import annotations

from ortools.sat.python import cp_model

from solver.model import Instance, _build


def describe(name: str, inst: Instance) -> str:
    kind, _, arg = name.partition(":")
    if kind == "count":
        return f"Dia {int(arg) + 1}: não cabem {inst.per_day} lugares (horários de funcionamento e deslocamento)"
    if kind == "horizon":
        return f"Dia {int(arg) + 1}: janela do dia ({inst.t_start // 60}h–{inst.t_end // 60}h) é curta demais"
    if kind == "mandatory":
        return f"Obrigatório '{arg}' não pode ser incluído (fechado nos dias disponíveis ou longe demais)"
    if kind == "budget":
        return "Orçamento insuficiente para os lugares exigidos"
    return name


def _infeasible_with(inst: Instance, active: set[str], time_limit: float) -> bool:
    """Só os grupos em `active` ficam ligados; os demais são relaxados."""
    b = _build(inst, guarded=True)
    b.model.clear_assumptions()  # senão os literais seriam forçados a verdadeiro
    for name, lit in b.guards.items():
        b.model.add(lit == (name in active))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 1
    return solver.solve(b.model) == cp_model.INFEASIBLE


def explain(inst: Instance, time_limit: float = 5.0) -> list[str]:
    """Núcleo de inviabilidade minimal: o núcleo do CP-SAT é só suficiente (na prática
    veio com todos os grupos), então reduz por remoção, um grupo por vez."""
    b = _build(inst, guarded=True)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 1  # extração de núcleo é confiável em thread única
    if solver.solve(b.model) != cp_model.INFEASIBLE:
        return []
    by_index = {lit.index: name for name, lit in b.guards.items()}
    core = {by_index[i] for i in solver.sufficient_assumptions_for_infeasibility() if i in by_index}
    for name in sorted(core):
        if _infeasible_with(inst, core - {name}, time_limit):
            core.discard(name)
    return [describe(name, inst) for name in sorted(core)]
