import json

import pytest

from pipeline.details import fetch_all
from pipeline.places import BudgetExceeded


class FakeClient:
    def __init__(self, fail=(), budget=None):
        self.calls, self.fail, self.budget = [], set(fail), budget

    def details(self, place_id, language="en"):
        if self.budget is not None and len(self.calls) >= self.budget:
            raise BudgetExceeded("teto")
        self.calls.append(place_id)
        if place_id in self.fail:
            raise RuntimeError("Places API 500")
        return {"id": place_id, "reviews": [{"text": {"text": "ótimo"}}]}


CANDS = [{"id": f"p{i}"} for i in range(5)]


def test_fetch_is_resumable(tmp_path):
    first = FakeClient(fail={"p2"})
    assert fetch_all(first, CANDS, tmp_path) == {"fetched": 4, "skipped": 0, "failed": 1}
    second = FakeClient()
    assert fetch_all(second, CANDS, tmp_path) == {"fetched": 1, "skipped": 4, "failed": 0}
    assert second.calls == ["p2"]  # só o que faltava foi pedido de novo
    assert json.loads((tmp_path / "details" / "p0.json").read_text())["id"] == "p0"


def test_budget_exceeded_stops_the_batch_but_keeps_progress(tmp_path):
    with pytest.raises(BudgetExceeded):
        fetch_all(FakeClient(budget=2), CANDS, tmp_path)
    assert len(list((tmp_path / "details").glob("*.json"))) == 2


def test_google_field_masks_never_request_review_authors_or_unused_fields():
    from pipeline.places import DETAILS_MASK, SEARCH_MASK

    fields = DETAILS_MASK.split(",")
    assert "reviews" not in fields  # o campo inteiro traria nome, foto e perfil do autor
    assert not any("author" in f.lower() for f in fields)
    assert {"reviews.rating", "reviews.text"} <= set(fields)
    assert "places.formattedAddress" not in SEARCH_MASK.split(",")
