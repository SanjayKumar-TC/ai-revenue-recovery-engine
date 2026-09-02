import React from 'react';
import {
  Activity,
  CheckCircle2,
  Clock,
  Cpu,
  Database,
  KeyRound,
  Layers,
  Radio,
  Server,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { SessionActivityItem } from '../types';

interface SystemTelemetryViewProps {
  activityLog: SessionActivityItem[];
  onTriggerQuickAction: (action: string) => void;
  activeTxnId: string;
  latestTraceId: string | null;
}

export const SystemTelemetryView: React.FC<SystemTelemetryViewProps> = ({
  activityLog,
  onTriggerQuickAction,
  activeTxnId,
  latestTraceId,
}) => {
  const subsystemHealth = [
    {
      name: 'Decision Intelligence Core',
      service: 'engine-decision-v2',
      status: 'Operational',
      badge: '99.99% uptime',
      icon: Cpu,
    },
    {
      name: 'Audit Immutable Ledger',
      service: 'audit-stream-service',
      status: 'Operational',
      badge: 'Synchronized',
      icon: Database,
    },
    {
      name: 'Payment Gateway Telemetry',
      service: 'corridor-inbound-proxy',
      status: 'Operational',
      badge: '6 corridors live',
      icon: Radio,
    },
    {
      name: 'Customer Notification Dispatcher',
      service: 'dispatch-comm-broker',
      status: 'Operational',
      badge: 'Email/SMS/WA ready',
      icon: Zap,
    },
  ];

  return (
    <div id="system-telemetry-workspace" className="space-y-6">
      {/* 25. Subsystem Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {subsystemHealth.map((sub, i) => {
          const Icon = sub.icon;
          return (
            <div
              key={i}
              className="rounded-xl border border-[#1E2530] bg-[#0E131A] p-4 transition-all hover:border-[#2D3748]"
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono text-zinc-400 uppercase">
                  {sub.service}
                </span>
                <span className="flex h-2 w-2 rounded-full bg-emerald-400" />
              </div>
              <div className="mt-3 flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="text-xs font-semibold text-white truncate">
                  {sub.name}
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between pt-2 border-t border-[#171E28] text-[10px] font-mono">
                <span className="text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="h-2.5 w-2.5" />
                  {sub.status}
                </span>
                <span className="text-zinc-400">{sub.badge}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 26. Session Activity Timeline */}
        <div className="lg:col-span-2 rounded-2xl border border-[#1E2530] bg-[#0C1017] p-5 lg:p-6 shadow-md">
          <div className="flex items-center justify-between border-b border-[#1A222D] pb-3.5">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-[#E8A33D]" />
              <h3 className="text-xs font-semibold tracking-wider text-white uppercase">
                Session Activity
              </h3>
            </div>
            <span className="font-mono text-[10px] text-zinc-400">
              Live Operator Events
            </span>
          </div>

          <div className="mt-4 space-y-3">
            {activityLog.map((act) => (
              <div
                key={act.id}
                className="flex items-start gap-3 rounded-lg border border-[#171F2B] bg-[#080B0F] p-3 text-xs"
              >
                <div className="mt-0.5 flex h-2 w-2 shrink-0 rounded-full bg-[#E8A33D]" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white truncate">
                      {act.title}
                    </span>
                    <span className="font-mono text-[10px] text-zinc-400 shrink-0 ml-2">
                      {act.timestamp}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[11px] text-zinc-400 truncate">
                    {act.detail}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 27. Quick Actions Panel */}
        <div className="rounded-2xl border border-[#1E2530] bg-[#0C1017] p-5 lg:p-6 shadow-md">
          <div className="border-b border-[#1A222D] pb-3.5">
            <h3 className="text-xs font-semibold tracking-wider text-white uppercase">
              Operational Quick Actions
            </h3>
            <p className="text-[10px] text-zinc-400 mt-0.5">
              Rapid trigger controls for testing and presentation
            </p>
          </div>

          <div className="mt-4 space-y-2.5 font-mono text-xs">
            <button
              onClick={() => onTriggerQuickAction('RUN_DECISION')}
              className="w-full flex items-center justify-between rounded-xl border border-[#E8A33D]/40 bg-[#E8A33D]/10 p-3 text-[#F3C06B] hover:bg-[#E8A33D]/20 transition-all font-semibold cursor-pointer"
            >
              <span>⚡ Run Recovery Decision</span>
              <span className="text-[10px] text-[#E8A33D]">⌘+Enter</span>
            </button>

            <button
              onClick={() => onTriggerQuickAction('VIEW_AUDIT')}
              className="w-full flex items-center justify-between rounded-xl border border-[#1E2530] bg-[#090D13] p-3 text-zinc-200 hover:border-[#2D3748] transition-all cursor-pointer"
            >
              <span>📋 View Audit Trail</span>
              <span className="text-[10px] text-zinc-400">Navigate</span>
            </button>

            <button
              onClick={() => onTriggerQuickAction('COPY_TXN')}
              className="w-full flex items-center justify-between rounded-xl border border-[#1E2530] bg-[#090D13] p-3 text-zinc-200 hover:border-[#2D3748] transition-all cursor-pointer"
            >
              <span>🔑 Copy Transaction ID</span>
              <span className="text-[10px] text-zinc-400">{activeTxnId}</span>
            </button>

            <button
              onClick={() => onTriggerQuickAction('COPY_TRACE')}
              className="w-full flex items-center justify-between rounded-xl border border-[#1E2530] bg-[#090D13] p-3 text-zinc-200 hover:border-[#2D3748] transition-all cursor-pointer"
            >
              <span>🔖 Copy Latest Trace ID</span>
              <span className="text-[10px] text-zinc-400">
                {latestTraceId || 'trace_none'}
              </span>
            </button>

            <button
              onClick={() => onTriggerQuickAction('SIMULATE_ERROR')}
              className="w-full flex items-center justify-between rounded-xl border border-rose-900/40 bg-rose-950/15 p-3 text-rose-300 hover:bg-rose-950/30 transition-all cursor-pointer"
            >
              <span>⚠️ Simulate Decision Error</span>
              <span className="text-[10px] text-rose-400">Test Error UI</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
