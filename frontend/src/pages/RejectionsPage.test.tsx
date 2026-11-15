import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { api } from "../api";
import { LanguageProvider } from "../language";
import type { RejectionListItem } from "../types";
import { RejectionsPage } from "./DataPages";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("RejectionsPage", () => {
  it("shows evaluator failures beside checkpoint rejections", async () => {
    vi.spyOn(api, "rejections").mockResolvedValue({
      items: [],
      failures: [
        {
          failure_id: "failure-1",
          run_id: "run-rag-1",
          topic: "Introduction to RAG",
          mode: "rag",
          attempt_number: 1,
          failure_kind: "evaluation",
          failure_stage: "evaluation_validation",
          error_category: "evaluation_validation_error",
          error_type: "WorkflowExecutionError",
          error_description: "The evaluator result was associated with a different run or attempt.",
          recorded_at: "2025-01-01T00:00:00Z",
        },
      ],
    });

    render(
      <MemoryRouter>
        <LanguageProvider>
          <RejectionsPage />
        </LanguageProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Evaluator A1/)).toBeTruthy();
    expect(
      screen.getByText("The evaluator result was associated with a different run or attempt."),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: /View run/i }).getAttribute("href")).toBe("/runs/run-rag-1");
  });

  it("refreshes and renders persisted rejection details and retry results", async () => {
    const record: RejectionListItem = {
      rejection: {
        rejection_id: "rejection-1",
        run_id: "run-1",
        attempt_number: 1,
        retry_attempt_number: 2,
        failed_checkpoints: ["C2"],
        failure_reasons: { C2: "The lesson uses unexplained terminology." },
        evidence: { C2: "The evidence contains the unexplained term." },
        correction_instructions: ["C2: Define the term before using it."],
        correction_applied: "Feedback supplied to generation attempt 2.",
        changes_made: "Changed content in: Introduction.",
        created_at: "2025-01-01T00:00:00Z",
      },
      topic: "Introduction to RAG",
      final_status: "APPROVED",
      feedback_sent: [
        "C2 (Beginner-friendly language) failed.\nFailure reason: The lesson uses unexplained terminology.\nSupporting evidence: The evidence contains the unexplained term.\nRequired corrections:\n- C2: Define the term before using it.",
      ],
      retry_attempt_status: "PASS",
    };
    const rejectionRequest = vi
      .spyOn(api, "rejections")
      .mockResolvedValueOnce({ items: [], failures: [] })
      .mockResolvedValueOnce({ items: [record], failures: [] });

    render(
      <MemoryRouter>
        <LanguageProvider>
          <RejectionsPage />
        </LanguageProvider>
      </MemoryRouter>,
    );

    await waitFor(
      () => expect(rejectionRequest).toHaveBeenCalledTimes(2),
      { timeout: 4000 },
    );
    expect(screen.getByRole("button", { name: /Refresh rejection log/i })).toBeTruthy();
    expect(screen.getByText("C2", { exact: true })).toBeTruthy();
    expect(screen.getByText("Retry A2: PASS")).toBeTruthy();
    expect(screen.getByText(/The lesson uses unexplained terminology\./)).toBeTruthy();
    fireEvent.click(screen.getByText("C2", { selector: "strong" }));
    expect(
      await screen.findByText("The lesson uses unexplained terminology."),
    ).toBeTruthy();
    expect(
      screen.getByText("The evidence contains the unexplained term."),
    ).toBeTruthy();
    expect(
      screen.getByText(/Failure reason: The lesson uses unexplained terminology/),
    ).toBeTruthy();
    expect(screen.getByText("Changed content in: Introduction.")).toBeTruthy();
  }, 8000);
});
