import { describe, expect, it } from "vitest";
import { displayModeClass } from "./displayModes";

describe("displayModeClass", () => {
  it("returns css class for each mode", () => {
    expect(displayModeClass("command")).toBe("display-mode-command");
    expect(displayModeClass("research")).toBe("display-mode-research");
    expect(displayModeClass("focus")).toBe("display-mode-focus");
    expect(displayModeClass("presentation")).toBe("display-mode-presentation");
  });
});
