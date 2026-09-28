from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    path: str
    title: str
    content: str


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    path: str
    title: str
    content: str


@dataclass(frozen=True)
class RetrievalResult:
    chunk: KnowledgeChunk
    score: float
    matched_terms: tuple[str, ...]
    evidence_type: str = "operational_knowledge"
    authoritative: bool = False
