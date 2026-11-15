# Loom Demonstration Script (18 minutes)

## Recording setup

- Target duration: **18 minutes** (acceptable range: 15–20 minutes).
- Keep your face visible throughout the recording; use picture-in-picture while sharing the screen.
- Close any window that could display `.env`, credentials, personal notifications, or unrelated files.
- The sample runs below are mocked and make no Gemini API calls. Call them mocked examples on-screen; do not describe them as live model output.
- Do not claim a live Gemini result unless you separately run and verify one manually.

## Run-of-show

| Time | Segment | Suggested screen-sharing actions |
|---|---|---|
| 0:00–1:15 | Introduction and problem | Keep camera prominent. Introduce the NxtWave assessment and explain why generating text alone is insufficient: quality checks, feedback, bounded retries, and persistent learning are required. |
| 1:15–3:15 | Architecture and structure | Show the repository tree and README architecture diagram. Open `app/main.py`, `app/workflow.py`, `app/agents/generator.py`, `app/agents/evaluator.py`, `app/memory/`, and `app/services/output_service.py`. Explain separate responsibilities. State that orchestration is currently a bounded Python workflow, not LangGraph. |
| 3:15–4:30 | Configuration and trusted references | Show `.env.example` only, never `.env`. Open `app/knowledge/source_notes.md` and `app/knowledge/reference_loader.py`. Explain citation IDs and the fixed Introduction to RAG topic. |
| 4:30–6:15 | Lesson shape and learner | Show `app/prompts/generator_prompt.py` and the mocked corrected lesson. Point out the beginner profile, simple English, required sections, Indian college-scholarship example, technical workflow, recap, and citations. Clarify that the example output is mocked, not Gemini-generated. |
| 6:15–8:15 | Six-checkpoint evaluation | Show `app/prompts/evaluator_prompt.py`, `app/agents/evaluator.py`, and `app/schemas.py`. Walk through C1–C6, the evidence/reason requirement, and the application rule that every checkpoint must pass. Show the related evaluator tests. |
| 8:15–11:00 | Deliberate failure and correction | Run `python -m app.demo --scenario corrected`. Show the deliberate false statement, the scripted C1 failure reason and evidence, the C1 correction supplied to generation 2, the corrected statement, and final APPROVED decision. Emphasize that the evaluator response is scripted for reproducibility and does not prove live semantic detection. |
| 11:00–12:45 | Retry limit and rejection | Run `python -m app.demo --scenario rejected`. Show that all three attempts fail C1 and the result remains REJECTED. Open the generated `rejection_log.md` and verify there is `rejected_lesson.md`, not `final_lesson.md`. Explain two retries means three generations total. |
| 12:45–14:45 | SQLite and learned rules | Show `app/memory/database.py`, `app/memory/memory_manager.py`, and `app/memory/learning_engine.py`. Explain the two-distinct-run threshold, why retries in one run count once, rejection provenance, and the checkpoint-specific allowlist. Show the cross-process/reopen and unsafe-rule tests. |
| 14:45–16:15 | Outputs and error handling | Show both folders under `outputs/examples/`, the mock-only banner, evaluation report, attempt history, summary, and learned rules report. Explain unique folders, persisted-data validation, no false approval, and safe failure behavior. |
| 16:15–17:15 | Automated verification | Run or show results for `python -m pytest`, `python -m compileall -q app tests`, and `python -m pip check`. Open `tests/test_demo.py` and a workflow test. Avoid showing `.env` or printing configuration values. |
| 17:15–18:00 | Limitations and close | Summarize honestly: no live Gemini validation or genuine final lesson is included; LangGraph is not implemented; pattern grouping is checkpoint-based; repository and video submission remain user actions. End with the next steps needed for submission. |

## Commands for the recorded demonstrations

```powershell
python -m app.demo --scenario corrected
python -m app.demo --scenario rejected
python -m pytest
python -m compileall -q app tests
python -m pip check
```

The demo outputs are stored in unique folders below `outputs/examples/corrected/` and `outputs/examples/rejected/`. Every Markdown artifact is prefixed with a mock-demonstration notice. Re-running a scenario creates another unique run folder and preserves earlier output folders.

## Presenter checklist

- [ ] Face remains visible for the full recording.
- [ ] Screen is readable and notifications are hidden.
- [ ] `.env` and API keys are never opened or shown.
- [ ] Mocked output is clearly distinguished from live Gemini output.
- [ ] State that the scripted C1 response demonstrates workflow behavior, not live model detection.
- [ ] Show the final rejected outcome has no `final_lesson.md`.
- [ ] Keep the final recording between 15 and 20 minutes.
