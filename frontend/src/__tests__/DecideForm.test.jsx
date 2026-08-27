import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import DecideForm from "../components/DecideForm.jsx";
import DecisionResult from "../components/DecisionResult.jsx";
import {
  ALLOWED_DECIDE_INPUT_NAMES,
  FORBIDDEN_SETTABLE_NAMES,
  controlNames,
  fillDecideForm,
  jsonResponse,
} from "./helpers.js";

function DecideHarness() {
  const [result, setResult] = useState(null);
  return (
    <>
      <DecideForm onOutcome={setResult} onSuccess={() => {}} />
      <DecisionResult result={result} />
    </>
  );
}

const SUCCESS_BODY = {
  transaction_id: "txn_m9_test",
  trace_id: "trace-1",
  selected_action: "discount",
  decision_type: "ev_optimization",
  decision_reason: "highest_expected_net_value",
  escalation_required: false,
  terminal: false,
  selected_ev: 12.5,
  selected_probability: 0.4,
  policy_version: "v1.0",
  communication: {
    sendable: true,
    channel: "email",
    message_body: "Please complete your payment.",
    fallback_used: false,
  },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("DecideForm", () => {
  it("collects exactly the allowed POST /decide fields and no forbidden fields", () => {
    render(<DecideHarness />);
    const form = screen.getByTestId("decide-form");
    const names = controlNames(form).sort();
    expect(names).toEqual([...ALLOWED_DECIDE_INPUT_NAMES].sort());
    for (const forbidden of FORBIDDEN_SETTABLE_NAMES) {
      expect(names).not.toContain(forbidden);
    }
  });

  it("submits POST /decide with the locked field names", async () => {
    fetch.mockResolvedValue(jsonResponse(200, SUCCESS_BODY));
    render(<DecideHarness />);
    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/decide");
    expect(init.method).toBe("POST");
    const payload = JSON.parse(init.body);
    expect(Object.keys(payload).sort()).toEqual(
      [...ALLOWED_DECIDE_INPUT_NAMES].sort()
    );
    expect(payload.transaction_id).toBe("txn_m9_test");
    expect(payload.failure_type).toBe("temporary_bank_decline");
    expect(payload.customer_segment).toBe("b2c_new");
    expect(payload.already_recovered).toBe(false);
    expect(payload).not.toHaveProperty("action");
    expect(payload).not.toHaveProperty("selected_action");
    expect(payload).not.toHaveProperty("payment_method");
  });

  it("renders a loading state while the request is in flight", async () => {
    let release;
    fetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    render(<DecideHarness />);
    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));
    expect(screen.getByTestId("decide-loading")).toBeTruthy();
    expect(screen.getByText(/Requesting decision from M8/)).toBeTruthy();
    release(await jsonResponse(200, SUCCESS_BODY));
    await waitFor(() => screen.getByTestId("decide-success"));
  });

  it("renders the successful 200 decision and communication fields", async () => {
    fetch.mockResolvedValue(jsonResponse(200, SUCCESS_BODY));
    render(<DecideHarness />);
    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));
    await waitFor(() => screen.getByTestId("decide-success"));
    expect(screen.getByText("txn_m9_test")).toBeTruthy();
    expect(screen.getByText("discount")).toBeTruthy();
    expect(screen.getByText("Please complete your payment.")).toBeTruthy();
    expect(screen.getByText("ev_optimization")).toBeTruthy();
  });

  it("renders a distinct 422 state", async () => {
    fetch.mockResolvedValue(jsonResponse(422, { detail: "validation" }));
    render(<DecideHarness />);
    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));
    await waitFor(() => screen.getByTestId("decide-422"));
    expect(screen.getByText(/Malformed request \(422\)/)).toBeTruthy();
    expect(screen.queryByTestId("decide-400")).toBeNull();
    expect(screen.queryByTestId("decide-500")).toBeNull();
  });

  it("renders a distinct 400 state", async () => {
    fetch.mockResolvedValue(jsonResponse(400, { detail: "Unknown failure_type" }));
    render(<DecideHarness />);
    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));
    await waitFor(() => screen.getByTestId("decide-400"));
    expect(screen.getByText(/Unknown failure_type \(400\)/)).toBeTruthy();
    expect(screen.queryByTestId("decide-422")).toBeNull();
  });

  it("renders a distinct 500 state", async () => {
    fetch.mockResolvedValue(jsonResponse(500, { detail: "Internal server error" }));
    render(<DecideHarness />);
    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));
    await waitFor(() => screen.getByTestId("decide-500"));
    expect(screen.getByText(/Server error/)).toBeTruthy();
    expect(screen.queryByText(/Internal server error/)).toBeNull();
  });

  it("renders the 500/network-error state when fetch rejects", async () => {
    fetch.mockRejectedValue(new Error("network down"));
    render(<DecideHarness />);
    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));
    await waitFor(() => screen.getByTestId("decide-500"));
  });
});
