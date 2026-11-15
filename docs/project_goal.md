# PROJECT GOAL
## Self-Evaluating Agentic Lesson Content Generator
### NxtWave – GenAI Engineer, Content Systems Assessment

## 1. Project Overview

The objective of this project is to design and develop an autonomous, self-evaluating AI content-generation system that generates beginner-friendly educational lessons, evaluates their quality against predefined criteria, identifies weaknesses, and automatically regenerates rejected content until it satisfies all mandatory quality requirements or reaches a defined retry limit.

The system will demonstrate an end-to-end agentic workflow rather than a simple prompt-based content-generation application.

The application will use Python, LangGraph, LangChain, an LLM API, Pydantic and SQLite to implement lesson generation, quality evaluation, conditional decision-making, feedback-driven regeneration and persistent memory.

## 2. Problem Statement

Traditional AI content-generation systems generate responses based on prompts but do not necessarily verify whether the generated content is accurate, understandable, complete or appropriate for its intended audience.

A generated lesson may:
- Contain technically incorrect information.
- Use complex English.
- Include unexplained technical terminology.
- Miss important concepts.
- Provide weak or misleading examples.
- Present information in a confusing order.

These problems are especially important in educational content because learners may depend on the generated material to understand unfamiliar concepts.

The project addresses this problem by introducing an independent evaluation mechanism that checks generated educational content before it is approved.

## 3. Primary Project Goal

Build an agentic AI system that follows this lifecycle:

**Generate → Evaluate → Decide → Regenerate → Approve or Reject → Store Feedback → Learn Across Runs.**

The system must independently determine whether a generated lesson meets the required quality standards.

It must not depend on a human to manually inspect and correct every generation attempt.

## 4. Assessment Topic

The fixed topic for the initial assessment is:

**Introduction to RAG (Retrieval-Augmented Generation).**

The application must generate a complete educational lesson about RAG.

The lesson must teach:
- What RAG is.
- Why RAG is needed.
- How RAG works.
- The major components of RAG.
- A practical real-world example.
- Benefits and limitations.
- Important technical terminology.

The content must be technically accurate and grounded in trusted reference material.

## 5. Target Audience

The generated lesson must be designed for:

- A student who has completed 12th grade in India.
- A complete beginner in Artificial Intelligence.
- A learner with limited English vocabulary.
- A student from a non-English-medium educational background.
- Someone who wants to begin an AI career.

The system must not assume prior knowledge of programming, machine learning, embeddings, vector databases or large language models.

## 6. Intended System Behaviour

The completed application must perform the following operations.

### 6.1 Accept Input

Accept the topic, learner profile, evaluation rubric, reference material and retry configuration.

### 6.2 Retrieve Knowledge

Load trusted RAG reference material and relevant historical feedback from persistent memory.

### 6.3 Generate Lesson

Use an LLM to create a complete beginner-friendly lesson.

### 6.4 Evaluate Quality

Evaluate the lesson against six mandatory binary checkpoints:

1. Accuracy and grounding.
2. Beginner-friendly language.
3. Teaching through examples.
4. Jargon explanation.
5. Key concept coverage.
6. Logical teaching flow.

Each checkpoint must return PASS or FAIL.

### 6.5 Make an Autonomous Decision

If all six checkpoints PASS, approve the lesson.

If one or more checkpoints FAIL, reject the lesson and prepare correction instructions.

### 6.6 Regenerate Content

Pass evaluator feedback to the generator and create an improved lesson.

Allow a maximum of two retries after the initial generation.

Maximum generation attempts per execution: Three.

### 6.7 Maintain Rejection History

Record every failed checkpoint, its explanation, the correction instructions and the changes made during regeneration.

### 6.8 Maintain Persistent Memory

Store execution history, generated lessons, evaluation results, rejection records and learned rules in SQLite.

Retrieve relevant previous failures during future executions.

### 6.9 Learn from Repeated Failures

Identify recurring failure patterns across separate executions.

Convert recurring patterns into reusable generation rules.

Use these rules in future generation prompts without weakening the mandatory evaluation rubric.

### 6.10 Publish Final Result

If approved, publish the final lesson in Markdown.

If rejected after all attempts, retain the best candidate and generate a rejection report without falsely marking it as approved.

## 7. Project Scope

### In Scope — Mandatory

- Python-based application.
- LLM integration.
- Separate lesson generator.
- Separate quality evaluator.
- Six binary evaluation checkpoints.
- Structured evaluation responses.
- Feedback-driven regeneration.
- Maximum two retries.
- LangGraph workflow orchestration.
- Persistent SQLite memory.
- Rejection logging.
- Repeated failure identification.
- Self-evolving generation rules.
- Trusted reference material.
- Final lesson generation.
- Evaluation and execution reports.
- Automated tests.
- GitHub repository and README.
- Loom video demonstration.

### Out of Scope — Initial Implementation

- Training an LLM from scratch.
- Building a production-grade RAG search engine.
- Building a commercial learning management system.
- Creating a student-facing learning platform.
- Building a complex frontend.
- Deploying a production SaaS application.
- Implementing unrestricted autonomous agents.
- Automatically modifying mandatory evaluation standards.

Optional enhancements must not delay mandatory functionality.

## 8. Expected Final Deliverables

### Deliverable 1: GitHub Repository

A complete and executable Python project containing all application code, workflow implementation, memory, evaluation logic, tests and documentation.

### Deliverable 2: Final Lesson Document

A standalone Markdown document containing the approved Introduction to RAG lesson.

### Deliverable 3: Loom Demonstration

A 15–20 minute video showing:
- The complete workflow.
- Lesson generation.
- Evaluator execution.
- A deliberately introduced error.
- Rejection and regeneration.
- Final evaluation.
- Persistent memory.
- System architecture.

The presenter's face must be visible.

## 9. Definition of Success

The project will be considered technically complete when:

1. The application executes successfully.
2. The generator creates a complete RAG lesson.
3. All six evaluation checkpoints execute.
4. The evaluator correctly identifies failures.
5. Any failed checkpoint causes rejection.
6. The generator receives actionable feedback.
7. Regeneration happens automatically.
8. No execution exceeds three generation attempts.
9. Approved lessons are published correctly.
10. Rejected lessons are never incorrectly marked as approved.
11. Execution and rejection history are saved.
12. Memory survives application restarts.
13. Repeated failures create reusable learned rules.
14. Future runs retrieve and use learned rules.
15. Automated tests verify the mandatory functionality.
16. The complete application can be reproduced using the README instructions.

## 10. Primary Engineering Principle

The system must prioritize:

- Technical accuracy over fluent but incorrect content.
- Actual evaluation over superficial scoring.
- Explicit feedback over blind regeneration.
- Deterministic workflow control over unrestricted agent behaviour.
- Persistent and traceable memory over temporary conversation history.
- Verifiable results over untested implementation claims.

The final product should demonstrate how an AI engineering system can autonomously generate, inspect, improve and approve educational content using a controlled and explainable workflow.