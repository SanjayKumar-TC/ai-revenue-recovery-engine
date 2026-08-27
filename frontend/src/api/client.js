/**
 * Thin fetch wrappers for the three M8 endpoints. No other HTTP calls.
 */

async function readBody(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function getHealth() {
  const response = await fetch("/health", { method: "GET" });
  const data = await readBody(response);
  return { ok: response.ok, status: response.status, data };
}

export async function postDecide(payload) {
  const response = await fetch("/decide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readBody(response);
  return { ok: response.ok, status: response.status, data };
}

export async function getAudit(transactionId) {
  const encoded = encodeURIComponent(transactionId);
  const response = await fetch(`/audit/${encoded}`, { method: "GET" });
  const data = await readBody(response);
  return { ok: response.ok, status: response.status, data };
}
