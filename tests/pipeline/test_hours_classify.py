import json
from types import SimpleNamespace

from pipeline.classify import DEFAULT_DURATION, build_prompt, classify_all, classify_place
from pipeline.hours import parse_windows

from pathlib import Path

CITY_JSON = Path(__file__).resolve().parents[2] / "data" / "cities" / "florianopolis" / "city.json"


def period(od, oh, cd=None, ch=None, om=0, cm=0):
    p = {"open": {"day": od, "hour": oh, "minute": om}}
    if cd is not None:
        p["close"] = {"day": cd, "hour": ch, "minute": cm}
    return p


def test_google_sunday_zero_becomes_solver_sunday_six():
    # Google: dom=0, seg=1..sex=5 ; solver: seg=0 .. dom=6
    w = parse_windows({"periods": [period(0, 10, 0, 14), period(1, 9, 1, 17)]})
    assert w[6] == ((600, 840),) and w[0] == ((540, 1020),)
    assert 1 not in w  # terça fechada


def test_split_hours_and_overnight():
    w = parse_windows({"periods": [period(5, 9, 5, 12), period(5, 14, 5, 18), period(5, 18, 6, 2)]})
    # sexta (google 5 -> solver 4): 9-12, 14-24 (14-18 e 18-meia-noite fundem); sábado 0-2h
    assert w[4] == ((540, 720), (840, 1440))
    assert w[5] == ((0, 120),)


def test_24h_and_missing_hours():
    assert parse_windows({"periods": [period(0, 0)]}) == {d: ((0, 1440),) for d in range(7)}
    assert parse_windows(None) is None  # sem horário = sempre aberto
    assert parse_windows({}) is None


GOOD = {
    "category": "mirante", "is_dining": False, "is_paid": False, "est_price_brl": 30.0,
    "duration_min": 5000, "setting": "outdoor", "authenticity": 0.4, "touristy": 0.8,
    "gastronomy": 0.0, "culture": 0.2, "nature": 0.9, "landmark": 0.7,
    "evidence": ["x" * 400], "confidence": "media",
}


class FakeLLM:
    def __init__(self, payload):
        self.payload, self.calls = payload, 0

    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content=json.dumps(self.payload))


SEARCH = {"id": "a", "displayName": {"text": "Mirante X"}, "primaryType": "scenic_spot",
          "types": ["scenic_spot"], "rating": 4.7, "userRatingCount": 1200}
DETAILS = {"displayName": {"text": "Mirante X"}, "reviews": [{"rating": 5, "text": {"text": "Vista linda"}}]}


def test_postprocessing_fixes_implausible_duration_price_and_long_evidence():
    f = classify_place(FakeLLM(GOOD), SEARCH, DETAILS)
    assert f.duration_min == DEFAULT_DURATION["mirante"]  # 5000 min é implausível
    assert f.est_price_brl is None  # não pago -> sem preço
    assert len(f.evidence[0]) <= 160


def test_invalid_json_is_retried_then_raises():
    llm = FakeLLM({"category": "mirante"})  # incompleto
    try:
        classify_place(llm, SEARCH, DETAILS)
        raise AssertionError("deveria falhar")
    except ValueError:
        assert llm.calls == 2  # 1 tentativa + 1 retry com o erro


def test_prompt_contains_metadata_and_reviews():
    p = build_prompt(SEARCH, DETAILS)
    assert "Mirante X" in p and "1200" in p and "Vista linda" in p


def test_classify_all_is_resumable(tmp_path):
    (tmp_path / "details").mkdir()
    cands = [{**SEARCH, "id": f"p{i}"} for i in range(3)]
    (tmp_path / "candidates.json").write_text(json.dumps(cands))
    for c in cands:
        (tmp_path / "details" / f"{c['id']}.json").write_text(json.dumps(DETAILS))
    llm = FakeLLM(GOOD)
    assert classify_all(tmp_path, llm=llm, limit=2) == {"done": 2, "skipped": 0, "failed": 0}
    assert classify_all(tmp_path, llm=llm) == {"done": 1, "skipped": 2, "failed": 0}


def test_compact_contract_mentions_every_feature_field_and_category():
    from pipeline.classify import CONTRACT, Features

    for field in Features.model_fields:
        assert field in CONTRACT, f"contrato compacto não cita {field}"
    for cat in DEFAULT_DURATION:
        assert cat in CONTRACT


def test_merge_never_copies_review_snippets_into_places_json(tmp_path):
    import shutil

    from pipeline.merge import merge_city

    city = tmp_path / "c"
    (city / "details").mkdir(parents=True)
    (city / "classified").mkdir()
    shutil.copy(CITY_JSON, city / "city.json")
    cand = {**SEARCH, "id": "p0", "location": {"latitude": -27.6, "longitude": -48.5}}
    (city / "candidates.json").write_text(json.dumps([cand]))
    (city / "details" / "p0.json").write_text(json.dumps(DETAILS))
    (city / "classified" / "p0.json").write_text(json.dumps({**GOOD, "evidence": ["trecho de review"]}))
    merge_city(city)
    places = json.loads((city / "places.json").read_text(encoding="utf-8"))
    assert places and "evidence" not in places[0]["features"]
    assert "trecho de review" not in (city / "places.json").read_text(encoding="utf-8")


def test_committed_places_files_contain_no_review_text():
    """Qualquer cidade em data/cities: places.json não pode ter `evidence` (rede de segurança antes de um commit)."""
    from pathlib import Path

    for f in (Path(__file__).resolve().parents[2] / "data" / "cities").glob("*/places.json"):
        assert '"evidence"' not in f.read_text(encoding="utf-8"), f"{f} contém trechos de reviews: rode o merge de novo"
