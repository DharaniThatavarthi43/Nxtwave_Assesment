from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from pypdf import PdfReader

from app.memory.database import connect
from app.schemas import ReferenceMaterial, ReferenceSource


EMBEDDING_DIMENSION = 32


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class KnowledgeDocumentRecord:
    document_id: UUID
    title: str
    source_type: str
    source_url: str | None
    content: str
    created_at: datetime


class KnowledgeBaseManager:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path).expanduser().resolve()

    def ingest_text(
        self,
        *,
        title: str,
        content: str,
        source_type: str = "manual",
        source_url: str | None = None,
    ) -> KnowledgeDocumentRecord:
        cleaned = self._normalize_content(content)
        if not cleaned:
            raise ValueError("Knowledge-base content must not be empty.")
        document_id = uuid4()
        created_at = datetime.now(timezone.utc)
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id, title, source_type, source_url, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(document_id),
                    title.strip() or "Untitled knowledge document",
                    source_type,
                    source_url,
                    cleaned,
                    created_at.isoformat(),
                ),
            )
            for chunk_index, chunk in enumerate(self._chunk_text(cleaned)):
                chunk_id = uuid4()
                embedding = self._embedding(chunk)
                connection.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        chunk_id, document_id, chunk_index, content, embedding_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(chunk_id),
                        str(document_id),
                        chunk_index,
                        chunk,
                        json.dumps(list(embedding)),
                        created_at.isoformat(),
                    ),
                )
        return KnowledgeDocumentRecord(
            document_id=document_id,
            title=title.strip() or "Untitled knowledge document",
            source_type=source_type,
            source_url=source_url,
            content=cleaned,
            created_at=created_at,
        )

    def ingest_url(self, url: str, *, title: str | None = None) -> KnowledgeDocumentRecord:
        normalized = self._normalize_url(url)
        text = self._fetch_url_text(normalized)
        return self.ingest_text(
            title=title or self._title_from_url(normalized),
            content=text,
            source_type="url",
            source_url=normalized,
        )

    def ingest_upload(
        self,
        *,
        filename: str,
        content: str,
        source_type: str = "upload",
    ) -> KnowledgeDocumentRecord:
        title = Path(filename).stem.strip() or "Uploaded document"
        return self.ingest_text(
            title=title,
            content=content,
            source_type=source_type,
            source_url=None,
        )

    def list_documents(self) -> list[KnowledgeDocumentRecord]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT document_id, title, source_type, source_url, content, created_at
                FROM knowledge_documents
                ORDER BY created_at DESC, document_id
                """
            ).fetchall()
        return [
            KnowledgeDocumentRecord(
                document_id=UUID(row["document_id"]),
                title=row["title"],
                source_type=row["source_type"],
                source_url=row["source_url"],
                content=row["content"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def retrieve(self, query: str, *, limit: int = 5, document_id: UUID | str | None = None) -> list[KnowledgeChunk]:
        if limit < 1:
            raise ValueError("Knowledge-base retrieval limit must be positive.")
        normalized_query = self._normalize_content(query)
        if not normalized_query:
            return []
        query_embedding = self._embedding(normalized_query)
        with connect(self.database_path) as connection:
            if document_id is None:
                rows = connection.execute(
                    """
                    SELECT chunk_id, document_id, chunk_index, content, embedding_json
                    FROM knowledge_chunks
                    ORDER BY chunk_index
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT chunk_id, document_id, chunk_index, content, embedding_json
                    FROM knowledge_chunks
                    WHERE document_id = ?
                    ORDER BY chunk_index
                    """,
                    (str(document_id),),
                ).fetchall()
        scored: list[tuple[float, KnowledgeChunk]] = []
        for row in rows:
            chunk_content = row["content"]
            chunk_embedding = tuple(json.loads(row["embedding_json"]))
            score = self._cosine_similarity(query_embedding, chunk_embedding)
            if score <= 0.0:
                continue
            chunk = KnowledgeChunk(
                chunk_id=UUID(row["chunk_id"]),
                document_id=UUID(row["document_id"]),
                chunk_index=row["chunk_index"],
                content=chunk_content,
                embedding=chunk_embedding,
            )
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]

    def build_reference_material(
        self,
        *,
        query: str,
        limit: int = 5,
        document_id: UUID | str | None = None,
    ) -> ReferenceMaterial:
        matches = self.retrieve(query, limit=limit, document_id=document_id)
        if not matches:
            raise ValueError("No chunks matched the supplied knowledge-base query.")
        document_map = {
            document.document_id: document
            for document in self.list_documents()
        }
        sources: list[ReferenceSource] = []
        sections: list[str] = []
        for index, chunk in enumerate(matches, start=1):
            document = document_map.get(chunk.document_id)
            if document is None:
                continue
            source_id = f"R{index}"
            source_url = document.source_url or "https://example.com/reference"
            sources.append(
                ReferenceSource(
                    source_id=source_id,
                    title=document.title,
                    url=source_url,
                )
            )
            sections.append(f"## {document.title}\n\n{chunk.content}")
        if not sources:
            raise ValueError("No sources could be collected from the knowledge-base matches.")
        content = "\n\n".join(sections)
        return ReferenceMaterial(
            title=f"Knowledge base results for: {query.strip()}",
            version="1.0",
            content=content,
            sources=tuple(sources),
        )

    def get_document(self, document_id: UUID | str) -> KnowledgeDocumentRecord | None:
        candidate = str(document_id)
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT document_id, title, source_type, source_url, content, created_at
                FROM knowledge_documents
                WHERE document_id = ?
                """,
                (candidate,),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeDocumentRecord(
            document_id=UUID(row["document_id"]),
            title=row["title"],
            source_type=row["source_type"],
            source_url=row["source_url"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def build_reference_material_for_document(
        self,
        *,
        document_id: UUID | str,
        query: str,
        limit: int = 5,
    ) -> ReferenceMaterial:
        document = self.get_document(document_id)
        if document is None:
            raise ValueError("The selected knowledge-base document could not be found.")
        matches = self.retrieve(query, limit=limit, document_id=document.document_id)
        if not matches:
            raise ValueError("The selected document has no matching chunks for the search query.")
        sources: list[ReferenceSource] = []
        chunks: list[str] = []
        for index, chunk in enumerate(matches, start=1):
            source_id = f"R{index}"
            sources.append(
                ReferenceSource(
                    source_id=source_id,
                    title=document.title,
                    url=document.source_url or "https://example.com/reference",
                )
            )
            chunks.append(f"## {document.title}\n\n{chunk.content}")
        return ReferenceMaterial(
            title=f"Knowledge base document: {document.title}",
            version="1.0",
            content="\n\n".join(chunks),
            sources=tuple(sources),
        )

    @staticmethod
    def _normalize_content(content: str) -> str:
        text = re.sub(r"\s+", " ", str(content)).strip()
        return text

    @staticmethod
    def _normalize_url(url: str) -> str:
        candidate = str(url).strip()
        if not candidate:
            raise ValueError("Knowledge-base URL must not be empty.")
        if "://" not in candidate:
            candidate = "https://" + candidate
        return candidate

    @staticmethod
    def _title_from_url(url: str) -> str:
        host = urlparse(url).netloc or "webpage"
        return host.replace("www.", "").split(":")[0].title()

    @staticmethod
    def _chunk_text(text: str, *, chunk_size: int = 400, overlap: int = 80) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
        chunks: list[str] = []
        buffer: list[str] = []
        current_length = 0
        for paragraph in paragraphs:
            length = len(paragraph)
            if buffer and current_length + length > chunk_size and buffer:
                chunks.append(" ".join(buffer))
                overlap_text = buffer[-1]
                buffer = [overlap_text]
                current_length = len(overlap_text)
            buffer.append(paragraph)
            current_length += length
        if buffer:
            chunks.append(" ".join(buffer))
        if not chunks:
            chunks = [text]
        merged: list[str] = []
        for index, chunk in enumerate(chunks):
            if index == 0:
                merged.append(chunk)
                continue
            previous = merged[-1]
            if len(previous) + len(chunk) <= chunk_size + overlap:
                merged[-1] = (previous + " " + chunk).strip()
            else:
                merged.append(chunk)
        return [segment.strip() for segment in merged if segment.strip()]

    @staticmethod
    def _embedding(text: str) -> tuple[float, ...]:
        tokens = re.findall(r"[a-z0-9]+", text.casefold())
        if not tokens:
            return tuple(0.0 for _ in range(EMBEDDING_DIMENSION))
        vector = [0.0 for _ in range(EMBEDDING_DIMENSION)]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], byteorder="big") % EMBEDDING_DIMENSION
            vector[index] += 1.0
        norm = (sum(value * value for value in vector)) ** 0.5
        if norm == 0:
            return tuple(0.0 for _ in range(EMBEDDING_DIMENSION))
        return tuple(value / norm for value in vector)

    @staticmethod
    def _cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
        left_values = list(left)
        right_values = list(right)
        if len(left_values) != len(right_values):
            return 0.0
        numerator = sum(a * b for a, b in zip(left_values, right_values, strict=True))
        left_norm = (sum(value * value for value in left_values)) ** 0.5
        right_norm = (sum(value * value for value in right_values)) ** 0.5
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _fetch_url_text(url: str) -> str:
        page = httpx.get(url, follow_redirects=True, timeout=15.0)
        page.raise_for_status()
        text = page.text
        cleaned = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        snippet = cleaned.strip()
        if not snippet:
            raise ValueError("The supplied webpage did not expose readable text.")
        return snippet

    @staticmethod
    def _extract_pdf_text(file_bytes: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
        except Exception as exc:  # pragma: no cover - fallback path
            raise ValueError("The PDF file could not be parsed.") from exc
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
        combined = "\n\n".join(pages)
        if not combined.strip():
            raise ValueError("The PDF file did not contain readable text.")
        return combined

    @staticmethod
    def _read_upload_bytes(filename: str, file_bytes: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            try:
                return file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return file_bytes.decode("utf-8", errors="replace")
        if suffix == ".pdf":
            return KnowledgeBaseManager._extract_pdf_text(file_bytes)
        raise ValueError("Unsupported file type. Add a PDF, TXT, or Markdown document.")
