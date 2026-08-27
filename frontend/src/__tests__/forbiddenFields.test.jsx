import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { FORBIDDEN_SETTABLE_NAMES, controlNames, jsonResponse } from "./helpers.js";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => jsonResponse(200, { status: "ok" }))
  );
});

describe("Forbidden-field safety", () => {
  it("exposes no user-settable inputs for forbidden fields", () => {
    render(<App />);
    const names = controlNames(document.body);
    for (const forbidden of FORBIDDEN_SETTABLE_NAMES) {
      expect(names).not.toContain(forbidden);
    }
    expect(screen.queryByRole("textbox", { name: /^action$/i })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /selected_action/i })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /rules_fired/i })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /latent_score/i })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /true_prob_HIDDEN/i })).toBeNull();
    expect(screen.queryByLabelText(/^EV$/i)).toBeNull();
    expect(screen.queryByLabelText(/^probability$/i)).toBeNull();
    expect(screen.queryByLabelText(/allowed_actions/i)).toBeNull();
    expect(screen.queryByLabelText(/blocked_actions/i)).toBeNull();
    expect(screen.queryByLabelText(/policy_version/i)).toBeNull();
    expect(screen.queryByLabelText(/model_version/i)).toBeNull();
    expect(screen.queryByLabelText(/decision_engine_version/i)).toBeNull();
  });
});
