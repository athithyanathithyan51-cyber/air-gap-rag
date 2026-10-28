import { describe, expect, it } from "vitest";
import { citedSentences, findEvidence } from "../src/evidence";

const PASSAGE =
  "5.3.1 Introduction. A recurrence relation defines a sequence once initial terms are given. " +
  "Each further term is a function of the preceding terms. Linear recurrences use constant coefficients.";

describe("citedSentences", () => {
  it("keeps only sentences that cite the label and strips the markers", () => {
    const answer = "A recurrence relation defines a sequence [S1]. Unrelated remark [S2]. Terms depend on earlier terms [S1].";
    expect(citedSentences(answer, "S1")).toBe("A recurrence relation defines a sequence. Terms depend on earlier terms.");
  });

  it("keeps a citation that follows the full stop with its sentence", () => {
    expect(citedSentences("Every student must attend classes. [S1]", "S1")).toBe("Every student must attend classes.");
  });

  it("returns an empty string when nothing cites the label", () => {
    expect(citedSentences("No citations here.", "S1")).toBe("");
  });
});

describe("findEvidence", () => {
  it("points at the passage sentence that matches the cited answer", () => {
    const hit = findEvidence(PASSAGE, "A recurrence relation defines a sequence once initial terms are given.");
    expect(hit).not.toBeNull();
    expect(PASSAGE.slice(hit!.start, hit!.end)).toBe(
      "A recurrence relation defines a sequence once initial terms are given.",
    );
    expect(hit!.score).toBeGreaterThanOrEqual(0.5);
  });

  it("returns null when no passage sentence is close enough", () => {
    expect(findEvidence(PASSAGE, "Photosynthesis converts sunlight into chemical energy.")).toBeNull();
  });

  it("returns null for an empty cited answer", () => {
    expect(findEvidence(PASSAGE, "")).toBeNull();
  });
});
