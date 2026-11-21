from __future__ import annotations

from pathlib import Path

from app.ai_evidence_package import (
    AIEvidencePackageBuilder,
)
from app.ai_tools import AIReadOnlyTools
from app.rag import OperationalKnowledgeBase
from app.test_ai_fixtures import (
    FakeIncidentStore,
    FakeDeploymentClient,
    FakePrometheusClient,
)


def build_tools():
    return AIReadOnlyTools(
        incident_store=FakeIncidentStore(),
        deployment_client=FakeDeploymentClient(),
        prometheus_client=FakePrometheusClient(),
    )


def build_knowledge_base():
    knowledge_dir = Path(__file__).resolve().parent.parent / "knowledge"
    return OperationalKnowledgeBase(knowledge_dir)


def test_package_contains_operational_evidence():
    builder = AIEvidencePackageBuilder(
        read_only_tools=build_tools(),
        knowledge_base=build_knowledge_base(),
    )

    package = builder.build(
        incident_id="incident-1",
        service="deployment-service",
        knowledge_query=(
            "deployment service high error rate incident"
        ),
    )

    assert (
        package.operational_evidence.incident_id
        == "incident-1"
    )

    assert len(
        package.operational_evidence.evidence
    ) == 3

    assert len(
        package.operational_evidence.successful_evidence()
    ) == 3


def test_package_contains_knowledge():
    builder = AIEvidencePackageBuilder(
        read_only_tools=build_tools(),
        knowledge_base=build_knowledge_base(),
    )

    package = builder.build(
        incident_id="incident-1",
        service="deployment-service",
        knowledge_query=(
            "high error rate deployment incident"
        ),
    )

    assert (
        "CLOUDFORGE OPERATIONAL KNOWLEDGE"
        in package.knowledge_context
    )

    assert (
        "high-error-rate.md"
        in package.knowledge_context
    )


def test_prompt_separates_evidence_and_knowledge():
    builder = AIEvidencePackageBuilder(
        read_only_tools=build_tools(),
        knowledge_base=build_knowledge_base(),
    )

    package = builder.build(
        incident_id="incident-1",
        service="deployment-service",
        knowledge_query=(
            "high error rate deployment incident"
        ),
    )

    prompt = package.to_prompt_context()

    assert (
        "AUTHORITATIVE OPERATIONAL EVIDENCE"
        in prompt
    )

    assert (
        "CONTEXTUAL OPERATIONAL KNOWLEDGE"
        in prompt
    )

    assert (
        "CLOUDFORGE OPERATIONAL EVIDENCE"
        in prompt
    )

    assert (
        "CLOUDFORGE OPERATIONAL KNOWLEDGE"
        in prompt
    )

    evidence_position = prompt.index(
        "AUTHORITATIVE OPERATIONAL EVIDENCE"
    )

    knowledge_position = prompt.index(
        "CONTEXTUAL OPERATIONAL KNOWLEDGE"
    )

    assert (
        evidence_position
        < knowledge_position
    )


def test_provenance_is_explicit():
    builder = AIEvidencePackageBuilder(
        read_only_tools=build_tools(),
        knowledge_base=build_knowledge_base(),
    )

    package = builder.build(
        incident_id="incident-1",
        service="deployment-service",
        knowledge_query=(
            "high error rate deployment incident"
        ),
    )

    operational_item = (
        package.operational_evidence.evidence[0]
    )

    assert (
        operational_item.evidence_type
        == "operational_telemetry"
    )

    assert (
        operational_item.authoritative
        is True
    )

    assert (
        "Evidence type: operational_knowledge"
        in package.knowledge_context
    )

    assert (
        "Authoritative: false"
        in package.knowledge_context
    )


def test_missing_incident_is_preserved():
    builder = AIEvidencePackageBuilder(
        read_only_tools=build_tools(),
        knowledge_base=build_knowledge_base(),
    )

    package = builder.build(
        incident_id="does-not-exist",
        service="deployment-service",
        knowledge_query="service down",
    )

    incident_evidence = (
        package.operational_evidence.evidence[0]
    )

    assert not incident_evidence.success

    assert (
        incident_evidence.source
        == "incident.get"
    )

    assert (
        incident_evidence.evidence_type
        == "operational_telemetry"
    )

    assert (
        incident_evidence.authoritative
        is True
    )


def run():
    print("========================================")
    print("AI EVIDENCE PACKAGE VALIDATION")
    print("========================================")

    test_package_contains_operational_evidence()
    print("OPERATIONAL EVIDENCE PACKAGE: PASS")

    test_package_contains_knowledge()
    print("KNOWLEDGE PACKAGE: PASS")

    test_prompt_separates_evidence_and_knowledge()
    print("EVIDENCE/KNOWLEDGE SEPARATION: PASS")

    test_provenance_is_explicit()
    print("EVIDENCE PROVENANCE: PASS")

    test_missing_incident_is_preserved()
    print("MISSING EVIDENCE HANDLING: PASS")

    print()
    print("ALL AI EVIDENCE PACKAGE TESTS PASSED")


if __name__ == "__main__":
    run()
