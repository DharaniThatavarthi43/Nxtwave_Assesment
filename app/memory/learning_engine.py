from collections import defaultdict
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence
from uuid import UUID

from app.config import DEFAULT_TOPIC
from app.memory.memory_manager import MemoryManager
from app.schemas import (
    CheckpointId,
    CheckpointStatus,
    EvaluationResult,
    LearnedRule,
    RejectionRecord,
    utc_now,
)


RECURRENCE_THRESHOLD = 2
RULE_GUIDANCE: Mapping[CheckpointId, str] = MappingProxyType(
    {
        CheckpointId.ACCURACY_AND_GROUNDING: (
            "Check factual statements against the trusted notes and cite their support; "
            "qualify unsupported details rather than inventing them."
        ),
        CheckpointId.BEGINNER_FRIENDLY_LANGUAGE: (
            "Use short, plain-English sentences and explain unfamiliar AI words in "
            "everyday language."
        ),
        CheckpointId.TEACHING_THROUGH_EXAMPLES: (
            "Explain abstract RAG ideas with a relevant everyday example, then connect "
            "the example back to the concept."
        ),
        CheckpointId.CLEAR_EXPLANATIONS: (
            "Define each technical term in plain English before relying on it in later "
            "explanations."
        ),
        CheckpointId.KEY_CONCEPT_COVERAGE: (
            "Check for all eight required RAG topics before finalizing, and add any "
            "missing topic without removing required material."
        ),
        CheckpointId.TEACHING_FLOW: (
            "Teach in a gradual order: motivation and definitions, system components, "
            "workflow, benefits and limitations, then recap."
        ),
    }
)

RULE_REJECTION_REASON = (
    "Proposal is not the approved actionable template for its checkpoint; it may "
    "be vague, unsupported, or conflict with mandatory C1-C6 requirements."
)
REJECTED_RULE_PREFIX = "Rejected rule proposal: "


@dataclass(frozen=True)
class RuleDecision:
    rule: LearnedRule
    accepted: bool
    rejection_reason: str | None = None


def identify_failure_patterns(
    memory_manager: MemoryManager,
    *,
    topic: str = DEFAULT_TOPIC,
) -> dict[CheckpointId, tuple[RejectionRecord, ...]]:
    if not _is_supported_topic(topic):
        return {}

    evaluations_by_attempt = {
        (evaluation.run_id, evaluation.attempt_number): evaluation
        for evaluation in memory_manager.get_evaluation_history()
    }
    run_topics: dict[UUID, str | None] = {}
    patterns: dict[CheckpointId, list[RejectionRecord]] = defaultdict(list)

    for rejection in memory_manager.get_previous_failures():
        if rejection.run_id not in run_topics:
            run = memory_manager.get_run(rejection.run_id)
            run_topics[rejection.run_id] = (
                run.topic.strip().casefold() if run is not None else None
            )
        if run_topics[rejection.run_id] != DEFAULT_TOPIC.casefold():
            continue

        evaluation = evaluations_by_attempt.get(
            (rejection.run_id, rejection.attempt_number)
        )
        if evaluation is None or evaluation.overall_status is not CheckpointStatus.FAIL:
            continue
        failed_in_evaluation = set(evaluation.failed_checkpoints)
        for checkpoint_id in rejection.failed_checkpoints:
            if checkpoint_id in failed_in_evaluation:
                patterns[checkpoint_id].append(rejection)

    distinct_run_patterns: dict[CheckpointId, tuple[RejectionRecord, ...]] = {}
    for checkpoint_id, rejections in patterns.items():
        one_per_run: dict[UUID, RejectionRecord] = {}
        for rejection in rejections:
            one_per_run.setdefault(rejection.run_id, rejection)
        distinct_run_patterns[checkpoint_id] = tuple(one_per_run.values())
    return distinct_run_patterns


def learn_from_rejection(
    memory_manager: MemoryManager,
    rejection: RejectionRecord,
    *,
    topic: str = DEFAULT_TOPIC,
) -> tuple[RuleDecision, ...]:
    if not _is_supported_topic(topic):
        return ()

    patterns = identify_failure_patterns(memory_manager, topic=topic)
    decisions = []
    for checkpoint_id in rejection.failed_checkpoints:
        supporting_rejections = patterns.get(checkpoint_id, ())
        if len(supporting_rejections) < RECURRENCE_THRESHOLD:
            continue
        decisions.append(
            create_or_update_learned_rule(
                memory_manager,
                checkpoint_id=checkpoint_id,
                description=RULE_GUIDANCE[checkpoint_id],
                supporting_rejections=supporting_rejections,
            )
        )
    return tuple(decisions)


