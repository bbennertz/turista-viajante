import json
import math
import re

import httpx
import pytest

from pipeline import matrix as M


# ── ORS simulado (provedor alternativo) ────────────────────────────────────────
def fake_ors(unroutable=frozenset()):
    """ORS falso: duração = distância euclidiana (graus) × 6000 s; devolve null se um ponto for isolado."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        locs = body["locations"]
        rows = []
        for s in body["sources"]:
            row = []
            for d in body["destinations"]:
                a, b = locs[s], locs[d]
                if tuple(a) in unroutable or tuple(b) in unroutable:
                    row.append(None)
                else:
                    row.append(math.dist(a, b) * 6000)
            rows.append(row)
        return httpx.Response(200, json={"durations": rows})

    return httpx.Client(transport=httpx.MockTransport(handler))


# ── OSRM simulado (provedor padrão) ────────────────────────────────────────────
def fake_osrm(unroutable=frozenset(), fail_first=0, seen=None):
    """OSRM falso: GET /{service}/table/v1/{profile}/lng,lat;...?sources=..&destinations=.. Mesma geometria do ORS falso."""
    state = {"fails": fail_first}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["fails"] > 0:
            state["fails"] -= 1
            return httpx.Response(500, text="erro temporário")
        m = re.match(r"^/(routed-foot|routed-car)/table/v1/(foot|car)/(.+)$", request.url.path)
        assert m, request.url.path
        assert m.group(1) == f"routed-{m.group(2)}"  # serviço e perfil coerentes
        assert "turista-viajante" in request.headers["user-agent"]  # identifica o app (uso justo)
        locs = [tuple(map(float, c.split(","))) for c in m.group(3).split(";")]
        q = request.url.params
        sources = [int(x) for x in q["sources"].split(";")]
        dests = [int(x) for x in q["destinations"].split(";")]
        if seen is not None:
            seen.append(len(locs))
        rows = []
        for s in sources:
            row = []
            for d in dests:
                a, b = locs[s], locs[d]
                row.append(None if (a in unroutable or b in unroutable) else math.dist(a, b) * 6000)
            rows.append(row)
        return httpx.Response(200, json={"code": "Ok", "durations": rows})

    return httpx.Client(transport=httpx.MockTransport(handler))


COORDS = [(-27.0 - i * 0.01, -48.0 - (i % 7) * 0.01) for i in range(120)]  # 120 > TILE: exige 3×3 blocos


def expected(i, j, coords=COORDS):
    (la, lo), (lb, lob) = coords[i], coords[j]
    return math.ceil(math.dist((lo, la), (lob, lb)) * 6000 / 60)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(M.time, "sleep", lambda s: None)  # sem esperas reais


# ── OSRM (padrão) ──────────────────────────────────────────────────────────────
def test_default_provider_is_osrm_and_needs_no_key(monkeypatch):
    monkeypatch.delenv("ROUTING_PROVIDER", raising=False)
    monkeypatch.delenv("ORS_API_KEY", raising=False)
    monkeypatch.setattr(M, "load_env", lambda: None)  # não ler o .env real do usuário
    assert M.default_provider() == "osrm"
    m = M.city_matrix(COORDS[:5], "walk", http=fake_osrm())  # sem key, sem provider: usa o padrão
    assert m[0][1] == expected(0, 1)


def test_provider_env_var_is_validated(monkeypatch):
    monkeypatch.setattr(M, "load_env", lambda: None)
    monkeypatch.setenv("ROUTING_PROVIDER", "ors")
    assert M.default_provider() == "ors"
    monkeypatch.setenv("ROUTING_PROVIDER", "google")
    with pytest.raises(ValueError):
        M.default_provider()


@pytest.mark.parametrize("mode", ["walk", "car"])
def test_osrm_tiled_matrix_is_correct_and_requests_stay_within_100_coords(mode):
    seen = []
    m = M.city_matrix(COORDS, mode, http=fake_osrm(seen=seen), provider="osrm")
    n = len(COORDS)
    assert all(m[i][i] == 0 for i in range(n))
    for i, j in [(0, 119), (60, 3), (119, 0), (49, 50), (50, 49)]:
        assert m[i][j] == expected(i, j), (i, j)
    assert max(seen) <= 100 and len(seen) == 9  # 3×3 blocos, nenhum pedido acima do limite do servidor


def test_osrm_retries_temporary_errors_then_succeeds():
    http = fake_osrm(fail_first=2)
    m = M.city_matrix(COORDS[:4], "walk", http=http, provider="osrm")
    assert m[0][3] == expected(0, 3)


def test_live_hotel_request_gives_up_fast_so_the_app_can_fall_back():
    calls = []

    def always_500(request):
        calls.append(request.url.params.get("sources"))
        return httpx.Response(500, text="fora do ar")

    http = httpx.Client(transport=httpx.MockTransport(always_500))
    with pytest.raises(RuntimeError, match="após 2 tentativas"):
        M.hotel_times((-27.5, -48.5), COORDS[:3], "walk", http=http, provider="osrm")
    assert len(calls) == 2  # ao vivo: 2 tentativas, não 5


def test_osrm_gives_up_with_a_clear_error():
    with pytest.raises(RuntimeError, match="OSRM indisponível"):
        M.city_matrix(COORDS[:4], "walk", http=fake_osrm(fail_first=99), provider="osrm")


def test_osrm_error_code_is_reported():
    def bad(request):
        return httpx.Response(200, json={"code": "TooBig", "message": "Too many table coordinates"})

    with pytest.raises(RuntimeError, match="TooBig"):
        M.city_matrix(COORDS[:4], "walk", http=httpx.Client(transport=httpx.MockTransport(bad)), provider="osrm")


def test_osrm_unreachable_points_become_a_day_and_never_zero():
    iso = (COORDS[5][1], COORDS[5][0])  # (lng, lat), como o OSRM recebe
    m = M.city_matrix(COORDS[:10], "car", http=fake_osrm(unroutable={iso}), provider="osrm")
    assert m[5][2] == M.UNREACHABLE and m[2][5] == M.UNREACHABLE and m[5][5] == 0


def test_osrm_hotel_rows_and_pool_travel_shape():
    hotel = (-27.5, -48.5)
    to_p, from_p = M.hotel_times(hotel, COORDS[:4], "walk", http=fake_osrm(), provider="osrm")
    assert len(to_p) == len(from_p) == 4
    full = M.city_matrix(COORDS[:6], "walk", http=fake_osrm(), provider="osrm")
    ids = [f"p{i}" for i in range(6)]
    t = M.pool_travel(ids, full, ["p4", "p1"], to_p[:2], from_p[:2])
    assert len(t) == 3 and t[1][2] == full[4][1] and t[2][1] == full[1][4]
    assert t[0][1] == to_p[0] and t[1][0] == from_p[0] and t[0][0] == 0


def test_osrm_extend_matrix_only_queries_pairs_with_new_places_and_matches_full():
    full = M.city_matrix(COORDS[:8], "walk", http=fake_osrm(), provider="osrm")
    ids = [f"p{i}" for i in range(8)]
    old_ids, old = ids[:5], [row[:5] for row in full[:5]]
    seen = []
    ext = M.extend_matrix(old_ids, old, ids, COORDS[:8], "walk", http=fake_osrm(seen=seen), provider="osrm")
    assert ext == full
    assert seen and max(seen) <= 8 + 3  # só blocos com os 3 novos, nunca a cidade toda de novo
    shuffled = ["p6", "p0", "p3"]  # reaproveita por id, não por posição
    sub = M.extend_matrix(
        ids, full, shuffled, [COORDS[6], COORDS[0], COORDS[3]], "walk", http=fake_osrm(), provider="osrm"
    )
    assert sub[0][1] == full[6][0] and sub[1][2] == full[0][3] and sub[2][0] == full[3][6]


def test_matrix_files_record_their_provider_and_old_files_count_as_ors(tmp_path):
    ids = ["a", "b"]
    M.save_matrix(tmp_path, "walk", ids, [[0, 5], [6, 0]], provider="osrm")
    assert M.matrix_provider(tmp_path, "walk") == "osrm"
    assert M.load_matrix(tmp_path, "walk") == (ids, [[0, 5], [6, 0]])
    (tmp_path / "matrix_car.json").write_text(json.dumps({"ids": ids, "minutes": [[0, 1], [1, 0]]}))  # formato antigo
    assert M.matrix_provider(tmp_path, "car") == "ors"
    assert M.matrix_provider(tmp_path, "bike") is None


# ── ORS (alternativo) ──────────────────────────────────────────────────────────
def test_ors_tiled_matrix_equals_expected_and_has_zero_diagonal():
    m = M.city_matrix(COORDS, "walk", http=fake_ors(), key="k", provider="ors")
    n = len(COORDS)
    assert all(m[i][i] == 0 for i in range(n))
    for i, j in [(0, 119), (60, 3), (119, 0), (49, 50), (50, 49)]:
        assert m[i][j] == expected(i, j), (i, j)


def test_ors_unreachable_points_become_a_day():
    iso = (COORDS[5][1], COORDS[5][0])
    m = M.city_matrix(COORDS[:10], "car", http=fake_ors(unroutable={iso}), key="k", provider="ors")
    assert m[5][2] == M.UNREACHABLE and m[2][5] == M.UNREACHABLE and m[5][5] == 0


def test_ors_requires_a_key(monkeypatch):
    monkeypatch.delenv("ORS_API_KEY", raising=False)
    monkeypatch.setattr(M, "require", lambda name: (_ for _ in ()).throw(RuntimeError(f"{name} não definida")))
    with pytest.raises(RuntimeError, match="ORS_API_KEY"):
        M.city_matrix(COORDS[:3], "walk", http=fake_ors(), provider="ors")


def test_hotel_row_costs_a_single_request_and_matches_both_directions():
    calls = []
    http = fake_osrm(seen=calls)
    hotel = (-27.5, -48.5)
    to_p, from_p = M.hotel_times(hotel, COORDS[:6], "car", http=http, provider="osrm")
    assert len(calls) == 1 and calls[0] == 7  # um pedido, hotel + 6 lugares
    pts = [hotel, *COORDS[:6]]
    assert to_p == [expected(0, k, pts) for k in range(1, 7)]
    assert from_p == [expected(k, 0, pts) for k in range(1, 7)]


@pytest.mark.parametrize("error", [httpx.RemoteProtocolError("Server disconnected"), httpx.ConnectError("x"), httpx.ReadTimeout("x")])
def test_osrm_retries_dropped_connections_and_timeouts(error):
    state = {"n": 0}
    ok = fake_osrm()

    def flaky(request):
        state["n"] += 1
        if state["n"] <= 2:
            raise error
        return ok._transport.handle_request(request)

    m = M.city_matrix(COORDS[:4], "walk", http=httpx.Client(transport=httpx.MockTransport(flaky)), provider="osrm")
    assert m[0][3] == expected(0, 3) and state["n"] == 3
