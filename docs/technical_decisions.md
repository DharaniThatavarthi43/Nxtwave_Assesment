# TECHNICAL DECISIONS DOCUMENT
## Self-Evaluating Agentic Lesson Content Generator

## 1. Purpose

This document records the technical architecture decisions for the project.

It explains:
- Selected technologies.
- Reasons for technology selection.
- Component responsibilities.
- Data flow.
- LLM interaction strategy.
- Memory architecture.
- Evaluation strategy.
- Retry mechanism.
- Reliability and security decisions.
- Trade-offs and limitations.

The objective is to create a modular, maintainable, testable and explainable agentic AI application.

# 2. Technology Selection

## 2.1 Python

Decision: Use Python as the primary programming language.

Reason:
- Strong ecosystem for AI and LLM development.
- Native support from LangChain and LangGraph.
- Good support for API integrations.
- Extensive testing and data-validation libraries.
- Suitable for modular application development.

## 2.2 LangGraph

Planned technology: LangGraph for agent workflow orchestration.

Reason:
- Supports graph-based execution.
- Allows separate nodes for generation, evaluation and regeneration.
- Supports conditional routing.
- Maintains shared execution state.
- Allows controlled retry loops.
- Supports workflow checkpointing.

Current implementation status:

LangGraph has not been integrated. The running application uses the bounded Python orchestrator in `app/workflow.py`; there is no graph, shared graph state, or LangGraph checkpointer. This is a documented deviation from the initial architecture plan and remains an assessment gap relative to that plan.

The direct workflow is covered by mocked tests and enforces the same approval, feedback, and retry rules, but those tests do not satisfy a requirement to use LangGraph.

## 2.3 LangChain

Decision: Use LangChain for LLM integration and prompt management.

Responsibilities:
- Configure the LLM provider.
- Send model requests.
- Manage prompts.
- Parse structured model responses.
- Support reusable model interactions.

Keep the LLM integration behind a reusable provider interface.

## 2.4 LLM Provider

Decision: Use Google Gemini as the LangChain provider integration.

Requirements:
- The model name and API key are supplied through environment variables.
- The API key must come from `LLM_API_KEY`; do not store it in source control.
- Provider-specific construction is isolated in `app/llm/provider.py`.
- Model interaction must be mockable during testing.
- Do not add a default model name or API credential.

The provider is selected with `LLM_PROVIDER=google`; the exact model and API credential remain deployment configuration. The adapter passes the configured key to `ChatGoogleGenerativeAI` without logging or exposing it. Additional provider integrations are out of scope unless needed later.

## 2.5 Pydantic

Decision: Use Pydantic for structured data validation.

Responsibilities:
- Validate lesson structures.
- Validate evaluator responses.
- Validate checkpoint statuses.
- Validate workflow-related data.
- Validate memory records where appropriate.

Reason:

LLMs may return malformed JSON, unexpected fields or missing values.

Pydantic provides a reliable validation boundary between LLM-generated data and application logic.

## 2.6 SQLite

Decision: Use SQLite for persistent memory and execution history.

Reason:
- No separate database server is required.
- Easy local development.
- Suitable for a take-home assessment.
- Supports relational records.
- Preserves data across application restarts.
- Easy to inspect and demonstrate during Loom.

SQLite is sufficient for the initial application.

A production deployment may later migrate to PostgreSQL.

## 2.7 Pytest

Decision: Use pytest.

Responsibilities:
- Unit testing.
- Integration testing.
- Workflow testing.
- Retry-limit testing.
- Memory testing.
- End-to-end testing.

Use mocked LLM responses to keep automated tests deterministic and reduce API costs.

## 2.8 Python Logging

Decision: Use Python's standard logging library.

Reason:
- No unnecessary logging dependency.
- Supports different log levels.
- Useful for tracking workflow execution.
- Supports debugging and error reporting.

# 3. High-Level Architecture

The application will follow a modular architecture.

Main components:

1. Input and configuration.
2. Reference knowledge loader.
3. Lesson generator.
4. Quality evaluator.
5. Regeneration engine.
6. LangGraph orchestrator.
7. Persistent memory manager.
8. Self-evolving learning engine.
9. Output and reporting service.

The components must remain independently testable.

# 4. Component Responsibilities

## 4.1 Input and Configuration Layer

Files:
- app/main.py
- app/config.py
- app/utils/validators.py

Responsibilities:
- Read topic input.
- Validate user configuration.
- Load environment variables.
- Initialize application dependencies.
- Start the workflow.

## 4.2 Reference Knowledge Layer

Files:
- app/knowledge/reference_loader.py
- app/knowledge/source_notes.md

Responsibilities:
- Load trusted RAG reference material.
- Provide relevant technical facts.
- Provide reference identifiers.
- Ensure the generator and evaluator use consistent source material.

