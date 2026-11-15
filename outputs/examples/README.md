# Mocked Example Outputs

These are reproducible, deterministic demonstrations of the application workflow. They use scripted generator and evaluator responses and are **not genuine Gemini-generated lessons**.

- [Latest corrected run](corrected/README.md): attempt 1 fails C1, targeted feedback is supplied, attempt 2 passes all six scripted checkpoints.
- [Latest rejected run](rejected/README.md): C1 fails on all three generations; the final output is REJECTED and has no `final_lesson.md`.

Run either scenario again with `python -m app.demo --scenario corrected` or `python -m app.demo --scenario rejected`. Each run creates a new output folder and preserves prior demonstration folders.

Earlier run folders are retained to demonstrate non-overwriting behavior. Use the latest corrected and rejected folders linked above as the reviewed examples.
