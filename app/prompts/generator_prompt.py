from collections.abc import Sequence

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from app.schemas import LearnedRule, ReferenceMaterial


TARGET_LEARNER_PROFILE = (
    "An Indian student who has completed 12th grade, has limited English "
    "vocabulary, studied in a non-English-medium environment, has no prior "
    "knowledge of AI, and wants to start a career in AI."
)

REQUIRED_LESSON_SECTIONS = (
    "Learning Objectives",
    "Introduction",
    "What Is RAG?",
    "Why Is RAG Needed?",
    "How Does RAG Work?",
    "Main Components of a RAG System",
    "Simple Real-World Example",
    "Technical Workflow Example",
    "RAG Compared with a Normal LLM Response",
    "Benefits",
    "Limitations",
    "Common Applications",
    "Key Terms",
    "Recap",
    "Knowledge Check",
    "Answers",
)

NON_FACTUAL_SECTIONS = frozenset({"learning objectives", "knowledge check"})

SYSTEM_PROMPT = """\
You are an educational lesson writer. Create a complete, standalone lesson for
the specified beginner learner. Use simple English, define technical terms
before relying on them, teach gradually, and use relatable Indian examples.

Use only the supplied trusted reference notes for factual claims. Cite factual
explanations inline using square brackets containing one or more exact source
IDs from the valid source list. Separate multiple IDs with commas. Never invent
a source ID or claim that a citation supports something not present in the
notes. If the references do not support a factual detail, leave that detail
out.

Return structured content with a title and a sections object. Include every
required section exactly once using its exact heading, in the supplied order.
Do not omit, combine, duplicate, or rename a required section, and do not add
extra section keys. The sections object must use the exact required headings
as its keys.

Use only the valid source IDs listed with the reference notes. For every factual
section, include at least one inline citation containing the exact supported
ID or IDs in square brackets, with multiple IDs separated by commas. Do not
copy placeholder IDs, invent IDs, change capitalization, add leading zeroes,
or use another citation format. Learning Objectives and Knowledge Check are
the only sections that may omit citations. The application validates and
renders the final Markdown. Do not evaluate, approve, or reject the lesson.
"""

USER_PROMPT = """\
Topic: {topic}
Learner profile: {learner_profile}
Generation attempt: {attempt_number}

Required lesson sections, in this order:
{required_sections}

Trusted reference notes:
{reference_notes}

Valid source IDs for citations (use only these exact IDs):
{valid_source_ids}

Learned improvement rules to apply without omitting required topics:
{learned_rules}

Feedback from a previous attempt, if any:
{previous_feedback}

Return a sections object with all 16 required headings exactly once and in the
listed order. The per-section citation note beside each heading is mandatory.
Do not combine headings, use alternate spellings, or add duplicate heading
variants. Write a complete lesson that can be understood without external
reading.
Explain what RAG is, why it is needed, how it works, and its main components.
Include a simple real-world example, a technical step-by-step workflow example,
the difference from a normal LLM response, benefits, limitations, and a recap.
Also include useful applications, key terms, a short knowledge check, and
answers. In every factual section, include at least one square-bracketed
citation containing exact IDs from the valid source list above, separated by
commas when using multiple IDs. Each cited source must directly support a
factual claim in that section. Never copy placeholder IDs or cite a source that
does not support the claim. If the curated notes do not support a detail, omit
that detail instead of guessing or adding a citation. Learning Objectives and
Knowledge Check may be uncited; Answers is factual and must be cited. The
knowledge check should test understanding of the lesson; put answers only in
the Answers section.
"""

GENERATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ]
)


def format_generation_messages(
    *,
    topic: str,
    learner_profile: str,
    reference_material: ReferenceMaterial,
    learned_rules: Sequence[str | LearnedRule] = (),
    attempt_number: int,
    previous_feedback: Sequence[str] = (),
) -> list[BaseMessage]:
    formatted_rules = []
    for rule in learned_rules:
        if isinstance(rule, LearnedRule):
            formatted_rules.append(
                f"- {rule.rule_description} Reason: {rule.rationale}"
            )
        else:
            formatted_rules.append(f"- {rule}")

    required_sections = []
    for index, heading in enumerate(REQUIRED_LESSON_SECTIONS, start=1):
        citation_note = (
            "citation optional"
            if heading.casefold() in NON_FACTUAL_SECTIONS
            else "include at least one relevant valid citation"
        )
        required_sections.append(f"{index}. {heading} - {citation_note}")

    return GENERATOR_PROMPT.format_messages(
        topic=topic,
        learner_profile=learner_profile,
        attempt_number=attempt_number,
        required_sections="\n".join(required_sections),
        reference_notes=reference_material.content,
        valid_source_ids=", ".join(
            source.source_id for source in reference_material.sources
        ),
        learned_rules="\n".join(formatted_rules) or "- None",
        previous_feedback="\n".join(
            f"- {feedback}" for feedback in previous_feedback
        )
        or "- None",
    )
