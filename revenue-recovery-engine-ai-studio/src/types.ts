// ─────────────────────────────────────────────────────────────────────────────
// UI FORM TYPES — aligned to exact backend-accepted literals
// Source: api/schemas.py, ml/policy/eligibility.py, ml/llm/contracts.py
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Exact failure_type values accepted by the backend (M1-locked, 7 values).
 * Source: ml/policy/eligibility.py ELIGIBILITY dict keys.
 */
export type FailureType =
  | 'temporary_bank_decline'
  | 'network_timeout'
  | 'card_expired'
  | 'risk_block'
  | 'customer_abandoned'
  | 'subscription_mandate_fail'
  | 'insufficient_funds';

/**
 * Exact customer_segment values accepted by the backend (3 values).
 * Source: api/schemas.py Literal + ml/llm/contracts.py VALID_CUSTOMER_SEGMENTS.
 */
export type CustomerSegment = 'b2c_new' | 'b2c_returning' | 'b2b';

/**
 * Exact communication_channel values accepted by the backend (4 values).
 * Source: api/schemas.py Literal + ml/llm/contracts.py VALID_CHANNELS.
 */
export type CommunicationChannel = 'email' | 'sms' | 'whatsapp' | 'none';

/**
 * All 8 backend action strings that POST /decide can return.
 * Source: ml/llm/contracts.py ACTIVE_RECOVERY_ACTIONS | INACTIVE_ACTIONS.
 * These are lowercase exactly as the backend returns them.
 */
export type RecoveryAction =
  | 'discount'
  | 'retry'
  | 'payment_link'
  | 'reminder'
  | 'wait'
  | 'close'
  | 'escalate'
  | 'no_action_required';

export interface TransactionInput {
  transactionId: string;
  failureType: FailureType;
  amount: number;
  attemptNumber: number;
  riskScore: number; // 0.0 - 1.0
  contactFatigueScore: number; // 0.0 - 1.0
  hoursSinceFailure: number;
  currentDiscountPercent: number; // 0 - 30
  customerSegment: CustomerSegment;
  alreadyRecovered: boolean;
  customerName: string;
  communicationChannel: CommunicationChannel;
  paymentLinkUrl: string;
}

export interface DecisionFactor {
  label: string;
  impact: 'positive' | 'negative' | 'neutral';
  detail: string;
}

export interface DecisionResult {
  action: RecoveryAction;
  /** INR expected net value from backend. Null when backend returns null (rule-only/escalate paths). */
  expectedValue: number | null;
  /** Recovery probability as a 0-100 percentage. Null when backend returns null. */
  recoveryProbability: number | null;
  decisionType: string;
  /** Human-readable escalation status derived from escalation_required boolean. */
  escalation: string;
  terminal: 'No' | 'Yes';
  policyVersion: string;
  traceId: string;
  timestamp: string;
  /** Backend decision_reason string — displayed verbatim, never fabricated. */
  reasoning: string;
  /** Always empty [] when using real backend — no fabricated factors. */
  factors: DecisionFactor[];
  communication: {
    sendable: boolean;
    channel: string | null;
    fallback: string;
    subject: string;
    message: string;
  };
}

export interface AuditRecord {
  id: string;
  traceId: string;
  transactionId: string;
  action: RecoveryAction;
  timestamp: string;
  decisionType: string;
  decisionReason: string;
  expectedValue: number | null;
  recoveryProbability: number | null;
  escalation: string;
  terminal: string;
  /** Not stored in GET /audit/{id} response — always undefined for real backend records. */
  customerSegment?: CustomerSegment | null;
  communicationChannel: CommunicationChannel;
  communicationSnippet: string;
  policyVersion: string;
}

export interface SessionActivityItem {
  id: string;
  timestamp: string;
  title: string;
  detail: string;
  type: 'decision' | 'audit' | 'system' | 'preset';
}

export type ActiveTab = 'decision' | 'audit' | 'system';

// ─────────────────────────────────────────────────────────────────────────────
// BACKEND CONTRACT TYPES
// These interfaces mirror the Pydantic schemas in api/schemas.py exactly.
// They are used only inside src/api/recoveryClient.ts.
// Do NOT use these types in UI components directly.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Valid failure_type values accepted by the real backend.
 * Source: ml/policy/eligibility.py — ELIGIBILITY dict keys (M1-locked).
 * The backend raises HTTP 400 "Unknown failure_type" for any other value.
 */
