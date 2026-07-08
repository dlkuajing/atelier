"""Tests for app.core.rag.store + /api/rag/lens-patents."""

import json

from fastapi.testclient import TestClient

from app.core.lens_system import Scenario
from app.core.rag import (
    LensPatentHit,
    MockLensPatentStore,
    RealLensCaseStore,
    get_default_store,
)
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# MockLensPatentStore behaviour
# ---------------------------------------------------------------------------


def test_mock_store_returns_smartphone_telephoto_hits():
    store = MockLensPatentStore()
    hits = store.search(
        query="seven element telephoto lens for smartphone",
        scenario=Scenario.SMARTPHONE_TELEPHOTO,
        top_k=5,
    )
    assert len(hits) > 0
    for h in hits:
        assert isinstance(h, LensPatentHit)
        assert 0.0 <= h.score <= 1.0


def test_mock_store_scenario_filter_works():
    """Smartphone-telephoto query in DSLR scenario yields nothing (no patents tagged for DSLR)."""
    store = MockLensPatentStore()
    hits = store.search(
        query="seven element telephoto lens",
        scenario=Scenario.DSLR_PRIME,
        top_k=5,
    )
    assert hits == []


def test_mock_store_ar_scenario_finds_ar_patent():
    store = MockLensPatentStore()
    hits = store.search(
        query="augmented reality waveguide near eye display",
        scenario=Scenario.AR_NEAR_EYE,
        top_k=5,
    )
    assert len(hits) >= 1
    assert any("waveguide" in h.title.lower() or "near" in h.title.lower() for h in hits)


def test_mock_store_scores_sorted_descending():
    store = MockLensPatentStore()
    hits = store.search(
        query="periscope folded telephoto smartphone six",
        scenario=Scenario.SMARTPHONE_TELEPHOTO,
        top_k=5,
    )
    if len(hits) >= 2:
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)


def test_mock_store_top_k_caps_results():
    store = MockLensPatentStore()
    hits = store.search(query="lens", scenario=Scenario.SMARTPHONE_TELEPHOTO, top_k=1)
    assert len(hits) <= 1


def test_mock_store_top_k_zero_returns_empty():
    store = MockLensPatentStore()
    hits = store.search(query="lens", scenario=Scenario.SMARTPHONE_TELEPHOTO, top_k=0)
    assert hits == []


def test_mock_store_backend_name():
    store = MockLensPatentStore()
    assert store.backend_name == "mock"


def test_mock_store_specific_query_ranks_periscope_higher():
    """A query mentioning periscope should rank the Largan periscope patent
    above the generic seven-element one."""
    store = MockLensPatentStore()
    hits = store.search(
        query="periscope folded smartphone",
        scenario=Scenario.SMARTPHONE_TELEPHOTO,
        top_k=5,
    )
    assert len(hits) >= 1
    # The periscope patent's title contains "Imaging Lens Assembly and Electronic Device"
    top = hits[0]
    assert top.id == "US20210311293A1"


# ---------------------------------------------------------------------------
# /api/rag/lens-patents endpoint
# ---------------------------------------------------------------------------


