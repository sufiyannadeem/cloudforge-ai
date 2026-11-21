from __future__ import annotations

from pathlib import Path

from app.rag import OperationalKnowledgeBase


def knowledge_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "knowledge"
    )


def test_documents_loaded():
    knowledge = OperationalKnowledgeBase(
        knowledge_path()
    )

    assert len(
        knowledge.documents
    ) >= 8


def test_high_error_rate_retrieval():
    knowledge = OperationalKnowledgeBase(
        knowledge_path()
    )

    results = knowledge.search(
        "high error rate deployment incident",
        top_k=5,
    )

    assert results
    assert any(
        "high-error-rate.md"
        in result.chunk.path
        for result in results
    )


def test_latency_retrieval():
    knowledge = OperationalKnowledgeBase(
        knowledge_path()
    )

    results = knowledge.search(
        "p95 latency high latency incident",
        top_k=5,
    )

    assert results
    assert any(
        "high-latency.md"
        in result.chunk.path
        for result in results
    )


def test_deployment_failure_retrieval():
    knowledge = OperationalKnowledgeBase(
        knowledge_path()
    )

    results = knowledge.search(
        "failed deployment image namespace commit",
        top_k=5,
    )

    assert results
    assert any(
        "deployment-failure.md"
        in result.chunk.path
        for result in results
    )


def test_slo_retrieval():
    knowledge = OperationalKnowledgeBase(
        knowledge_path()
    )

    results = knowledge.search(
        "availability SLO error budget",
        top_k=5,
    )

    assert results
    assert any(
        "cloudforge-slos.md"
        in result.chunk.path
        for result in results
    )


def test_context_generation():
    knowledge = OperationalKnowledgeBase(
        knowledge_path()
    )

    context = knowledge.build_context(
        "deployment caused high error rate",
        top_k=3,
    )

    assert (
        "CLOUDFORGE OPERATIONAL KNOWLEDGE"
        in context
    )

    assert "Source:" in context
    assert "Relevance:" in context
    assert "deployment" in context.lower()


def test_empty_query():
    knowledge = OperationalKnowledgeBase(
        knowledge_path()
    )

    assert (
        knowledge.search("")
        == []
    )


def run():
    print("========================================")
    print("OPERATIONAL RAG VALIDATION")
    print("========================================")

    test_documents_loaded()
    print("KNOWLEDGE DOCUMENT LOADING: PASS")

    test_high_error_rate_retrieval()
    print("HIGH ERROR RATE RETRIEVAL: PASS")

    test_latency_retrieval()
    print("LATENCY RETRIEVAL: PASS")

    test_deployment_failure_retrieval()
    print("DEPLOYMENT FAILURE RETRIEVAL: PASS")

    test_slo_retrieval()
    print("SLO RETRIEVAL: PASS")

    test_context_generation()
    print("CONTEXT GENERATION: PASS")

    test_empty_query()
    print("EMPTY QUERY HANDLING: PASS")

    print()
    print("ALL OPERATIONAL RAG TESTS PASSED")


if __name__ == "__main__":
    run()