def create_or_update_learned_rule(
    memory_manager: MemoryManager,
    *,
    checkpoint_id: CheckpointId,
    description: str,
    supporting_rejections: Sequence[RejectionRecord],
) -> RuleDecision:
    checkpoint_id = CheckpointId(checkpoint_id)
    supporting = _distinct_run_rejections(checkpoint_id, supporting_rejections)
    if len(supporting) < RECURRENCE_THRESHOLD:
        raise ValueError(
            f"At least {RECURRENCE_THRESHOLD} distinct runs are required to learn a rule."
        )

    rejection_reason = validate_rule_description(checkpoint_id, description)
    stored_description = (
        RULE_GUIDANCE[checkpoint_id]
        if rejection_reason is None
        else (
            description.strip()
            if isinstance(description, str) and description.strip()
            else "[empty proposed rule]"
        )
    )
    rationale = _rule_rationale(
        checkpoint_id,
        len(supporting),
        rejection_reason=rejection_reason,
    )
    source_rejection_ids = tuple(
        sorted(
            (rejection.rejection_id for rejection in supporting),
            key=str,
        )
    )
    existing_rule = next(
        (
            rule
            for rule in memory_manager.get_learned_rules(checkpoint_id)
            if _normalize(rule.rule_description) == _normalize(stored_description)
        ),
        None,
    )

    if existing_rule is None:
        rule = LearnedRule(
            rule_description=stored_description,
            rationale=rationale,
            related_checkpoint=checkpoint_id,
            failure_count=len(supporting),
            confidence=1.0 if rejection_reason is None else 0.0,
            source_rejection_ids=source_rejection_ids,
            active_status=rejection_reason is None,
        )
        persisted_rule = memory_manager.save_learned_rule(rule)
    else:
        persisted_rule = memory_manager.update_learned_rule(
            existing_rule.model_copy(
                update={
                    "rationale": (
                        existing_rule.rationale
                        if existing_rule.rationale.startswith(REJECTED_RULE_PREFIX)
                        and rejection_reason is not None
                        else rationale
                    ),
                    "failure_count": len(supporting),
                    "confidence": 1.0 if rejection_reason is None else 0.0,
                    "source_rejection_ids": source_rejection_ids,
                    "active_status": (
                        existing_rule.active_status
                        if rejection_reason is None
                        else False
                    ),
                    "updated_at": utc_now(),
                }
            )
        )

    return RuleDecision(
        rule=persisted_rule,
        accepted=rejection_reason is None,
        rejection_reason=rejection_reason,
    )


def validate_rule_description(
    checkpoint_id: CheckpointId,
    description: str,
) -> str | None:
    checkpoint_id = CheckpointId(checkpoint_id)
    if not isinstance(description, str) or not description.strip():
        return RULE_REJECTION_REASON
    if _normalize(description) != _normalize(RULE_GUIDANCE[checkpoint_id]):
        return RULE_REJECTION_REASON
    return None


def get_relevant_learned_rules(
    memory_manager: MemoryManager,
    *,
    topic: str,
) -> tuple[LearnedRule, ...]:
    if not _is_supported_topic(topic):
        return ()

    relevant_rules = []
    seen_descriptions: set[tuple[CheckpointId, str]] = set()
    for rule in memory_manager.get_active_rules():
        rejection_reason = validate_rule_description(
            rule.related_checkpoint,
            rule.rule_description,
        )
        if rejection_reason is not None:
            memory_manager.update_learned_rule(
                rule.model_copy(
                    update={
                        "rationale": (
                            REJECTED_RULE_PREFIX
                            + rejection_reason
                            + " The unsafe stored rule was deactivated."
                        ),
                        "confidence": 0.0,
                        "active_status": False,
                        "updated_at": utc_now(),
                    }
                )
            )
            continue

        key = (rule.related_checkpoint, _normalize(rule.rule_description))
        if key in seen_descriptions:
            continue
        seen_descriptions.add(key)
        relevant_rules.append(rule)
    return tuple(relevant_rules)


def _distinct_run_rejections(
    checkpoint_id: CheckpointId,
    rejections: Sequence[RejectionRecord],
) -> tuple[RejectionRecord, ...]:
    one_per_run: dict[UUID, RejectionRecord] = {}
    for rejection in rejections:
        if checkpoint_id in rejection.failed_checkpoints:
            one_per_run.setdefault(rejection.run_id, rejection)
    return tuple(one_per_run.values())


def _rule_rationale(
    checkpoint_id: CheckpointId,
    distinct_run_count: int,
    *,
    rejection_reason: str | None,
) -> str:
    pattern = (
        f"Checkpoint {checkpoint_id.value} failed in {distinct_run_count} distinct "
        "Introduction to RAG runs. Supporting rejection records are linked for audit."
    )
    if rejection_reason is None:
        return (
            f"{pattern} The checkpoint-specific allowlist was validated and the "
            "rule was created active."
        )
    return (
        f"{REJECTED_RULE_PREFIX}{rejection_reason} The rule remains inactive. "
        f"{pattern}"
    )


def _is_supported_topic(topic: str) -> bool:
    return isinstance(topic, str) and topic.strip().casefold() == DEFAULT_TOPIC.casefold()


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()
