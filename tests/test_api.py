from fastapi.testclient import TestClient

from api.main import app
from api.places import DATA

client = TestClient(app)
CITY = "florianopolis"
HOTEL = {"hotel_lat": -27.589, "hotel_lng": -48.54}


def have_data():
    return (DATA / CITY / "places.json").exists() and (DATA / CITY / "matrix_walk.json").exists()


def test_cities_and_places():
    if not have_data():
        return
    cities = client.get("/api/cities").json()
    assert any(c["id"] == CITY and c["center"]["lat"] < 0 for c in cities)
    places = client.get(f"/api/cities/{CITY}/places").json()
    assert len(places) > 50 and {"id", "name", "lat", "lng", "tags", "duration_min", "region"} <= set(places[0])
    all_places = client.get(f"/api/cities/{CITY}/places", params={"include_food": True}).json()
    assert len(all_places) > len(places)  # comida fica fora por padrão


def test_route_feasible_and_infeasible_shapes():
    if not have_data():
        return
    places = client.get(f"/api/cities/{CITY}/places").json()
    near = [p["id"] for p in places if p["region"].startswith("Centro")][:3]
    r = client.post(
        f"/api/cities/{CITY}/route", json={**HOTEL, "place_ids": near, "day": "2026-10-21", "mode": "walk"}
    )
    assert r.status_code == 200
    body = r.json()
    if body["status"] in ("OPTIMAL", "FEASIBLE"):
        assert len(body["stops"]) == 3
        assert all({"name", "lat", "arrive", "travel_min"} <= set(s) for s in body["stops"])
        assert body["back"] >= body["stops"][-1]["leave"] + body["back_travel_min"]
    many = [p["id"] for p in places][:40]
    r = client.post(
        f"/api/cities/{CITY}/route", json={**HOTEL, "place_ids": many, "day": "2026-10-21", "mode": "car"}
    )
    assert r.status_code == 200 and r.json()["status"] == "INFEASIBLE" and r.json()["conflicts"]


def test_validation_errors():
    assert client.get("/api/cities/nao-existe/places").status_code == 404
    if not have_data():
        return
    base = {**HOTEL, "day": "2026-10-21"}
    url = f"/api/cities/{CITY}/route"
    assert client.post(url, json={**base, "place_ids": ["inexistente"]}).status_code == 422
    assert client.post(url, json={**base, "place_ids": []}).status_code == 422
    bad_window = {**base, "place_ids": ["x"], "t_start": "18:00", "t_end": "09:00"}
    assert client.post(url, json=bad_window).status_code == 422
    assert client.post(url, json={**base, "place_ids": ["x"], "t_start": "9h"}).status_code == 422
    assert client.get("/api/cities/..%2F..%2Fetc/places").status_code == 404


def test_places_missing_from_the_matrices_are_not_offered():
    if not have_data():
        return
    from api.places import routable_ids

    in_matrix = routable_ids(CITY)
    listed = {p["id"] for p in client.get(f"/api/cities/{CITY}/places", params={"include_food": True}).json()}
    assert listed <= in_matrix and listed


def test_api_does_not_import_llm_libraries():
    """O Docker instala só requirements.txt (sem langgraph/langchain): a API não pode depender deles."""
    import subprocess
    import sys

    code = (
        "import sys, api.main; "
        "bad = sorted({m.split('.')[0] for m in sys.modules} & {'langgraph', 'langchain_core', 'langchain_groq'}); "
        "print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]", out


def test_cities_list_every_configured_city_with_a_ready_flag():
    cities = {c["id"]: c for c in client.get("/api/cities").json()}
    assert {"florianopolis", "geneva", "montreal"} <= set(cities)
    assert all({"ready", "n_places", "partial", "center", "name"} <= set(c) for c in cities.values())
    for cid, c in cities.items():
        has_data = (DATA / cid / "places.json").exists() and (DATA / cid / "matrix_walk.json").exists()
        assert c["ready"] == (c["n_places"] > 0) and (not c["ready"] or has_data)
    if not cities["geneva"]["ready"]:  # cidade ainda sem dados: aparece, mas não oferece lugares nem roteiro
        assert client.get("/api/cities/geneva/places").status_code == 404
