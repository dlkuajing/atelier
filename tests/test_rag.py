"""Tests for app.core.rag.store + /api/rag/lens-patents."""

from fastapi.testclient import TestClient

from app.core.lens_system import Scenario
from app.core.rag import LensPatentHit, MockLensPatentStore
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
    hits = store.search(
        query="lens", scenario=Scenario.SMARTPHONE_TELEPHOTO, top_k=1
    )
    assert len(hits) <= 1


def test_mock_store_top_k_zero_returns_empty():
    store = MockLensPatentStore()
    hits = store.search(
        query="lens", scenario=Scenario.SMARTPHONE_TELEPHOTO, top_k=0
    )
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
    assert "US20210311293A1" == top.id


# ---------------------------------------------------------------------------
# /api/rag/lens-patents endpoint
# ---------------------------------------------------------------------------


def test_lens_patents_endpoint_returns_200():
    r = client.post(
        "/api/rag/lens-patents",
        json={
            "query": "seven element telephoto lens",
            "scenario": "smartphone-telephoto",
            "top_k": 3,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["backend"] == "mock"
    assert data["scenario"] == "smartphone-telephoto"
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
            "query": "seven element telephoto",
            "scenario": "smartphone-telephoto",
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
