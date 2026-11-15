from pathlib import Path

import pytest

from app.knowledge.reference_loader import (
    DEFAULT_REFERENCE_PATH,
    ReferenceLoadError,
    REQUIRED_SECTIONS,
    load_reference_material,
)


def test_loads_curated_rag_reference_notes() -> None:
    material = load_reference_material()

    assert material.title == "Trusted Reference Notes: Introduction to RAG"
    assert all(
        f"## {section}" in material.content for section in REQUIRED_SECTIONS
    )
    assert {source.source_id for source in material.sources} == {
        "R1",
        "R2",
        "R3",
        "R4",
    }
    assert "cannot eliminate hallucinations" in material.content


def test_missing_reference_file_raises_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(ReferenceLoadError, match="Unable to read"):
        load_reference_material(tmp_path / "missing.md")


def test_missing_required_section_is_rejected(tmp_path: Path) -> None:
    markdown = DEFAULT_REFERENCE_PATH.read_text(encoding="utf-8")
    markdown = markdown.replace("## Benefits", "## Optional benefits", 1)
    path = tmp_path / "incomplete.md"
    path.write_text(markdown, encoding="utf-8")

    with pytest.raises(ReferenceLoadError, match="Benefits"):
        load_reference_material(path)


def test_invalid_reference_url_is_rejected(tmp_path: Path) -> None:
    markdown = DEFAULT_REFERENCE_PATH.read_text(encoding="utf-8")
    markdown = markdown.replace(
        "https://arxiv.org/abs/2005.11401",
        "https://",
        1,
    )
    path = tmp_path / "invalid-url.md"
    path.write_text(markdown, encoding="utf-8")

    with pytest.raises(ReferenceLoadError, match="Invalid metadata"):
        load_reference_material(path)
