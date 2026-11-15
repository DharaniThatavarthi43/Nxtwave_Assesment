# IMPLEMENTATION PLAN
## Self-Evaluating Agentic Lesson Content Generator

## 1. Development Strategy

The application will be developed incrementally using a phase-based implementation approach.

Each phase must be implemented, tested and verified before proceeding to the next phase.

The development process must follow these principles:

1. Implement only the current phase.
2. Follow the master requirements in PROJECT_SPEC.md.
3. Maintain modular and reusable code.
4. Avoid unnecessary dependencies.
5. Write executable code, not pseudocode.
6. Test every important component.
7. Maintain integration compatibility.
8. Do not implement optional enhancements before mandatory functionality is complete.
9. Never claim a feature is implemented without verification.
10. Update the implementation checklist after each completed phase.

## 2. Implementation Overview

| Phase | Name | Main outcome |
|---|---|---|
| 1 | Project Foundation | Working Python project |
| 2 | Reference Material and Data Models | Trusted knowledge and validated schemas |
| 3 | Persistent Storage | SQLite database and CRUD operations |
| 4 | Lesson Generation | Complete AI-generated RAG lesson |
| 5 | Quality Evaluation | Six strict PASS/FAIL checks |
| 6 | Feedback and Regeneration | Automatic lesson correction |
| 7 | LangGraph Orchestration | Complete agentic workflow |
| 8 | Persistent Memory and Self-Evolution | Cross-run learning |
| 9 | Output and Reporting | Lesson, evaluation and rejection reports |
| 10 | Testing and Error Handling | Verified application |
| 11 | Documentation and Submission | GitHub-ready project |

---

# PHASE 1 — PROJECT FOUNDATION

## Objective

Create a clean, executable Python application with configuration management, dependency management and logging.

## Task 1.1 — Inspect the Workspace

Actions:
1. Inspect the existing VS Code workspace.
2. Read PROJECT_SPEC.md.
3. Read project_goal.md.
4. Identify the Python version.
5. Check whether a virtual environment exists.
6. Avoid overwriting existing user files.

Expected result:
A verified development environment and an agreed folder structure.

## Task 1.2 — Create Project Structure

Create the mandatory directories:

- app/
- app/agents/
- app/memory/
- app/prompts/
- app/knowledge/
- app/services/
- app/utils/
- data/database/
- data/memory/
- outputs/
- tests/
- docs/

Create appropriate __init__.py files.

## Task 1.3 — Dependency Management

Create requirements.txt.

Include compatible dependencies for:
- LangGraph.
- LangChain.
- Selected LLM provider integration.
- Pydantic.
- python-dotenv.
- pytest.
- pytest-cov.

Use compatible pinned versions after testing.

Avoid installing unrelated packages.

## Task 1.4 — Configuration

Create:

app/config.py

Responsibilities:
- Load environment variables.
- Validate required configuration.
- Define LLM provider.
- Define model name.
- Define database path.
- Define retry count.
- Define logging level.
- Keep API keys secure.

Create .env.example.

Create .gitignore.

## Task 1.5 — Logging

Create:

app/utils/logger.py

Requirements:
- Consistent log format.
- Timestamp.
- Log level.
- Module name.
- Useful error details.
- No sensitive credentials.

## Task 1.6 — Application Entry Point

Create:

app/main.py

Responsibilities:
- Load configuration.
- Initialize logging.
- Validate environment.
- Initialize application dependencies.
- Provide a basic executable entry point.

## Phase 1 Verification

Run:

python -m app.main

Verify:
- Application imports successfully.
- Configuration loads.
- Missing environment variables are handled.
- No circular imports exist.
- Logging works.

Completion criteria:
All project foundations are executable.

---

# PHASE 2 — REFERENCE MATERIAL AND DATA MODELS

## Objective

Prepare trusted RAG knowledge and define validated application data structures.

## Task 2.1 — Research RAG

Prepare technical reference notes covering:

1. What RAG means.
2. Why RAG is used.
3. LLM limitations without external context.
4. Document collection.
5. Document chunking.
6. Embeddings.
7. Vector databases.
8. Retrieval.
9. Context injection.
10. Answer generation.
11. Benefits.
12. Limitations.
13. Applications.

Verify technical statements using reliable documentation.

## Task 2.2 — Store Reference Material

Create:

app/knowledge/source_notes.md

Store:
- Reference explanations.
- Source names.
- Source URLs.
- Relevant technical facts.
- Any important qualifications or limitations.

