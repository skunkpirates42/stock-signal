import { describe, expect, it } from "vitest";
import { phaseLabel } from "@/lib/jobs";

describe("phaseLabel", () => {
  it("names the current phase while the worker is still on the job", () => {
    expect(phaseLabel("running")).toBe("Phase");
    expect(phaseLabel("cancel_requested")).toBe("Phase");
  });

  it("names the last phase once the job has ended, so completed never reads as still verifying", () => {
    expect(phaseLabel("completed")).toBe("Last phase");
    expect(phaseLabel("failed")).toBe("Last phase");
    expect(phaseLabel("cancelled")).toBe("Last phase");
  });
});
