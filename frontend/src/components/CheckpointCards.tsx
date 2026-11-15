import { AlertCircle, CheckCircle2, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import type { EvaluationResult } from "../types";
import { useLanguage } from "../language";

const checkpointNames: Record<string, string> = {
  C1: "Accuracy and grounding",
  C2: "Beginner-friendly language",
  C3: "Examples",
  C4: "Clear explanations without unexplained jargon",
  C5: "Key concept coverage",
  C6: "Teaching flow",
};

export function CheckpointCards({
  evaluation,
}: {
  evaluation: EvaluationResult;
}) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <div className="checkpoint-grid">
      {evaluation.checkpoints.map((checkpoint) => {
        const isOpen = expanded === checkpoint.checkpoint_id;
        const failed = checkpoint.status === "FAIL";
        const correction = evaluation.correction_instructions.find((instruction) =>
          instruction.trim().toUpperCase().startsWith(`${checkpoint.checkpoint_id}:`),
        );
        return (
          <article
            className={`checkpoint-card ${failed ? "checkpoint-fail" : "checkpoint-pass"} ${isOpen ? "checkpoint-expanded" : ""}`}
            key={checkpoint.checkpoint_id}
          >
            <button
              className="checkpoint-card-trigger"
              onClick={() => setExpanded(isOpen ? null : checkpoint.checkpoint_id)}
              aria-expanded={isOpen}
            >
              <span className="checkpoint-id">{checkpoint.checkpoint_id}</span>
              <span className="checkpoint-title">{t(checkpointNames[checkpoint.checkpoint_id])}</span>
              <span className={`checkpoint-state ${failed ? "fail" : "pass"}`}>
                {failed ? <AlertCircle size={15} /> : <CheckCircle2 size={15} />}
                {t(checkpoint.status === "PASS" ? "Pass" : "Fail")}
              </span>
              {isOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>
            <p className="checkpoint-reason">{checkpoint.reason}</p>
            {isOpen && (
              <div className="checkpoint-evidence">
                <span className="eyebrow">{t("LESSON EVIDENCE")}</span>
                <blockquote>{checkpoint.evidence}</blockquote>
                {correction && (
                  <>
                    <span className="eyebrow correction-eyebrow">{t("REQUESTED CORRECTION")}</span>
                    <p>{correction}</p>
                  </>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