Create:

app/knowledge/reference_loader.py

Responsibilities:
- Load reference notes.
- Validate that material exists.
- Return structured reference content.
- Make references accessible to generator and evaluator.

## Task 2.3 — Create Pydantic Schemas

Create:

app/schemas.py

Define models for:

### Lesson
- lesson_id
- topic
- title
- attempt_number
- sections
- full_markdown
- reference_ids
- generation_timestamp

### EvaluationCheckpoint
- checkpoint_name
- status
- reason
- evidence

### EvaluationResult
- evaluation_id
- run_id
- attempt_number
- overall_status
- checkpoints
- failed_checkpoints
- correction_instructions
- overall_reason

### GenerationAttempt
- attempt_id
- run_id
- attempt_number
- generated_lesson
- timestamp

### RejectionRecord
- rejection_id
- run_id
- attempt_number
- failure_reason
- failed_checkpoint
- correction_applied
- timestamp

### LearnedRule
- rule_id
- rule_description
- related_checkpoint
- failure_count
- confidence
- timestamps
- active_status

Use enums for status fields.

Use strict validation and reject unexpected or invalid status values.

## Phase 2 Verification

- Verify reference material loads.
- Verify all mandatory schemas validate.
- Test invalid checkpoint names.
- Test invalid status values.
- Test missing required fields.

Completion criteria:
Reference knowledge and structured data validation work independently.

---

# PHASE 3 — PERSISTENT STORAGE

## Objective

Create the SQLite database and implement reliable persistence.

## Task 3.1 — Database Initialization

Create:

app/memory/database.py

Responsibilities:
- Create database connection.
- Initialize schema.
- Manage transactions.
- Handle connection failures.
- Provide safe connection cleanup.

## Task 3.2 — Create Tables

Create the following tables:

1. execution_runs
2. generation_attempts
3. evaluation_results
4. rejection_logs
5. learned_rules

Use appropriate:
- Primary keys.
- Foreign keys.
- Unique constraints.
- Indexes.
- Timestamps.
- JSON serialization where required.

## Task 3.3 — Repository Operations

Create:

app/memory/memory_manager.py

Implement:
- create_run()
- update_run_status()
- save_generation_attempt()
- save_evaluation_result()
- save_rejection()
- save_learned_rule()
- get_run_history()
- get_previous_failures()
- get_active_rules()
- get_attempt_history()

Use parameterized SQL queries.

Do not construct SQL queries by concatenating untrusted user input.

## Task 3.4 — Persistence Verification

Test:
- Creating records.
- Reading records.
- Updating records.
- Retrieving related records.
- Preserving records after application restart.

Completion criteria:
All required database operations work correctly.

---

# PHASE 4 — LESSON GENERATION

## Objective

Build the independent AI lesson-generation component.

## Task 4.1 — LLM Provider Integration

Create a configurable provider integration.

The provider should:
- Read model configuration.
- Read API credentials securely.
- Send requests.
- Receive responses.
- Handle timeout and rate-limit errors.
- Support deterministic mock responses in tests.

Keep provider-specific logic separate from generator logic.

## Task 4.2 — Generation Prompt

Create:

app/prompts/generator_prompt.py

The prompt must contain:

1. System role.
2. Project objective.
3. Target learner profile.
4. Topic.
5. Trusted reference material.
6. Mandatory lesson structure.
7. Language constraints.
8. Technical accuracy constraints.
9. Previous learned rules.
10. Output requirements.

## Task 4.3 — Generator Implementation

Create:

app/agents/generator.py

Implement:

generate_lesson()

Inputs:
- Topic.
- Learner profile.
- Reference material.
- Learned rules.
- Attempt number.
- Previous feedback, if available.

Outputs:
- Validated Lesson object.

## Task 4.4 — Lesson Structure Validation

Verify that the generated lesson contains:

1. Title.
2. Learning objectives.
3. Introduction.
4. RAG definition.
5. Why RAG is needed.
6. How RAG works.
7. Major RAG components.
8. Practical example.
9. Technical example or workflow.
10. Benefits.
11. Limitations.
12. Applications.
13. Terminology.
14. Summary.
15. Knowledge-check questions.
16. Answers.

The lesson must also follow the complete section requirements in PROJECT_SPEC.md.

## Task 4.5 — Generator Testing

Test:
- Valid generation.
- Empty response.
- Malformed response.
- API failure.
- Missing configuration.
- Incomplete lesson structure.

