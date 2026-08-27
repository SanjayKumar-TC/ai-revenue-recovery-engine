import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HealthIndicator from "../components/HealthIndicator.jsx";
import { jsonResponse } from "./helpers.js";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("HealthIndicator", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("calls GET /health on mount", async () => {
    fetch.mockResolvedValue(jsonResponse(200, { status: "ok" }));
    render(<HealthIndicator />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/health");
    expect(init.method).toBe("GET");
  });

  it("renders the checking state before the request settles", () => {
    fetch.mockImplementation(() => new Promise(() => {}));
    render(<HealthIndicator />);
    expect(screen.getByTestId("health-indicator").getAttribute("data-state")).toBe(
      "checking"
    );
    expect(screen.getByText(/Checking connection/)).toBeTruthy();
  });

  it("renders the connected state when /health succeeds", async () => {
    fetch.mockResolvedValue(jsonResponse(200, { status: "ok" }));
    render(<HealthIndicator />);
    await waitFor(() =>
      expect(screen.getByTestId("health-indicator").getAttribute("data-state")).toBe(
        "connected"
      )
    );
    expect(screen.getByText(/Connected to M8/)).toBeTruthy();
  });

  it("renders the unreachable state when /health fails", async () => {
    fetch.mockRejectedValue(new Error("offline"));
    render(<HealthIndicator />);
    await waitFor(() =>
      expect(screen.getByTestId("health-indicator").getAttribute("data-state")).toBe(
        "unreachable"
      )
    );
    expect(screen.getByText(/M8 unreachable/)).toBeTruthy();
  });
});
