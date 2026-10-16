"""Converte regularOpeningHours do Google para as janelas que o solver espera.

Google numera os dias 0=domingo..6=sábado; o solver usa 0=segunda (datetime.weekday()).
Retorna {weekday: ((abre, fecha), ...)} em minutos desde 00:00; dia ausente = fechado.
Retorna None quando o Google não tem horário: o lugar é tratado como sempre aberto.
"""

from __future__ import annotations

from collections import defaultdict

Windows = dict[int, tuple[tuple[int, int], ...]]


def _minutes(point: dict) -> int:
    return point.get("hour", 0) * 60 + point.get("minute", 0)


def _weekday(google_day: int) -> int:
    return (google_day - 1) % 7


def parse_windows(opening_hours: dict | None) -> Windows | None:
    periods = (opening_hours or {}).get("periods")
    if not periods:
        return None
    # 24h todos os dias: um único período sem `close`, aberto no domingo 00:00
    if len(periods) == 1 and "close" not in periods[0]:
        return {d: ((0, 1440),) for d in range(7)}

    raw: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for p in periods:
        o, c = p["open"], p.get("close")
        od, om = _weekday(o["day"]), _minutes(o)
        if c is None:
            raw[od].append((om, 1440))
            continue
        cd, cm = _weekday(c["day"]), _minutes(c)
        if cd == od and cm > om:
            raw[od].append((om, cm))
        else:  # vira a meia-noite: parte no dia de abertura, resto no dia seguinte
            raw[od].append((om, 1440))
            if cm > 0:
                raw[cd].append((0, cm))

    out: Windows = {}
    for day, intervals in raw.items():
        merged: list[tuple[int, int]] = []
        for lo, hi in sorted(intervals):
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        out[day] = tuple(merged)
    return out