Completion criteria:
The generator produces a complete structured lesson using the configured LLM.

---

# PHASE 5 — QUALITY EVALUATION

## Objective

Build an independent evaluator that judges generated lessons against the six mandatory checkpoints.

## Task 5.1 — Evaluation Rubric

Create:

docs/evaluation_rubric.md

Document:
- Checkpoint name.
- Exact PASS conditions.
- Exact FAIL conditions.
- Expected evidence.
- Example passing content.
- Example failing content.

The rubric must remain consistent with PROJECT_SPEC.md.

## Task 5.2 — Evaluator Prompt

Create:

app/prompts/evaluator_prompt.py

The prompt must instruct the evaluator to:

- Act as an independent quality examiner.
- Inspect the entire lesson.
- Check technical claims against reference material.
- Evaluate each checkpoint separately.
- Return binary decisions.
- Explain every failure.
- Provide specific correction instructions.
- Avoid approving content merely because it is fluent.

## Task 5.3 — Evaluator Implementation

Create:

app/agents/evaluator.py

Implement:

evaluate_lesson()

Inputs:
- Generated lesson.
- Reference material.
- Evaluation rubric.

Outputs:
- Structured EvaluationResult.

## Task 5.4 — Binary Decision Engine

Implement the decision rule:

If all six checkpoints PASS:
overall_status = PASS

Otherwise:
overall_status = FAIL

The decision must be computed and verified in Python.

Do not rely exclusively on the LLM to decide the overall result.

## Task 5.5 — Evaluator Validation

Validate:
- Exactly six checkpoint results.
- All mandatory checkpoint names.
- Only PASS or FAIL values.
- Failure reasons.
- Evidence.
- Consistency of overall status.

Malformed evaluation responses must never result in approval.

## Task 5.6 — Evaluator Tests

Create controlled examples for:
- Correct technical explanation.
- Incorrect RAG explanation.
- Unexplained jargon.
- Missing examples.
- Missing mandatory sections.
- Disorganized lesson flow.

Verify that the evaluator identifies the corresponding failures.

Completion criteria:
The evaluator returns reliable structured PASS/FAIL decisions and actionable feedback.

---

# PHASE 6 — FEEDBACK AND REGENERATION

## Objective

Implement automatic correction of rejected lessons.

## Task 6.1 — Regeneration Prompt

Create:

app/prompts/regeneration_prompt.py

Include:
- Original lesson.
- Failed checkpoint results.
- Failure reasons.
- Evidence.
- Correction instructions.
- Trusted references.
- Learner profile.
- Previous attempt number.

## Task 6.2 — Regenerator Implementation

Create:

app/agents/regenerator.py

Implement:

regenerate_lesson()

Responsibilities:
- Inspect feedback.
- Identify affected sections.
- Correct failed areas.
- Preserve correct explanations.
- Generate a complete revised lesson.
- Record modifications.

## Task 6.3 — Feedback Traceability

For every regeneration, record:

- Previous lesson.
- Previous evaluation.
- Failed checkpoints.
- Feedback instructions.
- Updated lesson.
- Changes made.

## Task 6.4 — Regeneration Tests

Test:
- One failed checkpoint.
- Multiple failed checkpoints.
- Corrected lesson.
- Uncorrected lesson.
- Regeneration introducing a new error.

Completion criteria:
The regenerated lesson is based on actual evaluator feedback and is independently evaluated again.

---

# PHASE 7 — LANGGRAPH ORCHESTRATION

## Objective

Connect all components into a controlled agentic workflow.

## Task 7.1 — Define Shared State

Create:

app/state.py

Include:
- run_id
- topic
- learner_profile
- reference_material
- memory_rules
- current_lesson
- current_attempt
- max_retries
- evaluation_result
- failed_checkpoints
- correction_instructions
- attempt_history
- rejection_history
- final_status
- final_lesson_path

Use appropriate types.

## Task 7.2 — Create Workflow Nodes

Create nodes for:

1. Input validation.
2. Memory retrieval.
3. Reference retrieval.
4. Lesson generation.
5. Lesson evaluation.
6. Evaluation validation.
7. Rejection logging.
8. Regeneration.
9. Approval.
10. Rejection termination.
11. Report generation.
12. Memory update.

Each node must have one clear responsibility.

## Task 7.3 — Implement Conditional Routing

Use LangGraph conditional edges.

Routing rules:

PASS:
- Save approved lesson.
- Update memory.
- Generate reports.
- End workflow.

