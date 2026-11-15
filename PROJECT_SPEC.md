# NxtWave GenAI Engineer – Take-Home Assessment

## Project: Self-Evaluating Lesson Content Generator

## 1. Objective

Build an AI-powered system that generates educational lessons, evaluates their quality against predefined criteria, and automatically improves rejected lessons using evaluator feedback.

The system must demonstrate autonomous evaluation, controlled regeneration, persistent memory, and continuous improvement across multiple runs.

This is not just a lesson-generation application. It must implement a complete generate → evaluate → improve → approve/reject workflow.

## 2. Target Audience

The generated lesson must be designed for:

- An Indian student who has completed 12th grade.
- A student with limited English vocabulary.
- Someone from a non-English-medium educational background.
- Someone with no previous knowledge of Artificial Intelligence.
- Someone interested in starting a career in AI.

Use simple English, familiar examples, and a gradual teaching approach.

## 3. Fixed Topic

**Introduction to RAG (Retrieval-Augmented Generation)**

The generated lesson must independently explain:

1. What RAG is.
2. Why RAG is needed.
3. How RAG works.
4. The important components of a RAG system.
5. A simple real-world example of RAG.
6. How RAG differs from a normal LLM response.
7. Benefits and limitations of RAG.
8. A short recap of the key concepts.

The lesson must be understandable without requiring the learner to read external material.

## 4. Functional Requirements

### FR-01: Topic Input

- Accept a topic as input.
- Validate the input.
- Use the fixed assessment topic: Introduction to RAG.
- Allow the architecture to support additional topics in the future without compromising the required assessment demonstration.

### FR-02: Lesson Generation

Generate a complete, standalone beginner-friendly lesson.

The lesson must:
- Use simple English.
- Explain technical terms before using them.
- Include familiar examples and analogies.
- Follow a logical teaching sequence.
- Cover all required concepts.
- Avoid unsupported technical claims.

Use trusted reference material to ground factual explanations.

### FR-03: Quality Evaluation

Evaluate every generated lesson using six mandatory binary checkpoints.

Each checkpoint must return PASS or FAIL, with a reason and supporting evidence.

| ID | Checkpoint | PASS condition |
|---|---|---|
| C1 | Accuracy and grounding | Information is technically accurate and supported by trusted references. |
| C2 | Beginner-friendly language | Language is simple and suitable for the specified learner. |
| C3 | Teaching through examples | Relevant, understandable examples are included. |
| C4 | Clear explanations | Technical terms and jargon are explained before use. |
| C5 | Key concept coverage | All required RAG concepts are covered. |
| C6 | Teaching flow | Content follows a clear and logical learning sequence. |

A lesson passes only when **all six checkpoints PASS**.

The final PASS/FAIL decision must be calculated by application code. Do not blindly trust an LLM's overall evaluation.

### FR-04: Feedback and Regeneration

- If all six checkpoints PASS, approve the lesson.
- If any checkpoint FAILS, reject the current attempt.
- Record the failed checkpoint IDs, reasons, evidence, and correction instructions.
- Send the evaluator feedback to the regeneration process.
- Generate an improved lesson and evaluate it again.
- Allow a maximum of two retries after the initial generation.

Therefore, the maximum number of generation attempts is three.

### FR-05: Rejection Log

Maintain a detailed rejection log containing:

- Attempt number.
- Generated lesson or candidate reference.
- Failed checkpoints.
- Reasons for failure.
- Evaluator feedback.
- Changes made during regeneration.
- Final approval or rejection status.

If all three attempts fail, preserve the best rejected candidate and clearly mark the run as REJECTED.

Never present a rejected lesson as approved.

### FR-06: Persistent Memory

Implement persistent storage so information survives application restarts and can be reused across separate runs.

Store:
- Run history.
- Generated lesson attempts.
- Evaluation results.
- Rejection logs.
- Regeneration feedback.
- Learned improvement rules.

Use SQLite or another suitable persistent database.

### FR-07: Self-Evolving Mechanism

Demonstrate how the system learns from repeated failures.

The system should:

1. Identify recurring quality failures across runs.
2. Group similar failures into meaningful categories.
3. Create or update improvement rules when a defined recurrence threshold is reached.
4. Store rules with their reasons and supporting failure history.
5. Retrieve relevant rules during future lesson generation.
6. Apply learned rules to improve subsequent lessons.