def test_lens_patents_endpoint_returns_200():
    r = client.post(
        "/api/rag/lens-patents",
        json={
            "query": "wide camera EFL 2.8 F2.4 FOV 78",
            "scenario": "smartphone-wide",
            "top_k": 3,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # real case library is active when index.json is present (committed); mock otherwise
    assert data["backend"] in ("real_case", "mock")
    assert data["scenario"] == "smartphone-wide"
    assert isinstance(data["hits"], list)


def test_lens_patents_endpoint_invalid_scenario_returns_422():
    r = client.post(
        "/api/rag/lens-patents",
        json={
            "query": "test",
            "scenario": "not-a-real-scenario",
            "top_k": 3,
        },
    )
    assert r.status_code == 422


def test_lens_patents_endpoint_short_query_rejected():
    r = client.post(
        "/api/rag/lens-patents",
        json={
            "query": "a",  # below min_length=2
            "scenario": "smartphone-telephoto",
            "top_k": 3,
        },
    )
    assert r.status_code == 422


def test_lens_patents_endpoint_top_k_max_enforced():
    r = client.post(
        "/api/rag/lens-patents",
        json={
            "query": "lens",
            "scenario": "smartphone-telephoto",
            "top_k": 100,  # over max=20
        },
    )
    assert r.status_code == 422


def test_lens_patents_endpoint_response_shape():
    r = client.post(
        "/api/rag/lens-patents",
        json={
            "query": "wide camera EFL 2.8 F2.4 FOV 78",
            "scenario": "smartphone-wide",
            "top_k": 5,
        },
    )
    assert r.status_code == 200
    data = r.json()
    if data["hits"]:
        h = data["hits"][0]
        for key in ("id", "title", "abstract", "assignee", "score", "source", "source_url"):
            assert key in h
        assert 0.0 <= h["score"] <= 1.0


# ---------------------------------------------------------------------------
# RealLensCaseStore — parameter-distance retrieval over the v2-02 case library
# ---------------------------------------------------------------------------


def _tiny_index(tmp_path):
    idx = tmp_path / "index.json"
    idx.write_text(
        json.dumps(
            [
                {
                    "case_id": "near",
                    "scenario": "smartphone-wide",
                    "n_pieces": 4,
                    "n_imaging": 4,
                    "n_filter": 1,
                    "efl_mm": 2.6,
                    "fnum": 2.2,
                    "fov_deg": 68.0,
                    "image_height_mm": 1.8,
                    "materials": ["BK7"],
                },
                {
                    "case_id": "far",
                    "scenario": "smartphone-wide",
                    "n_pieces": 5,
                    "n_imaging": 5,
                    "n_filter": 1,
                    "efl_mm": 3.9,
                    "fnum": 2.0,
                    "fov_deg": 84.0,
                    "image_height_mm": 3.3,
                    "materials": ["ZEONEX-E48R"],
                },
            ]
        )
    )
    return idx


def test_real_store_nearest_first(tmp_path):
    store = RealLensCaseStore(index_path=_tiny_index(tmp_path))
    hits = store.search_by_params(
        efl_mm=2.6, fnum=2.2, fov_deg=68.0, scenario=Scenario.SMARTPHONE_WIDE, top_k=2
    )
    assert len(hits) == 2
    assert hits[0].id == "near"  # exact-match design ranks first
    assert hits[0].score == max(h.score for h in hits)


def test_real_store_score_in_range_and_sorted(tmp_path):
    store = RealLensCaseStore(index_path=_tiny_index(tmp_path))
    hits = store.search_by_params(
        efl_mm=3.0, fnum=2.1, fov_deg=75.0, scenario=Scenario.SMARTPHONE_WIDE, top_k=5
    )
    scores = [h.score for h in hits]
    assert all(0.0 < s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_real_store_search_parses_query_params(tmp_path):
    store = RealLensCaseStore(index_path=_tiny_index(tmp_path))
    hits = store.search(
        query="wide design EFL 2.6 F2.2 FOV 68",
        scenario=Scenario.SMARTPHONE_WIDE,
        top_k=1,
    )
    assert len(hits) == 1
    assert hits[0].id == "near"  # parsed params steer to the nearest design


def test_real_store_empty_for_scenario_without_cases(tmp_path):
    store = RealLensCaseStore(index_path=_tiny_index(tmp_path))
    hits = store.search_by_params(
        efl_mm=7.0,
        fnum=2.4,
        fov_deg=30.0,
        scenario=Scenario.SMARTPHONE_TELEPHOTO,
        top_k=5,
    )
    assert hits == []  # no telephoto cases in the index


def _tiny_index_with_stale_telephoto(tmp_path):
    """A genuine long-focus record frozen as smartphone-wide in the index — the
    pre-fix state that made RAG telephoto search return nothing."""
    idx = tmp_path / "index.json"
    idx.write_text(
        json.dumps(
            [
                {
                    "case_id": "wide-main",
                    "scenario": "smartphone-wide",
                    "n_pieces": 5,
                    "n_imaging": 5,
                    "n_filter": 1,
                    "efl_mm": 3.9,
                    "fnum": 2.0,
                    "fov_deg": 84.0,
                    "image_height_mm": 3.3,
                    "materials": ["ZEONEX-E48R"],
                },
                {
                    "case_id": "tele-frozen-as-wide",
                    "scenario": "smartphone-wide",  # stale label; (EFL 12, FOV 20) => telephoto
                    "n_pieces": 6,
                    "n_imaging": 6,
                    "n_filter": 1,
                    "efl_mm": 12.0,
                    "fnum": 2.8,
                    "fov_deg": 20.0,
                    "image_height_mm": 3.7,
                    "materials": ["BK7"],
                },
            ]
        )
    )
    return idx


def test_real_store_derives_telephoto_from_stale_index(tmp_path):
    """RAG retrieval re-derives scenario from (FOV, EFL): a long-focus record
    frozen as smartphone-wide is retrievable under smartphone-telephoto and no
    longer pollutes the smartphone-wide pool."""
    store = RealLensCaseStore(index_path=_tiny_index_with_stale_telephoto(tmp_path))
    tele = store.search_by_params(
        efl_mm=12.0, fnum=2.8, fov_deg=20.0, scenario=Scenario.SMARTPHONE_TELEPHOTO, top_k=5
    )
    assert [h.id for h in tele] == ["tele-frozen-as-wide"]
    wide = store.search_by_params(
        efl_mm=3.9, fnum=2.0, fov_deg=84.0, scenario=Scenario.SMARTPHONE_WIDE, top_k=5
    )
    assert [h.id for h in wide] == ["wide-main"]  # telephoto seed left the wide pool


def test_real_store_committed_index_has_telephoto_hits():
    """End-to-end on the committed index.json: telephoto retrieval is non-empty
    (was empty pre-fix because every seed was frozen wide/ultrawide)."""
    store = RealLensCaseStore()
    hits = store.search_by_params(
        efl_mm=12.0, fnum=2.8, fov_deg=20.0, scenario=Scenario.SMARTPHONE_TELEPHOTO, top_k=3
    )
    assert hits
    assert all(h.id for h in hits)


def test_factory_uses_real_when_index_present():
    """With the committed case index, the default store is the real one."""
    get_default_store.cache_clear()
    try:
        assert get_default_store().backend_name == "real_case"
    finally:
        get_default_store.cache_clear()


def test_factory_falls_back_to_mock_without_index(monkeypatch, tmp_path):
    from app.core.rag import store as store_mod

    monkeypatch.setattr(store_mod, "_CASE_INDEX_PATH", tmp_path / "missing.json")
    get_default_store.cache_clear()
    try:
        assert get_default_store().backend_name == "mock"
    finally:
        get_default_store.cache_clear()  # restore real store for other tests