FAIL with retry available:
- Save rejection record.
- Increment attempt counter.
- Regenerate.
- Evaluate again.

FAIL with no retry remaining:
- Mark execution REJECTED.
- Preserve best candidate.
- Save final rejection report.
- End workflow.

## Task 7.4 — Retry Enforcement

Set:

MAX_RETRIES = 2

TOTAL_GENERATION_ATTEMPTS = 3

Implement the counter in application logic.

Never permit more than three lesson generations in a single execution.

Distinguish lesson regeneration attempts from transient API request retries.

## Task 7.5 — Workflow Testing

Test:

Scenario A:
First lesson passes.

Expected:
One generation and one evaluation.

Scenario B:
First lesson fails and second passes.

Expected:
Two generations and two evaluations.

Scenario C:
First two lessons fail and third passes.

Expected:
Three generations and three evaluations.

Scenario D:
All three lessons fail.

Expected:
Three generations and final REJECTED status.

Completion criteria:
All conditional routes terminate correctly.

---

# PHASE 8 — PERSISTENT MEMORY AND SELF-EVOLUTION

## Objective

Allow the system to retain previous feedback and improve future generation instructions across independent application runs.

## Task 8.1 — Memory Retrieval

Before generating a lesson:
- Retrieve previous execution records.
- Retrieve relevant rejection records.
- Retrieve active learned rules.
- Filter relevant rules by topic and checkpoint.
- Add the relevant rules to the generation context.

## Task 8.2 — Failure Pattern Detection

Create:

app/memory/learning_engine.py

Implement:

identify_failure_patterns()

Group recurring failures by:
- Checkpoint.
- Failure category.
- Similarity of failure descriptions.
- Repeated occurrence across separate executions.

## Task 8.3 — Rule Creation

Implement:

create_or_update_learned_rule()

Example:

Repeated failure:
Technical terminology is not being explained.

Learned rule:
Explain every important technical term immediately using simple English and an everyday example.

Rules must be:
- Traceable to historical failures.
- Relevant to a specific checkpoint.
- Reusable.
- Stored persistently.
- Protected against duplication.
- Activated only after the defined recurrence threshold.

## Task 8.4 — Rule Retrieval and Application

Implement:

get_relevant_learned_rules()

The generator must use active rules in subsequent executions.

The evaluator rubric must not be weakened or automatically rewritten.

## Task 8.5 — Cross-Run Testing

Run multiple independent executions.

Verify:
- Historical failures persist.
- Repeated patterns are identified.
- Learned rules are saved.
- Rules are retrieved after restart.
- The generator receives the rules.

Completion criteria:
Memory demonstrably affects future generation prompts.

---

# PHASE 9 — OUTPUT AND REPORTING

## Objective

Generate an isolated set of human-readable output files for each completed execution.

## Task 9.1 — Final Lesson Output

Create:

app/services/output_service.py

Store outputs in a unique directory under:

outputs/<UTC-timestamp>-run-<run-id>-<unique-token>/

For an approved execution, write:
- final_lesson.md
- evaluation_report.md
- execution_summary.md
- attempt_history.md
- learned_rules.md

For a rejected execution, write:
- rejected_lesson.md
- evaluation_report.md
- execution_summary.md
- attempt_history.md
- rejection_log.md
- learned_rules.md

The rejected lesson must be marked NOT APPROVED and must not be written as final_lesson.md. Select the candidate with the most passing checkpoints; if tied, select the latest attempt.

## Task 9.2 — Evaluation Report

Generate evaluation_report.md from persisted run history.

Include:
- All six checkpoint results.
- Reasons.
- Evidence.
- Overall decision.
- Attempt number.
- Run ID and execution timestamp.

## Task 9.3 — Rejection Log

For rejected executions, generate rejection_log.md.

Include:
- Every rejected attempt.
- Failure reasons.
- Feedback instructions.
- Corrections made.
- Subsequent evaluation results.

## Task 9.4 — Execution Summary

Generate execution_summary.md.

Include:
- Run ID.
- Topic.
- Final status.
- Total attempts.
- Start and end timestamps.
- Output locations.
- Memory update status.

## Task 9.5 — Output Verification

Verify:
- Files exist.
- File contents are valid.
- No unapproved lesson is published as final.
- Previous rejection records are preserved.
- Each output directory is unique and prior output is never overwritten.
- Output writing failures leave the persisted evaluation decision unchanged.
- Incomplete or failed workflow runs do not receive terminal output reports.

