import React, { useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Bell,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  HelpCircle,
  Info,
  Link2,
  RefreshCw,
  Scale,
  Shield,
  Sparkles,
  XCircle,
  Zap,
} from 'lucide-react';
import { DecisionResult, RecoveryAction } from '../types';
import { NumberCounter } from './NumberCounter';

interface DecisionHeroProps {
  decision: DecisionResult | null;
  isLoading: boolean;
  onRunDecision: () => void;
}

export const DecisionHero: React.FC<DecisionHeroProps> = ({
  decision,
  isLoading,
  onRunDecision,
}) => {
  const [copiedTrace, setCopiedTrace] = useState(false);

  const handleCopyTrace = () => {
    if (!decision) return;
    navigator.clipboard.writeText(decision.traceId);
    setCopiedTrace(true);
    setTimeout(() => setCopiedTrace(false), 2000);
  };

  // Action styling map — all 8 backend action strings, displayed verbatim.
  // Colors and descriptions are semantically truthful to the backend action meaning.
  const actionStyles: Record<
    RecoveryAction,
    {
      badgeBg: string;
      badgeText: string;
      border: string;
      glow: string;
      icon: React.ElementType;
      label: string;
      desc: string;
    }
  > = {
    // ── ACTIVE RECOVERY ACTIONS (M6 communication sent) ────────────────────
    discount: {
      badgeBg: 'bg-[#E8A33D]/15',
      badgeText: 'text-[#F3C06B]',
      border: 'border-[#E8A33D]/50',
      glow: 'shadow-[0_0_35px_rgba(232,163,61,0.22)]',
      icon: Sparkles,
      label: 'DISCOUNT',
      desc: 'Apply financial incentive to maximize immediate payment completion.',
    },
    retry: {
      badgeBg: 'bg-sky-500/15',
      badgeText: 'text-sky-400',
      border: 'border-sky-500/50',
      glow: 'shadow-[0_0_35px_rgba(56,189,248,0.2)]',
      icon: RefreshCw,
      label: 'RETRY',
      desc: 'Schedule automated zero-cost re-attempt via optimized gateway corridor.',
    },
    payment_link: {
      badgeBg: 'bg-cyan-500/15',
      badgeText: 'text-cyan-400',
      border: 'border-cyan-500/50',
      glow: 'shadow-[0_0_35px_rgba(34,211,238,0.2)]',
      icon: Link2,
      label: 'PAYMENT LINK',
      desc: 'Send customer a fresh, secure payment URL to complete the transaction manually.',
    },
    reminder: {
      badgeBg: 'bg-teal-500/15',
      badgeText: 'text-teal-400',
      border: 'border-teal-500/50',
      glow: 'shadow-[0_0_35px_rgba(45,212,191,0.2)]',
      icon: Bell,
      label: 'REMINDER',
      desc: 'Notify customer via configured channel to prompt payment completion.',
    },
    // ── INACTIVE ACTIONS (no M6 communication) ─────────────────────────────
    wait: {
      badgeBg: 'bg-amber-500/15',
      badgeText: 'text-amber-400',
      border: 'border-amber-500/50',
      glow: 'shadow-[0_0_35px_rgba(245,158,11,0.2)]',
      icon: Clock,
      label: 'WAIT',
      desc: 'Hold transaction in cooling buffer to preserve option value for a later recovery action.',
    },
    close: {
      badgeBg: 'bg-zinc-600/15',
      badgeText: 'text-zinc-400',
      border: 'border-zinc-600/50',
      glow: 'shadow-[0_0_35px_rgba(113,113,122,0.2)]',
      icon: XCircle,
      label: 'CLOSE (TERMINAL)',
      desc: 'Recovery window expired or conditions unresolvable. Transaction closed permanently.',
    },
    escalate: {
      badgeBg: 'bg-rose-500/15',
      badgeText: 'text-rose-400',
      border: 'border-rose-500/50',
      glow: 'shadow-[0_0_35px_rgba(244,63,94,0.25)]',
      icon: AlertTriangle,
      label: 'ESCALATE',
      desc: 'Route transaction to manual compliance review due to elevated risk parameters.',
    },
    no_action_required: {
      badgeBg: 'bg-rose-900/15',
      badgeText: 'text-rose-300',
      border: 'border-rose-900/50',
      glow: 'shadow-[0_0_35px_rgba(244,63,94,0.12)]',
      icon: AlertCircle,
      label: 'NO ACTION',
      desc: 'Transaction already recovered or no scoreable recovery action available.',
    },
  };

  if (!decision) {
    return (
      <div
        id="decision-hero-standby"
        className="relative overflow-hidden rounded-2xl border border-[#1E2530] bg-gradient-to-b from-[#10151E] to-[#0A0D12] p-8 text-center"
      >
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-[#E8A33D]/30 bg-[#161C26] shadow-[0_0_20px_rgba(232,163,61,0.12)]">
          <Scale className="h-7 w-7 text-[#E8A33D]" />
        </div>
        <h3 className="mt-4 text-base font-semibold text-white tracking-wide uppercase">
          Recovery Decision Engine Standby
        </h3>
        <p className="mt-2 mx-auto max-w-md text-xs text-zinc-400 leading-relaxed">
          Configure transaction parameters or select a scenario preset, then run
          the AI evaluation model to compute expected recovery values.
        </p>
        <div className="mt-6 flex justify-center">
          <button
            onClick={onRunDecision}
            className="flex items-center gap-2 rounded-xl border border-[#E8A33D] bg-[#E8A33D] px-6 py-2.5 text-xs font-semibold text-black hover:bg-[#F3C06B] transition-all shadow-[0_0_20px_rgba(232,163,61,0.25)] cursor-pointer"
          >
            <Zap className="h-3.5 w-3.5 fill-black" />
            <span>RUN RECOVERY DECISION</span>
          </button>
        </div>
      </div>
    );
  }

  const currentAction = actionStyles[decision.action] ?? actionStyles['escalate'];
  const ActionIcon = currentAction.icon;

  return (
    <div
      id="decision-hero"
      className={`relative overflow-hidden rounded-2xl border ${currentAction.border} bg-gradient-to-b from-[#121822] via-[#0E131A] to-[#080B0F] p-6 lg:p-7 ${currentAction.glow} transition-all duration-300`}
    >
      {/* Top Header Row of Hero */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1A222D] pb-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-2 w-2 rounded-full bg-[#E8A33D] animate-pulse" />
          <span className="font-mono text-[11px] font-semibold tracking-widest text-[#E8A33D] uppercase">
            Recovery Decision Intelligence
          </span>
          <span className="rounded bg-[#1A2330] px-2 py-0.5 font-mono text-[10px] text-zinc-300">
            {decision.policyVersion}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleCopyTrace}
            title="Copy Trace Identifier"
            className="flex items-center gap-1.5 rounded-lg border border-[#212B38] bg-[#0E141C] px-2.5 py-1 text-[11px] font-mono text-zinc-400 hover:text-white hover:border-[#2E3B4E] transition-colors"
          >
            {copiedTrace ? (
              <>
                <Check className="h-3 w-3 text-emerald-400" />
                <span className="text-emerald-400">Copied</span>
              </>
            ) : (
              <>
                <Copy className="h-3 w-3 text-zinc-500" />
                <span>{decision.traceId || '—'}</span>
              </>
            )}
          </button>
          <span className="font-mono text-[11px] text-zinc-500">
            {decision.timestamp}
          </span>
        </div>
      </div>

      {/* Main Selected Action Banner */}
      <div className="mt-6 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
            Recommended Recovery Action
          </div>
          <div className="mt-2 flex items-center gap-3.5">
            <div
              className={`inline-flex items-center gap-3 rounded-2xl border px-5 py-2.5 ${currentAction.border} ${currentAction.badgeBg} shadow-[0_0_20px_rgba(232,163,61,0.15)]`}
            >
              <ActionIcon className={`h-6 w-6 lg:h-7 lg:w-7 ${currentAction.badgeText}`} />
              <span
                className={`text-3xl lg:text-4xl font-extrabold tracking-tight ${currentAction.badgeText}`}
              >
                {currentAction.label}
              </span>
            </div>
          </div>
          <p className="mt-2.5 text-xs text-zinc-300 max-w-md leading-relaxed">
            {currentAction.desc}
          </p>
        </div>

        {/* Financial Metrics Inset Boxes */}
        <div className="grid grid-cols-2 gap-3 w-full md:w-auto">
          <div className="rounded-xl border border-[#222C3A] bg-[#090D12] p-3.5 min-w-[150px]">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              Expected Net Value
            </div>
            <div className="mt-1 text-2xl font-bold text-white tracking-tight">
              {decision.expectedValue !== null ? (
                <NumberCounter
                  value={decision.expectedValue}
                  prefix="₹"
                  decimals={2}
                  className="text-[#F3C06B]"
                />
              ) : (
                <span className="text-zinc-500 text-lg font-mono">—</span>
              )}
            </div>
            <div className="mt-1 text-[10px] text-zinc-500 font-mono">
              {decision.expectedValue !== null ? decision.decisionType : 'Not computed'}
            </div>
          </div>

          <div className="rounded-xl border border-[#222C3A] bg-[#090D12] p-3.5 min-w-[150px]">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
              Recovery Probability
            </div>
            <div className="mt-1 text-2xl font-bold text-white tracking-tight">
              {decision.recoveryProbability !== null ? (
                <NumberCounter
                  value={decision.recoveryProbability}
                  suffix="%"
                  decimals={2}
                  className="text-white"
                />
              ) : (
                <span className="text-zinc-500 text-lg font-mono">—</span>
              )}
            </div>
            <div className="mt-1 text-[10px] text-zinc-500 font-mono">
              {decision.recoveryProbability !== null ? 'Model estimate' : 'Not computed'}
            </div>
          </div>
        </div>
      </div>

      {/* Decision Metadata Ribbon */}
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-3 rounded-xl border border-[#1B232E] bg-[#0A0E13] p-3">
        <div className="flex items-center justify-between sm:justify-start sm:gap-3 px-2">
          <span className="text-[11px] text-zinc-400">Decision Type:</span>
          <span className="font-mono text-xs font-medium text-zinc-200">
            {decision.decisionType}
          </span>
        </div>
        <div className="flex items-center justify-between sm:justify-start sm:gap-3 px-2 border-t sm:border-t-0 sm:border-l border-[#1B232E] pt-2 sm:pt-0">
          <span className="text-[11px] text-zinc-400">Escalation:</span>
          <span
            className={`font-mono text-xs font-semibold ${
              decision.escalation === 'Not Required'
                ? 'text-emerald-400'
                : 'text-rose-400'
            }`}
          >
            {decision.escalation}
          </span>
        </div>
        <div className="flex items-center justify-between sm:justify-start sm:gap-3 px-2 border-t sm:border-t-0 sm:border-l border-[#1B232E] pt-2 sm:pt-0">
          <span className="text-[11px] text-zinc-400">Terminal State:</span>
          <span className={`font-mono text-xs font-medium ${decision.terminal === 'Yes' ? 'text-rose-400' : 'text-emerald-400'}`}>
            {decision.terminal}
          </span>
        </div>
      </div>

      {/* Section: Why this decision? — Backend decision_reason verbatim */}
      <div className="mt-5 rounded-xl border border-[#1E2734] bg-[#0A0D12] p-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-[#E8A33D]" />
          <h4 className="text-xs font-semibold tracking-wider text-zinc-200 uppercase">
            Why This Decision?
          </h4>
        </div>
        <p className="mt-2 text-xs text-zinc-300 leading-relaxed">
          {decision.reasoning}
        </p>
        {/* Factors are only shown if backend returns them (currently always []) */}
        {decision.factors && decision.factors.length > 0 && (
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2.5 pt-3 border-t border-[#18212C]">
            {decision.factors.map((f, i) => (
              <div
                key={i}
                className="rounded-lg border border-[#1E2530] bg-[#0D1219] p-2.5"
              >
                <div className="flex items-center gap-1.5">
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      f.impact === 'positive'
                        ? 'bg-emerald-400'
                        : f.impact === 'negative'
                        ? 'bg-rose-400'
                        : 'bg-zinc-400'
                    }`}
                  />
                  <span className="text-[11px] font-semibold text-zinc-200">
                    {f.label}
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-zinc-400 leading-snug">
                  {f.detail}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
