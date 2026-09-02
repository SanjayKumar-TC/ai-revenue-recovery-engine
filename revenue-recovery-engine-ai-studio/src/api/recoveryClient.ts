/**
 * recoveryClient.ts — AI Revenue Recovery Engine
 * ================================================
 * API client for the real M8 FastAPI backend.
 *
 * Responsibilities:
 *   • Serialize camelCase TransactionInput → snake_case BackendDecideRequest
 *   • POST /decide and normalize BackendDecideResponse → DecisionResult
 *   • GET /audit/{transactionId} and normalize BackendAuditRecord[] → AuditRecord[]
 *   • GET /health and return raw backend health status
 *
 * Rules (hard):
 *   • No mock calculations, no fabricated values, no fallback decisions.
 *   • No UI rendering. No React imports. No local EV/probability computation.
 *   • No synthetic audit records.
 *   • CamelCase ↔ snake_case conversion happens only in this file.
 *   • Only the 10 required + 3 optional backend fields are sent in POST /decide.
 *   • The backend uses extra="forbid"; any unrecognised field causes HTTP 422.
 *   • All 8 backend action strings are passed through verbatim — no collapsing.
 *
 * Backend source of truth: api/schemas.py
 * Valid failure_type values: ml/policy/eligibility.py (ELIGIBILITY dict keys, M1-locked)
 *
 * NOTE: FailureType, CustomerSegment, and CommunicationChannel in types.ts now
 * directly mirror the backend literals. No semantic mapping is required for those
 * fields — the UI form exposes exactly what the backend accepts.
 */

import type {
  AuditRecord,
  BackendAuditLookupResponse,
  BackendAuditRecord,
  BackendCommunicationChannel,
  BackendCustomerSegment,
  BackendDecideRequest,
  BackendDecideResponse,
  BackendFailureType,
  BackendHealthResponse,
  CommunicationChannel,
  CustomerSegment,
  DecisionResult,
  FailureType,
  RecoveryAction,
  TransactionInput,
} from '../types';

// ─────────────────────────────────────────────────────────────────────────────
// SERIALIZERS  (camelCase UI state → snake_case backend request)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * FailureType is now directly identical to BackendFailureType.
 * This function exists as an explicit boundary and type assertion only.
 * No semantic mapping is performed.
 */
function serializeFailureType(ft: FailureType): BackendFailureType {
  return ft as BackendFailureType;
}

/**
 * CustomerSegment is now directly identical to BackendCustomerSegment.
 * This function exists as an explicit boundary and type assertion only.
 */
function serializeCustomerSegment(seg: CustomerSegment): BackendCustomerSegment {
  return seg as BackendCustomerSegment;
}

/**
 * CommunicationChannel is now directly identical to BackendCommunicationChannel.
 * This function exists as an explicit boundary and type assertion only.
 */
function serializeCommunicationChannel(ch: CommunicationChannel): BackendCommunicationChannel {
  return ch as BackendCommunicationChannel;
}

/**
 * Produce the strict snake_case request body for POST /decide.
 * Only the 10 required + 3 optional backend fields are included.
 * Optional fields are omitted entirely (not sent as null) when empty.
 * Backend uses extra="forbid" — no extra keys allowed.
 */
export function serializeDecideRequest(input: TransactionInput): BackendDecideRequest {
  const req: BackendDecideRequest = {
    transaction_id:           input.transactionId.trim(),
    failure_type:             serializeFailureType(input.failureType),
    amount:                   Number(input.amount),
    attempt_number:           Math.round(Number(input.attemptNumber)),
    risk_score:               Number(input.riskScore),
    contact_fatigue:          Number(input.contactFatigueScore),
    hours_since_failure:      Number(input.hoursSinceFailure),
    current_discount_percent: Number(input.currentDiscountPercent),
    customer_segment:         serializeCustomerSegment(input.customerSegment),
    already_recovered:        Boolean(input.alreadyRecovered),
  };

  // Optional fields — only include if non-empty
  const trimmedName = input.customerName?.trim();
  if (trimmedName) {
    req.customer_name = trimmedName;
  }

  // Always send the channel if present; 'none' is a valid backend value
  if (input.communicationChannel) {
    req.communication_channel = serializeCommunicationChannel(input.communicationChannel);
  }

  const trimmedUrl = input.paymentLinkUrl?.trim();
  if (trimmedUrl) {
    req.payment_link_url = trimmedUrl;
  }

  return req;
}

