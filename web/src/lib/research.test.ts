import { expect, it } from "vitest";
import { warningsBeyondScopeNote } from "./research";

it("drops only the catalog scope warning that the page's scope note already covers", () => {
  expect(
    warningsBeyondScopeNote([
      "Saved-source research catalog only; it does not authorize execution or replay.",
      "An oversized saved result was omitted from this response.",
    ]),
  ).toEqual(["An oversized saved result was omitted from this response."]);
  expect(warningsBeyondScopeNote(["Catalog scope changed wording."])).toEqual([
    "Catalog scope changed wording.",
  ]);
});