Initial implementation decision:

Use a small, curated reference document.

Do not introduce a vector database or embedding-based retrieval system for the assignment itself unless the reference collection becomes too large.

The system is teaching RAG, not required to implement a complete production RAG retrieval engine.

## 4.3 Lesson Generator

File:
- app/agents/generator.py

Responsibilities:
- Construct generation instructions.
- Include learner profile.
- Include trusted references.
- Include previous learned rules.
- Call the LLM.
- Generate the complete lesson.
- Validate and return structured output.

The generator must not make its own approval decision.

## 4.4 Quality Evaluator

File:
- app/agents/evaluator.py

Responsibilities:
- Inspect the entire lesson.
- Check technical accuracy.
- Check beginner suitability.
- Check examples.
- Check jargon.
- Check completeness.
- Check logical flow.
- Return structured PASS/FAIL results.

The evaluator must be independent from the generator's approval logic.

## 4.5 Regeneration Engine

File:
- app/agents/regenerator.py

Responsibilities:
- Receive failed checkpoint results.
- Receive specific correction instructions.
- Improve the rejected lesson.
- Preserve correct content.
- Generate a complete revised lesson.
- Record changes.

The regenerator must not decide whether its own output passes.

Every regenerated lesson must be evaluated again.

## 4.6 Workflow Orchestrator

Files:
- app/workflow.py

Responsibilities:
- Maintain bounded execution state and history.
- Call the generator and evaluator.
- Route PASS and FAIL results.
- Control regeneration.
- Enforce retry limits.
- Terminate correctly.

The current implementation performs these operations in Python; LangGraph nodes and conditional edges are not implemented.

## 4.7 Persistent Memory

Files:
- app/memory/database.py
- app/memory/memory_manager.py

Responsibilities:
- Store execution records.
- Store attempts.
- Store evaluation results.
- Store rejection logs.
- Store learned rules.
- Retrieve historical information.

SQLite is the persistent storage layer.

## 4.8 Self-Evolving Learning Engine

File:
- app/memory/learning_engine.py

Responsibilities:
- Analyse repeated rejection patterns.
- Identify common failure categories.
- Create reusable improvement rules.
- Update existing rules.
- Provide relevant rules to future generation runs.

The learning engine must not modify the mandatory evaluation rubric.

## 4.9 Output and Reporting

File:
- app/services/output_service.py

Responsibilities:
- Save approved lessons.
- Save rejected candidates separately.
- Generate evaluation reports.
- Generate rejection logs.
- Generate execution summaries.

# 5. Architecture and Data Flow

The main execution flow is:

1. Application receives a topic.
2. Configuration is validated.
3. Previous memory is retrieved.
4. Trusted reference material is loaded.
5. Generator creates a lesson.
6. Evaluator checks six mandatory dimensions.
7. Evaluation response is validated.
8. Python determines the overall PASS/FAIL decision.
9. The Python workflow selects whether to approve, retry, or reject.
10. If PASS, the lesson is approved.
11. If FAIL, rejection details are saved.
12. If retries remain, regeneration is triggered.
13. The regenerated lesson is evaluated again.
14. Workflow terminates after approval or retry exhaustion.
15. Memory and reports are updated.

# 6. LLM Interaction Decisions

## 6.1 Separate Generator and Evaluator Responsibilities

Decision:

Use logically separate generation and evaluation components.

Reason:

The generator's responsibility is to create educational content.

The evaluator's responsibility is to identify whether the content meets the quality requirements.

Separating them improves modularity and testing.

The same underlying LLM model may initially be used for both components, but each must use a separate prompt and independent structured output contract.

Using different models is optional.

## 6.2 Structured Output

Decision:

Use structured JSON-like output validated with Pydantic.

Reason:
- Predictable application behaviour.
- Easier workflow decisions.
- Easier database storage.
- Easier testing.
- Reduced risk of parsing failures.

## 6.3 Temperature and Model Configuration

Decision:

Use configurable model settings.

Generation can use a moderate creativity setting, while evaluation should prioritize consistency and factual precision.

Do not assume a low temperature guarantees correctness.

Use rubric-based evaluation, source grounding and deterministic application logic to improve reliability.

## 6.4 Evidence-Based Evaluation

Decision:

Require evidence and reasons for failed checkpoints.

Reason:

An evaluator that only returns FAIL without explaining why is not useful for regeneration.

Evidence must identify the relevant lesson section or claim.

The evaluator must avoid inventing evidence or pretending that unsupported facts have been verified.

# 7. Evaluation Architecture Decisions

## 7.1 Six Mandatory Checkpoints

Use the exact six checkpoints:

1. Accuracy and grounding.
2. Beginner-friendly language.
3. Teaching through examples.
4. Jargon explanation.
5. Key concept coverage.
6. Logical teaching flow.