// ─────────────────────────────────────────────────────────────────────────────
// NORMALIZERS  (snake_case backend response → camelCase UI types)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Pass through the backend selected_action string verbatim as RecoveryAction.
 * The backend can return: 'discount', 'retry', 'wait', 'escalate',
 *                         'payment_link', 'reminder', 'close', 'no_action_required'.
 * All 8 values are represented in the RecoveryAction type in types.ts.
 * NO collapsing is performed:
 *   payment_link ≠ retry
 *   reminder ≠ retry
 *   close ≠ wait
 *
 * Throws on any action string not in the known set — never silently fabricates
 * an alternative decision. The caller (App.tsx handleRunDecision) catches this
 * and surfaces it as an apiError state exactly like an HTTP error.
 */
function normalizeAction(action: string): RecoveryAction {
  const known: RecoveryAction[] = [
    'discount', 'retry', 'payment_link', 'reminder',
    'wait', 'close', 'escalate', 'no_action_required',
  ];
  const lower = action.toLowerCase() as RecoveryAction;
  if (known.includes(lower)) return lower;
  throw new Error(`Unknown backend action: "${action}". The backend returned an action outside the known domain. Do not fabricate a decision.`);
}

/**
 * Normalize a BackendDecideResponse → DecisionResult (UI type).
 * Fields with no backend equivalent:
 *   - factors         → always []  (never fabricated)
 *   - communication.subject → synthesized if channel is email; blank otherwise
 *   - communication.fallback → derived from fallback_used boolean
 * Probability: backend returns 0.0–1.0 raw; UI expects 0–100 percentage.
 * EV/probability remain null when backend returns null — never substituted with zero.
 */
export function normalizeDecideResponse(resp: BackendDecideResponse): DecisionResult {
  const channel = resp.communication.channel;
  const fallbackUsed = resp.communication.fallback_used;

  // Synthesize email subject only — no invented business logic
  const subject =
    channel === 'email' && resp.communication.sendable
      ? `Action Required: Transaction ${resp.transaction_id}`
      : '';

  return {
    action:              normalizeAction(resp.selected_action),
    expectedValue:       resp.selected_ev !== null ? resp.selected_ev : null,
    recoveryProbability: resp.selected_probability !== null
                           ? Number((resp.selected_probability * 100).toFixed(2))
                           : null,
    decisionType:        resp.decision_type,
    escalation:          resp.escalation_required ? 'Required' : 'Not Required',
    terminal:            resp.terminal ? 'Yes' : 'No',
    policyVersion:       resp.policy_version,
    traceId:             resp.trace_id ?? '',
    timestamp:           new Date().toLocaleTimeString('en-US', {
                           hour12: false,
                           hour:   '2-digit',
                           minute: '2-digit',
                           second: '2-digit',
                         }),
    reasoning:           resp.decision_reason,
    factors:             [],   // No backend equivalent — never fabricated
    communication: {
      sendable: resp.communication.sendable,
      channel,
      fallback: fallbackUsed ? 'Fallback Used' : 'Not Used',
      subject,
      message:  resp.communication.message_body ?? '',
    },
  };
}

/**
 * Normalize a single BackendAuditRecord → AuditRecord (UI type).
 * Fields with no backend equivalent:
 *   - customerSegment      → placeholder 'b2c_new' (not stored in audit DB)
 *   - communicationChannel → derived from m6_channel; defaults to 'none' if null
 *   - communicationSnippet → truncated decision_reason (safe derivation)
 * Probability: backend 0.0–1.0 → UI percentage (×100). Null preserved as null.
 */
