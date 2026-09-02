import React from 'react';
import {
  CirclePercent,
  Coins,
  Percent,
  Receipt,
} from 'lucide-react';
import { DecisionResult, TransactionInput } from '../types';
import { NumberCounter } from './NumberCounter';

interface SummaryMetricsProps {
  input: TransactionInput;
  decision: DecisionResult | null;
}

export const SummaryMetrics: React.FC<SummaryMetricsProps> = ({
  input,
  decision,
}) => {
  const expectedValue = decision ? decision.expectedValue : null;
  const recoveryProb = decision ? decision.recoveryProbability : null;

  return (
    <div
      id="top-summary-metrics"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mb-6"
    >
      {/* Metric 1: Expected Value */}
      <div
        id="metric-expected-value"
        className="group relative overflow-hidden rounded-xl border border-[#1E2530] bg-[#0E131A] p-4 transition-all duration-200 hover:border-[#E8A33D]/40 hover:bg-[#111721] hover:shadow-[0_4px_20px_rgba(0,0,0,0.4)]"
      >
        <div className="flex items-center justify-between text-zinc-400">
          <span className="text-[11px] font-semibold tracking-wider uppercase text-zinc-400">
            Expected Value
          </span>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#E8A33D]/30 bg-[#E8A33D]/10 text-[#E8A33D]">
            <Coins className="h-3.5 w-3.5" />
          </div>
        </div>

        <div className="mt-2.5 flex items-baseline gap-1">
          <div className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
            {expectedValue !== null ? (
              <NumberCounter
                value={expectedValue}
                prefix="₹"
                decimals={2}
                className="text-white"
              />
            ) : (
              <span className="text-zinc-500 font-mono text-xl">—</span>
            )}
          </div>
        </div>

        <div className="mt-2.5 flex items-center justify-between text-[11px]">
          <span className="inline-flex items-center gap-1 font-mono text-[10px] text-zinc-500">
            {decision ? decision.decisionType : 'Awaiting decision'}
          </span>
        </div>

        {/* Subtle accent border glow on top */}
        <div className="absolute inset-x-0 top-0 h-[1.5px] bg-gradient-to-r from-transparent via-[#E8A33D]/40 to-transparent" />
      </div>

      {/* Metric 2: Recovery Probability */}
      <div
        id="metric-recovery-probability"
        className="group relative overflow-hidden rounded-xl border border-[#1E2530] bg-[#0E131A] p-4 transition-all duration-200 hover:border-[#38BDF8]/40 hover:bg-[#111721] hover:shadow-[0_4px_20px_rgba(0,0,0,0.4)]"
      >
        <div className="flex items-center justify-between text-zinc-400">
          <span className="text-[11px] font-semibold tracking-wider uppercase text-zinc-400">
            Recovery Probability
          </span>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#38BDF8]/30 bg-[#38BDF8]/10 text-[#38BDF8]">
            <CirclePercent className="h-3.5 w-3.5" />
          </div>
        </div>

        <div className="mt-2.5 flex items-baseline gap-1">
          <div className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
            {recoveryProb !== null ? (
              <NumberCounter
                value={recoveryProb}
                suffix="%"
                decimals={2}
                className="text-white"
              />
            ) : (
              <span className="text-zinc-500 font-mono text-xl">—</span>
            )}
          </div>
        </div>

        <div className="mt-2.5 flex items-center justify-between text-[11px]">
          <div className="w-24 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-gradient-to-r from-[#38BDF8] to-[#E8A33D] h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(5, recoveryProb))}%` }}
            />
          </div>
          <span className="text-zinc-500 font-mono text-[10px]">
            {decision ? decision.decisionType : 'Model Standard'}
          </span>
        </div>
      </div>

      {/* Metric 3: Transaction Amount */}
      <div
        id="metric-transaction-amount"
        className="group relative overflow-hidden rounded-xl border border-[#1E2530] bg-[#0E131A] p-4 transition-all duration-200 hover:border-zinc-700 hover:bg-[#111721]"
      >
        <div className="flex items-center justify-between text-zinc-400">
          <span className="text-[11px] font-semibold tracking-wider uppercase text-zinc-400">
            Transaction Amount
          </span>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800/40 text-zinc-300">
            <Receipt className="h-3.5 w-3.5" />
          </div>
        </div>

        <div className="mt-2.5 flex items-baseline gap-1">
          <div className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
            <NumberCounter
              value={input.amount}
              prefix="₹"
              decimals={0}
              className="text-white"
            />
          </div>
        </div>

        <div className="mt-2.5 flex items-center justify-between text-[11px]">
          <span className="font-mono text-zinc-400 text-[10px] truncate max-w-[130px]">
            {input.transactionId}
          </span>
          <span className="rounded bg-zinc-800/80 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">
            Att. #{input.attemptNumber}
          </span>
        </div>
      </div>

      {/* Metric 4: Current Discount */}
      <div
        id="metric-current-discount"
        className="group relative overflow-hidden rounded-xl border border-[#1E2530] bg-[#0E131A] p-4 transition-all duration-200 hover:border-zinc-700 hover:bg-[#111721]"
      >
        <div className="flex items-center justify-between text-zinc-400">
          <span className="text-[11px] font-semibold tracking-wider uppercase text-zinc-400">
            Current Discount
          </span>
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-400">
            <Percent className="h-3.5 w-3.5" />
          </div>
        </div>

        <div className="mt-2.5 flex items-baseline gap-1">
          <div className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
            <NumberCounter
              value={input.currentDiscountPercent}
              suffix="%"
              decimals={0}
              className="text-white"
            />
          </div>
        </div>

        <div className="mt-2.5 flex items-center justify-between text-[11px]">
          <span className="text-zinc-500 text-[10px]">
            {input.currentDiscountPercent > 0 ? 'Concession active' : 'Zero discount rate'}
          </span>
          <span className="font-mono text-[10px] text-[#E8A33D]">
            Risk {(input.riskScore * 100).toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  );
};