Do not replace them with a numerical scoring system.

## 7.2 Overall Decision

Decision:

Compute overall PASS/FAIL in Python.

Logic:

PASS only when all six checkpoint results are PASS.

Otherwise FAIL.

Reason:

The final approval decision must be deterministic.

The LLM may evaluate individual checkpoints, but Python controls the overall decision.

## 7.3 Evaluation Failure

Decision:

Malformed or incomplete evaluation results must never result in approval.

If evaluation validation fails:
- Record the operational error.
- Attempt bounded recovery where appropriate.
- Do not publish the lesson as approved.
- Terminate safely if evaluation cannot be recovered.

# 8. Regeneration and Retry Decisions

## 8.1 Retry Configuration

MAX_RETRIES = 2

Maximum generation attempts = 3.

## 8.2 Retry Logic

Initial generation:
Attempt 1.

First regeneration:
Attempt 2.

Second regeneration:
Attempt 3.

After the third failed evaluation:
Mark the execution as REJECTED.

## 8.3 Separation of Retry Types

Decision:

Maintain two different retry mechanisms.

A. Lesson-improvement retries:
- Maximum two retries.
- Controlled by application logic in `app/workflow.py`.

B. Transient API retries:
- Used for temporary network failures or rate limits.
- Separately bounded.
- Must not count as successful lesson regeneration.
- Must not permit an unlimited number of calls.

## 8.4 Regeneration Feedback

The regenerator receives:
- Previous lesson.
- Failed checkpoints.
- Failure reasons.
- Evidence.
- Correction instructions.
- Trusted references.

It must return a complete revised lesson.

# 9. Memory Architecture Decisions

## 9.1 Two Different Types of Memory

Decision:

Separate workflow checkpointing from long-term application memory.

### Workflow Checkpointing

Purpose:
- The current application does not implement workflow checkpointing or execution recovery.

Technology:
None. SQLite stores application run/attempt/evaluation history, not resumable graph state.

### Persistent Application Memory

Purpose:
- Retain previous executions.
- Store failures.
- Store evaluation results.
- Learn recurring patterns.
- Retrieve reusable rules across independent runs.

Technology:
SQLite.

These are separate responsibilities and must not be confused.

## 9.2 Memory Retrieval

Before generation:
1. Retrieve active rules for the supported lesson topic.
2. Verify each retrieved rule against the checkpoint-specific allowlist; deactivate and audit any unsafe stored rule.
3. Add only validated, relevant rules to the generator's existing learned-rules input.

Do not insert every historical record into every prompt.

Use relevance filtering to keep prompts concise.

In the current implementation, matching the fixed assessment topic makes rules relevant; inactive rules and rules for other topics are withheld. Learning guidance supplements the existing generator instructions and does not change the evaluator prompt, checkpoint definitions, or approval logic.

## 9.3 Self-Evolving Rules

Decision:

Use bounded rule-based feedback learning rather than unrestricted autonomous prompt modification.

A recurring failure must be identified before creating or updating a learned rule.

For example:

Repeated failure:
Unexplained technical terminology.

Learned rule:
Explain every important technical term using simple English and an everyday example.

For the fixed Introduction to RAG assessment, the recurrence threshold is two distinct execution runs with a failed evaluation and a matching rejection for the same checkpoint. Repeated attempts in one run count only once. The initial implementation groups by checkpoint; it does not claim semantic similarity matching between different failure descriptions.

Use checkpoint-specific approved guidance templates and require an exact normalized match. This allowlist prevents learned rules from weakening or bypassing C1-C6. A non-matching proposal is saved inactive with a rejection reason and its supporting rejection links for audit. Valid new rules are recorded as active with a rationale describing the recurrence and allowlist validation.

Deduplicate by normalized checkpoint ID and rule description. Update an existing matching rule's distinct-run count and source rejection links instead of creating a duplicate. Persist rules and their provenance in the existing `learned_rules` and `learned_rule_rejections` tables; do not add another history table.

The fixed-topic scope is intentional: the existing rule schema has no topic field and this assessment's lesson topic is Introduction to RAG. The rule must be stored and retrieved in later runs.

## 9.4 Protect Evaluation Standards

The six mandatory checkpoints are immutable during normal execution.

Memory may improve generation instructions but must not weaken the evaluator's pass conditions.

# 10. Database Design Decisions

Use SQLite with relational tables.

Required tables:

1. execution_runs.
2. generation_attempts.
3. evaluation_results.
4. rejection_logs.
5. learned_rules.

Use:
- Unique identifiers.
- Foreign keys.
- Timestamps.
- JSON serialization for structured evaluation details.
- Indexes for frequently queried fields.

Use database transactions for logically related writes.

Do not store sensitive credentials in the database.

# 11. Reference Material Decisions