export function normalizeAuditRecord(raw: BackendAuditRecord): AuditRecord {
  // Derive a valid CommunicationChannel from the nullable m6_channel string
  const channelRaw = raw.m6_channel?.toLowerCase();
  const commChannel: CommunicationChannel =
    channelRaw === 'email' ? 'email' :
    channelRaw === 'sms'   ? 'sms'   :
    channelRaw === 'whatsapp' ? 'whatsapp' : 'none';

  return {
    id:                  raw.trace_id,
    traceId:             raw.trace_id,
    transactionId:       raw.transaction_id,
    action:              normalizeAction(raw.selected_action),
    timestamp:           raw.timestamp,
    decisionType:        raw.decision_type,
    decisionReason:      raw.decision_reason,
    expectedValue:       raw.selected_ev !== null ? raw.selected_ev : null,
    recoveryProbability: raw.selected_probability !== null
                           ? Number((raw.selected_probability * 100).toFixed(2))
                           : null,
    escalation:          raw.escalation_required ? 'Required' : 'Not Required',
    terminal:            raw.terminal ? 'Yes' : 'No',
    // customerSegment is NOT stored in the audit DB — omitted, never fabricated
    communicationChannel: commChannel,
    // communicationSnippet derived only from the real backend decision_reason field
    communicationSnippet: raw.decision_reason.length > 95
                            ? raw.decision_reason.slice(0, 95) + '…'
                            : raw.decision_reason,
    policyVersion:       raw.policy_version,
  };
}

/**
 * Normalize a full BackendAuditLookupResponse → AuditRecord[].
 */
export function normalizeAuditResponse(resp: BackendAuditLookupResponse): AuditRecord[] {
  return resp.records.map(normalizeAuditRecord);
}

// ─────────────────────────────────────────────────────────────────────────────
// ERROR TYPES
// ─────────────────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly endpoint: string,
  ) {
    super(`API ${status} on ${endpoint}: ${detail}`);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(res: Response, endpoint: string): Promise<T> {
  if (res.ok) {
    return res.json() as Promise<T>;
  }
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    detail = body?.detail ?? detail;
  } catch {
    // Body not parseable — keep the status-based detail
  }
  throw new ApiError(res.status, detail, endpoint);
}

// ─────────────────────────────────────────────────────────────────────────────
// PUBLIC API FUNCTIONS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * GET /health
 * Returns { ok: boolean, status: string } where ok === (status === "ok").
 * Does NOT fabricate uptime, latency, or subsystem statistics.
 */
export async function checkHealth(): Promise<{ ok: boolean; status: string }> {
  const res = await fetch('/health', {
    method:  'GET',
    headers: { Accept: 'application/json' },
  });
  const data = await handleResponse<BackendHealthResponse>(res, 'GET /health');
  return {
    ok:     data.status === 'ok',
    status: data.status,
  };
}

/**
 * POST /decide
 * Serializes TransactionInput → BackendDecideRequest, submits to the real backend,
 * then normalizes BackendDecideResponse → DecisionResult for the UI.
 *
 * Throws ApiError on any HTTP error (400 Unknown failure_type, 422 Validation, 500).
 */
export async function requestDecision(input: TransactionInput): Promise<DecisionResult> {
  const body = serializeDecideRequest(input);
  const res = await fetch('/decide', {
    method:  'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept:         'application/json',
    },
    body: JSON.stringify(body),
  });
  const data = await handleResponse<BackendDecideResponse>(res, 'POST /decide');
  return normalizeDecideResponse(data);
}

/**
 * GET /audit/{transactionId}
 * Fetches real audit records from the SQLite append-only ledger.
 * Returns AuditRecord[] normalized for the UI.
 *
 * Throws ApiError on HTTP 404 (no records for transaction) or 500.
 * Does NOT create synthetic records.
 */
export async function fetchAudit(transactionId: string): Promise<AuditRecord[]> {
  const endpoint = `/audit/${encodeURIComponent(transactionId.trim())}`;
  const res = await fetch(endpoint, {
    method:  'GET',
    headers: { Accept: 'application/json' },
  });
  const data = await handleResponse<BackendAuditLookupResponse>(res, `GET ${endpoint}`);
  return normalizeAuditResponse(data);
}