export type BackendFailureType =
  | 'temporary_bank_decline'
  | 'network_timeout'
  | 'card_expired'
  | 'risk_block'
  | 'customer_abandoned'
  | 'subscription_mandate_fail'
  | 'insufficient_funds';

/**
 * Valid customer_segment values accepted by the real backend.
 * Source: api/schemas.py — Literal["b2c_new", "b2c_returning", "b2b"]
 */
export type BackendCustomerSegment = 'b2c_new' | 'b2c_returning' | 'b2b';

/**
 * Valid communication_channel values accepted by the real backend.
 * Source: api/schemas.py — Literal["email", "sms", "whatsapp", "none"]
 */
export type BackendCommunicationChannel = 'email' | 'sms' | 'whatsapp' | 'none';

/**
 * POST /decide — request body.
 * Source: api/schemas.py — class DecideRequest.
 * model_config = ConfigDict(extra="forbid") → any extra key → HTTP 422.
 * All 10 required fields must be present; 3 optional fields may be omitted.
 */
export interface BackendDecideRequest {
  // Required
  transaction_id: string;
  failure_type: BackendFailureType;
  amount: number;
  attempt_number: number;
  risk_score: number;
  contact_fatigue: number;
  hours_since_failure: number;
  current_discount_percent: number;
  customer_segment: BackendCustomerSegment;
  already_recovered: boolean;
  // Optional — omit (do not send as null) if not provided
  customer_name?: string;
  communication_channel?: BackendCommunicationChannel;
  payment_link_url?: string;
}

/**
 * POST /decide — communication sub-object in response.
 * Source: api/schemas.py — class CommunicationOut.
 */
export interface BackendCommunicationOut {
  sendable: boolean;
  channel: string | null;       // Optional[str] — null when not sendable
  message_body: string | null;  // Optional[str] — null when not sendable
  fallback_used: boolean;
}

/**
 * POST /decide — full response body.
 * Source: api/schemas.py — class DecideResponse.
 * selected_ev and selected_probability are null when the policy did not compute EV
 * (e.g. escalate / rule-only paths).
 */
export interface BackendDecideResponse {
  transaction_id: string;
  trace_id: string | null;          // Optional[str]
  selected_action: string;          // lowercase: 'discount' | 'retry' | 'wait' | 'escalate' | 'payment_link' | 'reminder' | 'close'
  decision_type: string;            // e.g. 'ev_optimization', 'rule_only'
  decision_reason: string;
  escalation_required: boolean;
  terminal: boolean;
  selected_ev: number | null;       // Optional[float] — INR value
  selected_probability: number | null; // Optional[float] — 0.0–1.0 raw probability
  policy_version: string;
  communication: BackendCommunicationOut;
}

/**
 * GET /health — response body.
 * Source: api/schemas.py — class HealthResponse.
 * Only field is "status"; value is "ok" when the service is healthy.
 */
export interface BackendHealthResponse {
  status: string; // "ok" when healthy
}

/**
 * GET /audit/{transaction_id} — single audit record.
 * Source: api/schemas.py — class AuditRecordOut.
 * selected_ev and selected_probability are null on rule-only decision paths.
 * m6_channel is null when communication was not sendable.
 */
export interface BackendAuditRecord {
  trace_id: string;
  timestamp: string;              // ISO-8601 UTC string
  transaction_id: string;
  selected_action: string;        // lowercase action string
  decision_type: string;
  decision_reason: string;
  policy_version: string;
  model_version: string;
  decision_engine_version: string;
  rules_fired: string[];          // list of rule names that fired
  escalation_required: boolean;
  terminal: boolean;
  selected_ev: number | null;
  selected_probability: number | null;
  m6_sendable: boolean;
  m6_channel: string | null;
  m6_fallback_used: boolean;
}

/**
 * GET /audit/{transaction_id} — full response body.
 * Source: api/schemas.py — class AuditLookupResponse.
 * records is an empty list [] if no records exist yet (backend returns HTTP 404,
 * so the client will never see an empty list in a successful response).
 */
export interface BackendAuditLookupResponse {
  transaction_id: string;
  records: BackendAuditRecord[];
}
