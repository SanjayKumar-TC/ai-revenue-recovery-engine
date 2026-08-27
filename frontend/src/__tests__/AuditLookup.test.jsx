import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import AuditLookup from "../components/AuditLookup.jsx";
import AuditResult from "../components/AuditResult.jsx";
import { jsonResponse } from "./helpers.js";

function AuditHarness() {
  const [lookup, setLookup] = useState(null);
  return (
    <>
      <AuditLookup onLookup={setLookup} />
      <AuditResult lookup={lookup} />
    </>
  );
}

function olderRecord(overrides = {}) {
  return {
    trace_id: "trace-old",
    timestamp: "2026-01-01T00:00:00.000Z",
    transaction_id: "txn_audit",
    selected_action: "wait",
    decision_type: "ev_optimization",
    decision_reason: "highest_expected_net_value",
    policy_version: "v1.0",
    model_version: "M2_logistic_regression",
    decision_engine_version: "v1.0",
    rules_fired: [],
    escalation_required: false,
    terminal: false,
    selected_ev: 1.0,
    selected_probability: 0.1,
    m6_sendable: false,
    m6_channel: null,
    m6_fallback_used: false,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("AuditLookup", () => {
  it("calls GET /audit/{transaction_id}", async () => {
    fetch.mockResolvedValue(
      jsonResponse(200, { transaction_id: "txn_audit", records: [olderRecord()] })
    );
    render(<AuditHarness />);
    fireEvent.change(screen.getByLabelText(/transaction id/i), {
      target: { value: "txn_audit" },
    });
    fireEvent.submit(screen.getByTestId("audit-form"));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/audit/txn_audit");
    expect(init.method).toBe("GET");
  });

  it("renders a loading state while the request is in flight", async () => {
    let release;
    fetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    render(<AuditHarness />);
    fireEvent.change(screen.getByLabelText(/transaction id/i), {
      target: { value: "txn_audit" },
    });
    fireEvent.submit(screen.getByTestId("audit-form"));
    expect(screen.getByTestId("audit-loading")).toBeTruthy();
    release(
      await jsonResponse(200, {
        transaction_id: "txn_audit",
        records: [olderRecord()],
      })
    );
    await waitFor(() => screen.getByTestId("audit-success"));
  });

  it("renders a successful response", async () => {
    fetch.mockResolvedValue(
      jsonResponse(200, {
        transaction_id: "txn_audit",
        records: [olderRecord({ selected_action: "retry" })],
      })
    );
    render(<AuditHarness />);
    fireEvent.change(screen.getByLabelText(/transaction id/i), {
      target: { value: "txn_audit" },
    });
    fireEvent.submit(screen.getByTestId("audit-form"));
    await waitFor(() => screen.getByTestId("audit-success"));
    expect(screen.getByText("retry")).toBeTruthy();
    expect(screen.getByText("trace-old")).toBeTruthy();
  });

  it("renders multiple records newest-first", async () => {
    fetch.mockResolvedValue(
      jsonResponse(200, {
        transaction_id: "txn_audit",
        records: [
          olderRecord({
            trace_id: "trace-old",
            timestamp: "2026-01-01T00:00:00.000Z",
            selected_action: "wait",
          }),
          olderRecord({
            trace_id: "trace-new",
            timestamp: "2026-08-01T00:00:00.000Z",
            selected_action: "discount",
          }),
        ],
      })
    );
    render(<AuditHarness />);
    fireEvent.change(screen.getByLabelText(/transaction id/i), {
      target: { value: "txn_audit" },
    });
    fireEvent.submit(screen.getByTestId("audit-form"));
    await waitFor(() => screen.getByTestId("audit-success"));
    const records = screen.getAllByTestId("audit-record");
    expect(records[0].textContent).toContain("trace-new");
    expect(records[1].textContent).toContain("trace-old");
  });

  it("renders 404 as a normal empty state, not an error", async () => {
    fetch.mockResolvedValue(jsonResponse(404, { detail: "Not found" }));
    render(<AuditHarness />);
    fireEvent.change(screen.getByLabelText(/transaction id/i), {
      target: { value: "missing_txn" },
    });
    fireEvent.submit(screen.getByTestId("audit-form"));
    await waitFor(() => screen.getByTestId("audit-404"));
    expect(screen.getByText(/No audit records found/)).toBeTruthy();
    expect(screen.queryByTestId("audit-500")).toBeNull();
    expect(screen.queryByText(/Server error/)).toBeNull();
  });

  it("renders a distinct 500 state", async () => {
    fetch.mockResolvedValue(jsonResponse(500, { detail: "Internal server error" }));
    render(<AuditHarness />);
    fireEvent.change(screen.getByLabelText(/transaction id/i), {
      target: { value: "txn_audit" },
    });
    fireEvent.submit(screen.getByTestId("audit-form"));
    await waitFor(() => screen.getByTestId("audit-500"));
    expect(screen.getByText(/Audit lookup could not be completed/)).toBeTruthy();
    expect(screen.queryByText(/Internal server error/)).toBeNull();
  });
});