The six mandatory evaluation checkpoints must never be weakened or removed by the learning mechanism.

This mechanism should improve prompts and generation guidance. It does not need to retrain the underlying LLM.

### FR-08: Output and Reporting

For every execution, produce:

- Final approved lesson, if successful.
- Evaluation results for every attempt.
- Rejection log.
- Regeneration history.
- Execution summary.
- Relevant learned improvement rules.

Keep approved and rejected outputs separate.

## 5. Expected Workflow

The complete system should follow this process:

1. Accept and validate the topic.
2. Load trusted reference material.
3. Retrieve relevant persistent memory and learned rules.
4. Generate the initial lesson.
5. Evaluate the lesson against all six checkpoints.
6. If PASS, approve and save the lesson.
7. If FAIL, record rejection reasons and feedback.
8. Regenerate using evaluator feedback if retries remain.
9. Evaluate the regenerated lesson again.
10. Stop after approval or a maximum of three generation attempts.
11. Save execution results and update persistent memory.
12. Learn from recurring failures for future runs.

## 6. Technical Expectations

Preferred technology stack:

- Python for application development.
- LangGraph for workflow orchestration.
- LangChain for LLM integration where useful.
- An LLM API provider for lesson generation and evaluation.
- Pydantic for structured data validation.
- SQLite for persistent memory.
- Pytest for automated testing.

Other suitable technologies may be used when justified.

Keep generation, evaluation, regeneration, memory, and orchestration logically separated.

## 7. Testing Requirements

Include automated tests for:

- Successful lesson generation.
- Each of the six evaluation checkpoints.
- PASS and FAIL decisions.
- Malformed or incomplete evaluator responses.
- Regeneration using evaluator feedback.
- Maximum retry enforcement.
- All attempts failing.
- Persistent memory across application restarts.
- Repeated failures creating learned rules.
- Learned rules being reused in future runs.
- Correct handling of approved and rejected outputs.
- API and database errors.

Use mocked LLM responses for deterministic automated tests.

Also demonstrate at least one deliberate lesson-quality failure that the evaluator detects and the system attempts to correct.

## 8. Submission Deliverables

### A. GitHub Repository

Include:
- Complete source code.
- Workflow implementation.
- Requirements/dependency file.
- README with project overview.
- Setup and execution instructions.
- Architecture explanation.
- Testing instructions.
- Sample outputs.

### B. Final Lesson Document

Provide a shareable document containing the final approved Introduction to RAG lesson.

Include evaluation results where appropriate.

### C. Loom Demonstration

Create a 15–20 minute demonstration.

The walkthrough should show:

1. Project architecture.
2. How to run the application.
3. Lesson generation.
4. Six-checkpoint evaluation.
5. A deliberate quality failure being detected.
6. Regeneration using evaluator feedback.
7. Final approval or rejection.
8. Persistent memory across runs.
9. Self-evolving improvement rules.
10. A brief explanation of important code components.

Keep your face visible during the walkthrough.

## 9. Acceptance Criteria

The project is considered complete only when:

- A standalone beginner-friendly RAG lesson can be generated.
- All six mandatory checkpoints are evaluated independently.
- Approval occurs only when every checkpoint passes.
- Failed lessons are regenerated using actionable feedback.
- No more than three generation attempts occur per run.
- Rejection logs contain the necessary failure details.
- Persistent memory works across separate runs.
- Repeated failures create reusable improvement rules.
- Learned rules influence future generation.
- Automated tests verify the important workflow paths.
- README and submission deliverables are complete.
- The Loom demonstration clearly proves the system works.

## 10. Engineering Principles

- Prefer simple, modular, maintainable code.
- Keep evaluation decisions explicit and deterministic.
- Never treat missing or malformed evaluation data as PASS.
- Never exceed the retry limit.
- Preserve complete execution history.
- Do not confuse persistent application memory with model training.
- Do not claim functionality is implemented until it has been tested.
- Document assumptions, limitations, and technical decisions.
- Prioritize assessment requirements over unnecessary features.

**Final Goal:** Build a working, testable, self-evaluating AI lesson-generation system that demonstrates quality control, autonomous improvement, and persistent learning—not merely an application that generates text.