import { AuditRecord, SessionActivityItem, TransactionInput } from '../types';

export const DEFAULT_TRANSACTION: TransactionInput = {
  transactionId: 'txn_7F3K92',
  failureType: 'temporary_bank_decline',
  amount: 2000,
  attemptNumber: 1,
  riskScore: 0.15,
  contactFatigueScore: 0.10,
  hoursSinceFailure: 6,
  currentDiscountPercent: 10,
  customerSegment: 'b2c_new',
  alreadyRecovered: false,
  customerName: 'Aarav Patel',
  communicationChannel: 'email',
  paymentLinkUrl: 'https://pay.engine.io/rec/7F3K92',
};

export const PRESET_TRANSACTIONS: { label: string; desc: string; data: TransactionInput }[] = [
  {
    label: 'Standard Demo (Bank Decline)',
    desc: '₹2,000 · Temp Bank Decline · 6h window · b2c_new',
    data: DEFAULT_TRANSACTION,
  },
  {
    label: 'B2B (Card Expired)',
    desc: '₹18,500 · Card Expired · B2B · Payment link recovery path',
    data: {
      transactionId: 'txn_9E4M11',
      failureType: 'card_expired',
      amount: 18500,
      attemptNumber: 2,
      riskScore: 0.08,
      contactFatigueScore: 0.15,
      hoursSinceFailure: 18,
      currentDiscountPercent: 0,
      customerSegment: 'b2b',
      alreadyRecovered: false,
      customerName: 'Nexus Cloud Systems Ltd',
      communicationChannel: 'email',
      paymentLinkUrl: 'https://pay.engine.io/rec/9E4M11',
    },
  },
  {
    label: 'Risk Block (High-Risk Escalation)',
    desc: '₹54,000 · Risk Block · Risk 0.82 · Route to Manual Compliance',
    data: {
      transactionId: 'txn_3B8Z44',
      failureType: 'risk_block',
      amount: 54000,
      attemptNumber: 3,
      riskScore: 0.82,
      contactFatigueScore: 0.65,
      hoursSinceFailure: 36,
      currentDiscountPercent: 0,
      customerSegment: 'b2c_new',
      alreadyRecovered: false,
      customerName: 'Vikram Mehta',
      communicationChannel: 'sms',
      paymentLinkUrl: 'https://pay.engine.io/rec/3B8Z44',
    },
  },
  {
    label: 'Network Timeout (Cooldown)',
    desc: '₹4,800 · Network Timeout · 1h ago · Low risk, low fatigue',
    data: {
      transactionId: 'txn_5H2Q78',
      failureType: 'network_timeout',
      amount: 4800,
      attemptNumber: 1,
      riskScore: 0.04,
      contactFatigueScore: 0.02,
      hoursSinceFailure: 1,
      currentDiscountPercent: 0,
      customerSegment: 'b2c_returning',
      alreadyRecovered: false,
      customerName: 'Ananya Sharma',
      communicationChannel: 'whatsapp',
      paymentLinkUrl: 'https://pay.engine.io/rec/5H2Q78',
    },
  },
  {
    label: 'Insufficient Funds',
    desc: '₹1,500 · Insufficient Funds · 12h ago · Low fatigue',
    data: {
      transactionId: 'txn_8K1L90',
      failureType: 'insufficient_funds',
      amount: 1500,
      attemptNumber: 1,
      riskScore: 0.22,
      contactFatigueScore: 0.18,
      hoursSinceFailure: 12,
      currentDiscountPercent: 5,
      customerSegment: 'b2c_returning',
      alreadyRecovered: false,
      customerName: 'Rohan Gupta',
      communicationChannel: 'sms',
      paymentLinkUrl: 'https://pay.engine.io/rec/8K1L90',
    },
  },
];

// Empty — no fabricated audit records.
// Audit trail is populated only from real GET /audit/{transaction_id} responses.
export const INITIAL_AUDIT_RECORDS: AuditRecord[] = [];

// Empty — no fabricated session activity.
// Session activity is populated only from real backend interactions.
export const INITIAL_SESSION_ACTIVITY: SessionActivityItem[] = [];
