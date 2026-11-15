import re
from pathlib import Path

from pydantic import ValidationError

from app.schemas import ReferenceMaterial, ReferenceSource


DEFAULT_REFERENCE_PATH = Path(__file__).with_name("source_notes.md")
REQUIRED_SECTIONS = frozenset(
    {
        "What RAG means",
        "Why RAG is useful",
        "How a basic RAG system works",
        "Main components",
        "Documents, chunks, and embeddings",
        "Vector databases and retrieval",
        "Adding context and generating an answer",
        "RAG compared with a normal LLM response",
        "Benefits",
        "Limitations and cautions",
        "Common applications",
        "Simple example",
        "Key terms",
    }
)
SOURCE_PATTERN = re.compile(r"^- \[(R[1-9]\d*)\] (.+?) \| (https?://\S*)$")
CITATION_GROUP_PATTERN = re.compile(r"\[(R[^\]]*)\]")
CITATION_ID_PATTERN = re.compile(r"R[1-9]\d*")


class ReferenceLoadError(ValueError):
    """Raised when curated reference notes are missing or invalid."""


def load_reference_material(
    path: Path | str = DEFAULT_REFERENCE_PATH,
) -> ReferenceMaterial:
    reference_path = Path(path)
    try:
        markdown = reference_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReferenceLoadError(
            f"Unable to read reference notes at '{reference_path}': {exc}"
        ) from exc

    lines = markdown.splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ReferenceLoadError("Reference notes must start with a Markdown title.")
    title = lines[0][2:].strip()
    if not title:
        raise ReferenceLoadError("Reference notes title must not be empty.")

    reference_heading_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == "## References"
        ),
        None,
    )
    if reference_heading_index is None:
        raise ReferenceLoadError("Reference notes must contain a '## References' section.")

    headings = {
        line[3:].strip()
        for line in lines[1:reference_heading_index]
        if line.startswith("## ")
    }
    missing_sections = sorted(REQUIRED_SECTIONS - headings)
    if missing_sections:
        raise ReferenceLoadError(
            "Reference notes are missing required sections: "
            + ", ".join(missing_sections)
            + "."
        )

    body = "\n".join(lines[:reference_heading_index]).strip()
    source_lines = [
        line.strip()
        for line in lines[reference_heading_index + 1 :]
        if line.strip()
    ]
    sources: list[ReferenceSource] = []
    for line in source_lines:
        match = SOURCE_PATTERN.fullmatch(line)
        if match is None:
            raise ReferenceLoadError(
                "Each reference must use '- [R#] title | https://source-url' format."
            )
        source_id, source_title, url = match.groups()
        try:
            sources.append(
                ReferenceSource(source_id=source_id, title=source_title, url=url)
            )
        except ValidationError as exc:
            raise ReferenceLoadError(
                f"Invalid metadata for reference {source_id}: {exc}"
            ) from exc

    if not sources:
        raise ReferenceLoadError("Reference notes must list at least one source.")

    source_ids = {source.source_id for source in sources}
    cited_ids: set[str] = set()
    for citation_group in CITATION_GROUP_PATTERN.findall(body):
        citation_ids = [citation.strip() for citation in citation_group.split(",")]
        if any(CITATION_ID_PATTERN.fullmatch(citation) is None for citation in citation_ids):
            raise ReferenceLoadError(
                f"Invalid citation group '[{citation_group}]' in reference notes."
            )
        cited_ids.update(citation_ids)
    uncited_sources = sorted(source_ids - cited_ids)
    unknown_citations = sorted(cited_ids - source_ids)
    if uncited_sources:
        raise ReferenceLoadError(
            "Reference IDs are listed but not cited in the notes: "
            + ", ".join(uncited_sources)
            + "."
        )
    if unknown_citations:
        raise ReferenceLoadError(
            "Reference notes cite unknown source IDs: "
            + ", ".join(unknown_citations)
            + "."
        )

    version = next(
        (
            line.partition(":")[2].strip()
            for line in lines[1:reference_heading_index]
            if line.startswith("Version:")
        ),
        "",
    )
    if not version:
        raise ReferenceLoadError("Reference notes must include a non-empty Version.")

    try:
        return ReferenceMaterial(
            title=title,
            version=version,
            content=body,
            sources=tuple(sources),
        )
    except ValidationError as exc:
        raise ReferenceLoadError(f"Reference notes failed validation: {exc}") from exc