## Task 9.6 — Executable CLI

Update `app/main.py` so:
- `python -m app.main` prompts for a topic when `--topic` is omitted.
- The assessment CLI accepts only Introduction to RAG and rejects unrelated topics.
- The CLI validates LLM configuration, invokes the workflow with persistent memory, and writes the appropriate output set.
- It displays the terminal decision, run ID, attempt count, and output directory.
- Workflow and output errors are reported without exposing provider credentials or changing the persisted evaluation decision.

Completion criteria:
All required outputs are generated correctly from completed, persisted workflow data, and the CLI exposes the end-to-end execution.

---

# PHASE 10 — TESTING AND ERROR HANDLING

## Objective

Verify reliability, correctness and compliance with the assessment.

## Task 10.1 — Unit Testing

Test:
- Generator.
- Evaluator.
- Regenerator.
- Pydantic schemas.
- Memory manager.
- Learning engine.
- Retry logic.
- Output services.

## Task 10.2 — Integration Testing

Test:
- Generator and evaluator integration.
- Evaluator and regenerator integration.
- Database integration.
- Memory retrieval and generation integration.
- LangGraph execution.
- Report generation.

## Task 10.3 — End-to-End Testing

Execute the complete application using mock LLM responses.

Test:
1. First-attempt approval.
2. Second-attempt approval.
3. Third-attempt approval.
4. Final rejection.
5. Multiple checkpoint failures.
6. Deliberate factual error.
7. Malformed evaluator response.
8. Missing API configuration.
9. Persistent memory across runs.
10. Self-evolving rules across runs.

## Task 10.4 — Error Handling

Handle:
- API failures.
- Network failures.
- Invalid JSON.
- Missing reference material.
- Database errors.
- Empty model responses.
- Invalid evaluations.
- File-writing errors.
- Retry exhaustion.

Never convert an operational failure into an approval.

## Task 10.5 — Final Verification

Run:

pytest -v

Run coverage:

pytest --cov=app --cov-report=term-missing

Verify the actual application using:

python -m app.main

Completion criteria:
All mandatory acceptance tests pass and no critical issues remain.

---

# PHASE 11 — DOCUMENTATION AND SUBMISSION

## Objective

Prepare the complete repository and assessment demonstration.

## Task 11.1 — README

Document:
- Project objective.
- Problem statement.
- Architecture.
- Technology stack.
- Installation.
- Configuration.
- Execution.
- Database.
- Evaluation rubric.
- Agentic workflow.
- Memory.
- Self-evolution.
- Testing.
- Sample outputs.
- Limitations.

## Task 11.2 — Architecture Documentation

Explain:
- Each component.
- Responsibilities.
- Data flow.
- Graph nodes.
- Conditional routing.
- Retry logic.
- Memory flow.

## Task 11.3 — GitHub Preparation

Verify:
- All mandatory files exist.
- No secrets are committed.
- Requirements are reproducible.
- README commands work.
- Tests are included.
- Repository structure is clean.

## Task 11.4 — Loom Preparation

Record a 15–20 minute demonstration.

Show:
- Project introduction.
- Architecture.
- Complete execution.
- Deliberate evaluator failure.
- Feedback-driven regeneration.
- Persistent memory.
- Rejection logs.
- Final output.

Keep the presenter's face visible.

## Task 11.5 — Submission

Prepare:
1. GitHub repository link.
2. Final lesson document link.
3. Loom video link.

Submit through the NxtWave assessment form.

---

# 3. PHASE COMPLETION PROTOCOL

After completing every phase, the coding assistant must report:

1. Phase name.
2. Tasks completed.
3. Files created.
4. Files modified.
5. Dependencies installed.
6. Commands executed.
7. Tests executed.
8. Actual test results.
9. Known issues.
10. Requirements still pending.
11. Next phase.

Do not begin the next phase if the current phase has unresolved critical failures.

The developer must review and approve each phase.

# 4. GLOBAL IMPLEMENTATION RULES

- PROJECT_SPEC.md is the master requirements document.
- project_goal.md defines the intended outcome.
- requirement_traceability.md defines compliance mapping.
- technical_decisions.md defines architecture and technology choices.
- This implementation plan defines the execution sequence.

Do not change mandatory assessment requirements without explicit developer approval.

Do not remove tests to make the project appear successful.

Do not invent successful execution results.

Do not implement optional enhancements before mandatory requirements are verified.

END OF IMPLEMENTATION PLAN.