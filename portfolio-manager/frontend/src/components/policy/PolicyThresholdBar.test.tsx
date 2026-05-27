import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PolicyThresholdBar } from "./PolicyThresholdBar";

describe("PolicyThresholdBar", () => {
  it("renders threshold labels and current weight", () => {
    render(
      <PolicyThresholdBar
        policy={{
          target: 0.05,
          warning: 0.08,
          hardBuyBlock: 0.1,
          urgentReview: 0.15,
          extreme: 0.25,
        }}
        currentWeight={0.538}
        symbol="META"
        showLegend
      />,
    );

    expect(screen.getByLabelText(/META cap ladder/i)).toBeTruthy();
    expect(screen.getByText(/53\.8%/)).toBeTruthy();
  });
});
