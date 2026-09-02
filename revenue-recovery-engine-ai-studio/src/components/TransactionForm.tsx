import React from 'react';
import {
  AlertCircle,
  Clock,
  CreditCard,
  Flame,
  HelpCircle,
  Link,
  Mail,
  Percent,
  RefreshCw,
  Shield,
  Sparkles,
  User,
  Zap,
} from 'lucide-react';
import {
  CommunicationChannel,
  CustomerSegment,
  FailureType,
  TransactionInput,
} from '../types';

interface TransactionFormProps {
  input: TransactionInput;
  onChange: (updates: Partial<TransactionInput>) => void;
  onSubmit: () => void;
  isLoading: boolean;
  onGenerateRandomId: () => void;
}

export const TransactionForm: React.FC<TransactionFormProps> = ({
  input,
  onChange,
  onSubmit,
  isLoading,
  onGenerateRandomId,
}) => {
  const failureTypeOptions: { value: FailureType; label: string }[] = [
    { value: 'temporary_bank_decline', label: 'Temporary Bank Decline' },
    { value: 'network_timeout',        label: 'Network Timeout' },
    { value: 'card_expired',           label: 'Card Expired' },
    { value: 'risk_block',             label: 'Risk Block (Fraud / Compliance)' },
    { value: 'customer_abandoned',     label: 'Customer Abandoned' },
    { value: 'subscription_mandate_fail', label: 'Subscription Mandate Failure' },
    { value: 'insufficient_funds',     label: 'Insufficient Funds' },
  ];

  const customerSegmentOptions: { value: CustomerSegment; label: string }[] = [
    { value: 'b2c_new',       label: 'B2C New' },
    { value: 'b2c_returning', label: 'B2C Returning' },
    { value: 'b2b',           label: 'B2B' },
  ];

  const channelOptions: { value: CommunicationChannel; label: string }[] = [
    { value: 'email',     label: 'Email' },
    { value: 'sms',       label: 'SMS' },
    { value: 'whatsapp',  label: 'WhatsApp' },
    { value: 'none',      label: 'None / No Communication' },
  ];

  // Risk meter styling
  const riskPercent = Math.round(input.riskScore * 100);
  const getRiskColor = (score: number) => {
    if (score < 0.3) return 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10';
    if (score < 0.6) return 'text-amber-400 border-amber-500/30 bg-amber-500/10';
    return 'text-rose-400 border-rose-500/30 bg-rose-500/10';
  };

  const getRiskBarColor = (score: number) => {
    if (score < 0.3) return 'bg-emerald-400';
    if (score < 0.6) return 'bg-amber-400';
    return 'bg-rose-500';
  };

  return (
    <div
      id="transaction-form-container"
      className="rounded-2xl border border-[#1E2530] bg-[#0C1017] p-5 lg:p-6 shadow-lg"
    >
      <div className="flex items-center justify-between border-b border-[#1A222D] pb-4">
        <div>
          <h2 className="text-sm font-semibold tracking-wide text-white uppercase">
            Transaction Parameters
          </h2>
          <p className="text-[11px] text-zinc-400">
            Define failed payment context to compute recovery policies
          </p>
        </div>
        <button
          type="button"
          onClick={onGenerateRandomId}
          className="flex items-center gap-1 text-[11px] font-mono text-zinc-400 hover:text-[#E8A33D] transition-colors"
        >
          <RefreshCw className="h-3 w-3" />
          <span>New ID</span>
        </button>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="mt-5 space-y-6"
      >
        {/* GROUP 1: TRANSACTION */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="flex h-1.5 w-1.5 rounded-full bg-[#E8A33D]" />
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-300">
              1. Transaction Context
            </h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            {/* Transaction ID */}
            <div>
              <label
                htmlFor="txn-id-input"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Transaction ID
              </label>
              <div className="relative">
                <input
                  id="txn-id-input"
                  type="text"
                  required
                  value={input.transactionId}
                  onChange={(e) => onChange({ transactionId: e.target.value })}
                  placeholder="txn_..."
                  className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] px-3 py-2 text-xs font-mono text-white transition-colors focus:border-[#E8A33D] focus:outline-none"
                />
              </div>
            </div>

            {/* Failure Type */}
            <div>
              <label
                htmlFor="failure-type-select"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Failure Type
              </label>
              <select
                id="failure-type-select"
                value={input.failureType}
                onChange={(e) =>
                  onChange({ failureType: e.target.value as FailureType })
                }
                className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] px-3 py-2 text-xs text-white transition-colors focus:border-[#E8A33D] focus:outline-none cursor-pointer"
              >
                {failureTypeOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Amount */}
            <div>
              <label
                htmlFor="amount-input"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Amount (₹)
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2 text-xs font-mono text-zinc-500">
                  ₹
                </span>
                <input
                  id="amount-input"
                  type="number"
                  min={1}
                  step={1}
                  required
                  value={input.amount}
                  onChange={(e) => onChange({ amount: Number(e.target.value) || 0 })}
                  className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] pl-7 pr-3 py-2 text-xs font-mono text-white transition-colors focus:border-[#E8A33D] focus:outline-none"
                />
              </div>
            </div>

            {/* Attempt Number */}
            <div>
              <label
                htmlFor="attempt-number-input"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Attempt Number
              </label>
              <input
                id="attempt-number-input"
                type="number"
                min={1}
                max={10}
                required
                value={input.attemptNumber}
                onChange={(e) =>
                  onChange({ attemptNumber: Number(e.target.value) || 1 })
                }
                className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] px-3 py-2 text-xs font-mono text-white transition-colors focus:border-[#E8A33D] focus:outline-none"
              />
            </div>
          </div>
        </div>

        {/* GROUP 2: RISK & RECOVERY */}
        <div className="pt-2 border-t border-[#171F2B]">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="flex h-1.5 w-1.5 rounded-full bg-[#E8A33D]" />
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-300">
                2. Risk & Recovery Context
              </h3>
            </div>
            <span
              className={`rounded border px-2 py-0.5 font-mono text-[10px] font-medium ${getRiskColor(
                input.riskScore
              )}`}
            >
              Risk: {riskPercent}% ({input.riskScore.toFixed(2)})
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {/* Risk Score Slider */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <label
                  htmlFor="risk-score-slider"
                  className="text-[11px] font-medium text-zinc-400"
                >
                  Risk Score
                </label>
                <span className="font-mono text-[11px] text-zinc-300">
                  {input.riskScore.toFixed(2)}
                </span>
              </div>
              <input
                id="risk-score-slider"
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={input.riskScore}
                onChange={(e) =>
                  onChange({ riskScore: parseFloat(e.target.value) })
                }
                className="w-full accent-[#E8A33D] bg-zinc-800 h-1.5 rounded-lg cursor-pointer"
              />
              <div className="mt-1 flex justify-between text-[9px] font-mono text-zinc-500">
                <span>0.00 Low</span>
                <span>0.50</span>
                <span>1.00 Critical</span>
              </div>
            </div>

            {/* Contact Fatigue Score Slider */}
            <div>
              <div className="flex justify-between items-center mb-1">
                <label
                  htmlFor="fatigue-score-slider"
                  className="text-[11px] font-medium text-zinc-400"
                >
                  Contact Fatigue
                </label>
                <span className="font-mono text-[11px] text-zinc-300">
                  {input.contactFatigueScore.toFixed(2)}
                </span>
              </div>
              <input
                id="fatigue-score-slider"
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={input.contactFatigueScore}
                onChange={(e) =>
                  onChange({ contactFatigueScore: parseFloat(e.target.value) })
                }
                className="w-full accent-sky-400 bg-zinc-800 h-1.5 rounded-lg cursor-pointer"
              />
              <div className="mt-1 flex justify-between text-[9px] font-mono text-zinc-500">
                <span>0.00 Fresh</span>
                <span>0.50</span>
                <span>1.00 Saturated</span>
              </div>
            </div>

            {/* Hours Since Failure */}
            <div>
              <label
                htmlFor="hours-failure-input"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Hours Since Failure
              </label>
              <div className="relative">
                <Clock className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <input
                  id="hours-failure-input"
                  type="number"
                  min={0}
                  max={720}
                  value={input.hoursSinceFailure}
                  onChange={(e) =>
                    onChange({
                      hoursSinceFailure: Math.max(0, Number(e.target.value)),
                    })
                  }
                  className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] pl-8 pr-3 py-2 text-xs font-mono text-white transition-colors focus:border-[#E8A33D] focus:outline-none"
                />
              </div>
            </div>

            {/* Current Discount Percent */}
            <div>
              <label
                htmlFor="discount-percent-input"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Current Discount (%)
              </label>
              <div className="relative">
                <Percent className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <input
                  id="discount-percent-input"
                  type="number"
                  min={0}
                  max={30}
                  value={input.currentDiscountPercent}
                  onChange={(e) =>
                    onChange({
                      currentDiscountPercent: Math.min(
                        30,
                        Math.max(0, Number(e.target.value))
                      ),
                    })
                  }
                  className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] pl-8 pr-3 py-2 text-xs font-mono text-white transition-colors focus:border-[#E8A33D] focus:outline-none"
                />
              </div>
            </div>

            {/* Customer Segment */}
            <div>
              <label
                htmlFor="customer-segment-select"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Customer Segment
              </label>
              <select
                id="customer-segment-select"
                value={input.customerSegment}
                onChange={(e) =>
                  onChange({
                    customerSegment: e.target.value as CustomerSegment,
                  })
                }
                className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] px-3 py-2 text-xs text-white transition-colors focus:border-[#E8A33D] focus:outline-none cursor-pointer"
              >
                {customerSegmentOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Already Recovered Toggle */}
            <div className="flex flex-col justify-center">
              <span className="text-[11px] font-medium text-zinc-400 mb-1">
                Already Recovered
              </span>
              <button
                type="button"
                id="already-recovered-toggle"
                onClick={() =>
                  onChange({ alreadyRecovered: !input.alreadyRecovered })
                }
                className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs font-mono transition-colors ${
                  input.alreadyRecovered
                    ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                    : 'border-[#1E2530] bg-[#070A0E] text-zinc-400'
                }`}
              >
                <span>{input.alreadyRecovered ? 'YES · Settled' : 'NO · Unsettled'}</span>
                <span
                  className={`h-2 w-2 rounded-full ${
                    input.alreadyRecovered ? 'bg-emerald-400' : 'bg-zinc-600'
                  }`}
                />
              </button>
            </div>
          </div>
        </div>

        {/* GROUP 3: CUSTOMER COMMUNICATION */}
        <div className="pt-2 border-t border-[#171F2B]">
          <div className="flex items-center gap-2 mb-3">
            <span className="flex h-1.5 w-1.5 rounded-full bg-[#E8A33D]" />
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-300">
              3. Customer Communication
            </h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
            {/* Customer Name */}
            <div>
              <label
                htmlFor="customer-name-input"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Customer Name
              </label>
              <div className="relative">
                <User className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <input
                  id="customer-name-input"
                  type="text"
                  value={input.customerName}
                  onChange={(e) => onChange({ customerName: e.target.value })}
                  placeholder="e.g. Aarav Patel"
                  className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] pl-8 pr-3 py-2 text-xs text-white transition-colors focus:border-[#E8A33D] focus:outline-none"
                />
              </div>
            </div>

            {/* Communication Channel */}
            <div>
              <label
                htmlFor="comm-channel-select"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Channel
              </label>
              <div className="relative">
                <Mail className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
                <select
                  id="comm-channel-select"
                  value={input.communicationChannel}
                  onChange={(e) =>
                    onChange({
                      communicationChannel: e.target
                        .value as CommunicationChannel,
                    })
                  }
                  className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] pl-8 pr-3 py-2 text-xs text-white transition-colors focus:border-[#E8A33D] focus:outline-none cursor-pointer"
                >
                  {channelOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Payment Link URL */}
            <div>
              <label
                htmlFor="payment-link-input"
                className="block text-[11px] font-medium text-zinc-400 mb-1"
              >
                Payment Link URL
              </label>
              <div className="relative">
                <Link className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500" />
                <input
                  id="payment-link-input"
                  type="text"
                  value={input.paymentLinkUrl}
                  onChange={(e) => onChange({ paymentLinkUrl: e.target.value })}
                  placeholder="https://pay.engine.io/..."
                  className="w-full rounded-lg border border-[#1E2530] bg-[#070A0E] pl-8 pr-3 py-2 text-xs font-mono text-white transition-colors focus:border-[#E8A33D] focus:outline-none truncate"
                />
              </div>
            </div>
          </div>
        </div>

        {/* PRIMARY ACTION BUTTON */}
        <div className="pt-2">
          <button
            type="submit"
            id="run-decision-button"
            disabled={isLoading}
            className={`group relative flex w-full items-center justify-center gap-3 rounded-xl border border-[#E8A33D] bg-gradient-to-r from-[#E8A33D] to-[#F59E0B] py-3.5 px-6 font-semibold text-black shadow-[0_0_25px_rgba(232,163,61,0.25)] transition-all hover:bg-[#F3C06B] hover:shadow-[0_0_35px_rgba(232,163,61,0.4)] active:scale-[0.99] disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer`}
          >
            {isLoading ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin text-black" />
                <span className="text-xs tracking-wider uppercase font-bold text-black">
                  ANALYZING TRANSACTION CONDITIONS...
                </span>
              </>
            ) : (
              <>
                <Zap className="h-4 w-4 fill-black text-black" />
                <span className="text-xs tracking-wider uppercase font-bold text-black">
                  RUN RECOVERY DECISION
                </span>
                <span className="rounded bg-black/20 px-2 py-0.5 font-mono text-[10px] text-black/90 ml-1 hidden sm:inline">
                  ⌘ + Enter
                </span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