Decision:

Use curated reference notes for the initial implementation.

Reason:
- The reference dataset is relatively small.
- It is sufficient for the fixed assessment topic.
- It avoids unnecessary vector-database infrastructure.
- It keeps the application simple.
- It makes source verification easier.

The generator and evaluator must use the same trusted knowledge base.

A future enhancement may introduce:
- Document embeddings.
- Vector search.
- Retrieval pipelines.
- Source-level citations.

These are not prerequisites for the initial assignment.

# 12. Testing Decisions

## 12.1 Mocked LLM Testing

Decision:

Use mocked LLM responses for automated tests.

Reason:
- Reproducible results.
- No API charges for every test.
- Faster test execution.
- Easier deliberate error injection.
- Reliable retry testing.

## 12.2 Real LLM Testing

Use real API calls for:
- Initial generation verification.
- Actual evaluation verification.
- Regeneration demonstration.
- Loom recording.

Keep real API tests separate from ordinary unit tests.

## 12.3 Test Coverage

Prioritize coverage of:
- Evaluation decisions.
- Retry limits.
- Workflow routing.
- Memory persistence.
- Learned-rule retrieval.
- Approval and rejection behaviour.

## 12.4 Test Integrity

Never weaken mandatory tests just to achieve a successful test report.

A test that fails because the implementation is incorrect must remain a failure until the actual issue is fixed.

# 13. Error Handling Decisions

The system must distinguish between:

A. Content quality failures.

Examples:
- Incorrect technical explanation.
- Missing example.
- Unexplained jargon.

These should cause lesson rejection and may trigger regeneration.

B. Operational failures.

Examples:
- API timeout.
- Missing credentials.
- Database error.
- Invalid response structure.

These should trigger error handling, bounded recovery or safe termination.

Operational errors must never be interpreted as successful evaluations.

# 14. Output Architecture Decisions

Approved output:

outputs/final_lesson.md

Rejected output:

outputs/rejected_candidate.md

Additional reports:

outputs/evaluation_report.json

outputs/rejection_log.md

outputs/execution_summary.json

Decision:

Keep structured reports and human-readable reports separate.

Reason:
- JSON is suitable for machine processing.
- Markdown is suitable for human inspection.
- Both provide useful demonstration evidence.

# 15. Security Decisions

- Store API keys in environment variables.
- Exclude .env from Git.
- Never print secrets.
- Use parameterized SQL queries.
- Validate user inputs.
- Avoid executing generated content as code.
- Treat LLM outputs as untrusted input.
- Validate all structured model responses.
- Keep dependencies minimal.
- Do not upload confidential information to external model providers.

# 16. Architectural Trade-offs

| Decision | Selected approach | Alternative not initially selected | Reason |
|---|---|---|---|
| Workflow | Bounded Python workflow (current) | LangGraph (planned) | Simple serial workflow; LangGraph remains an unimplemented deviation |
| Storage | SQLite | PostgreSQL | Simpler local setup |
| Data validation | Pydantic | Manual validation | Strong structured validation |
| Knowledge source | Curated reference notes | Vector database | Small fixed topic |
| Interface | CLI | Streamlit | Core workflow first |
| LLM | One configurable provider | Multiple models | Simpler integration |
| Testing | pytest with mocks | Only manual testing | Reproducibility |
| Memory | SQLite rules and history | Unrestricted autonomous memory | Controlled learning |

# 17. Known Limitations

The initial system will have the following limitations:

1. LLM-based evaluation is not a guarantee of factual correctness.
2. Simple reference material may not cover every possible technical claim.
3. Similarity-based failure detection may require careful tuning.
4. A single model may exhibit shared generation and evaluation biases.
5. The initial memory mechanism will use bounded learned rules rather than model training.
6. SQLite is suitable for a local assessment but not necessarily high-concurrency production usage.
7. The initial CLI will not provide a graphical user experience.

These limitations must be documented honestly.

# 18. Future Technical Improvements

Only after mandatory requirements are complete, consider:

- Separate generator and evaluator models.
- Multi-agent architecture.
- FastAPI service layer.
- Streamlit dashboard.
- PostgreSQL migration.
- Advanced semantic memory retrieval.
- Vector database integration.
- Multilingual generation.
- Human approval workflows.
- Model evaluation analytics.
- Docker deployment.
- Automated regression datasets.

These are optional and must not complicate the initial implementation.

# 19. Final Architecture Principle

The application uses an LLM integration for language generation and semantic quality assessment, Python for deterministic decisions and validation, and SQLite for persistent history and learned rules. The current workflow is a bounded Python orchestrator; LangGraph orchestration remains unimplemented.

Each component must have a clearly defined responsibility.

The system must be explainable, reproducible, bounded and independently testable.

END OF TECHNICAL DECISIONS DOCUMENT.