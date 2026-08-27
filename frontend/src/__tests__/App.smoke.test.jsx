import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App.jsx";
import { fillDecideForm, jsonResponse } from "./helpers.js";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, init = {}) => {
      const path = String(url);
      const method = init.method || "GET";
      if (path === "/health" && method === "GET") {
        return jsonResponse(200, { status: "ok" });
      }
      if (path === "/decide" && method === "POST") {
        return jsonResponse(200, {
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
        });
      }
      if (path.startsWith("/audit/") && method === "GET") {
        return jsonResponse(200, {
          transaction_id: "txn_m9_test",
          records: [
            {
              trace_id: "trace-1",
              timestamp: "2026-08-01T00:00:00.000Z",
              transaction_id: "txn_m9_test",
              selected_action: "discount",
              decision_type: "ev_optimization",
              decision_reason: "highest_expected_net_value",
              policy_version: "v1.0",
              model_version: "M2_logistic_regression",
              decision_engine_version: "v1.0",
              rules_fired: [],
              escalation_required: false,
              terminal: false,
              selected_ev: 12.5,
              selected_probability: 0.4,
              m6_sendable: true,
              m6_channel: "email",
              m6_fallback_used: false,
            },
          ],
        });
      }
      throw new Error(`Unexpected endpoint: ${method} ${path}`);
    })
  );
});

describe("App smoke integration", () => {
  it("calls only GET /health, POST /decide, and GET /audit/{transaction_id}", async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByTestId("health-indicator").getAttribute("data-state")).toBe(
        "connected"
      )
    );

    fillDecideForm(fireEvent, screen);
    fireEvent.submit(screen.getByTestId("decide-form"));
    await waitFor(() => screen.getByTestId("decide-success"));

    fireEvent.submit(screen.getByTestId("audit-form"));
    await waitFor(() => screen.getByTestId("audit-success"));

    const calls = fetch.mock.calls.map(([url, init]) => ({
      url: String(url),
      method: (init && init.method) || "GET",
    }));

    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) {
      const allowedHealth = call.method === "GET" && call.url === "/health";
      const allowedDecide = call.method === "POST" && call.url === "/decide";
      const allowedAudit = call.method === "GET" && /^\/audit\/[^/]+$/.test(call.url);
      expect(allowedHealth || allowedDecide || allowedAudit).toBe(true);
    }

    expect(calls.some((c) => c.method === "GET" && c.url === "/health")).toBe(true);
    expect(calls.some((c) => c.method === "POST" && c.url === "/decide")).toBe(true);
    expect(calls.some((c) => c.method === "GET" && c.url === "/audit/txn_m9_test")).toBe(
      true
    );
  });
});
