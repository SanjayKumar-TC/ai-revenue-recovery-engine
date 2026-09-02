import React, { useState } from 'react';
import {
  Check,
  Copy,
  Mail,
  MessageSquare,
  Send,
  Sparkles,
} from 'lucide-react';
import { DecisionResult } from '../types';

interface CustomerCommunicationProps {
  decision: DecisionResult | null;
  onDispatchTest?: () => void;
}

export const CustomerCommunication: React.FC<CustomerCommunicationProps> = ({
  decision,
  onDispatchTest,
}) => {
  const [copied, setCopied] = useState(false);
  const [dispatched, setDispatched] = useState(false);

  if (!decision) return null;

  const { communication } = decision;

  const handleCopy = () => {
    navigator.clipboard.writeText(communication.message);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDispatch = () => {
    setDispatched(true);
    if (onDispatchTest) onDispatchTest();
    setTimeout(() => setDispatched(false), 2500);
  };

  // If nothing to show — no message and not sendable — render nothing
  if (!communication.sendable && !communication.message) return null;

  return (
    <div
      id="customer-communication-panel"
      className="rounded-2xl border border-[#1E2530] bg-[#0C1017] p-5 lg:p-6 shadow-md"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1A222D] pb-4">
        <div className="flex items-center gap-2.5">
          <MessageSquare className="h-4 w-4 text-[#E8A33D]" />
          <div>
            <h3 className="text-xs font-semibold tracking-wider text-white uppercase">
              Customer Communication
            </h3>
            <p className="text-[11px] text-zinc-400">
              Prepared AI customer notification for optimal recovery conversion
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            id="copy-message-button"
            onClick={handleCopy}
            className="flex items-center gap-1.5 rounded-lg border border-[#1E2530] bg-[#0A0D12] px-3 py-1.5 text-xs text-zinc-300 hover:text-white hover:border-[#2E3B4E] transition-colors cursor-pointer"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-emerald-400 font-medium">Copied!</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5 text-zinc-400" />
                <span>Copy Message</span>
              </>
            )}
          </button>

          <button
            id="test-dispatch-button"
            onClick={handleDispatch}
            disabled={!communication.sendable || dispatched}
            title="DRY RUN SIMULATION — no real message is sent"
            className="flex items-center gap-1.5 rounded-lg border border-[#E8A33D]/40 bg-[#161C26] px-3 py-1.5 text-xs font-medium text-[#F3C06B] hover:bg-[#1C2431] transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <Send className="h-3.5 w-3.5" />
            <span>{dispatched ? 'Simulated ✓' : 'Test Dispatch (Dry Run)'}</span>
          </button>
        </div>
      </div>

      {/* Metadata Ribbon */}
      <div className="mt-4 grid grid-cols-3 gap-3 rounded-xl border border-[#18212C] bg-[#080B0F] p-3 text-[11px] font-mono">
        <div>
          <div className="text-[10px] text-zinc-400 uppercase">Sendable</div>
          <div
            className={`mt-0.5 font-bold ${
              communication.sendable ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {communication.sendable ? 'YES · Active' : 'NO · Inactive action'}
          </div>
        </div>
        <div className="border-l border-[#18212C] pl-3">
          <div className="text-[10px] text-zinc-400 uppercase">Channel</div>
          <div className="mt-0.5 font-semibold text-white uppercase">
            {communication.channel ?? '—'}
          </div>
        </div>
        <div className="border-l border-[#18212C] pl-3">
          <div className="text-[10px] text-zinc-400 uppercase">Fallback</div>
          <div className="mt-0.5 font-medium text-zinc-300">
            {communication.fallback}
          </div>
        </div>
      </div>

      {/* Subject Line (if email) */}
      {communication.subject && (
        <div className="mt-3.5 rounded-lg border border-[#1A222D] bg-[#090C10] px-3.5 py-2 text-xs">
          <span className="text-[10px] font-mono text-zinc-400 uppercase mr-2">
            Subject:
          </span>
          <span className="text-zinc-200 font-medium">
            {communication.subject}
          </span>
        </div>
      )}

      {/* Message Text Area */}
      <div className="mt-3 rounded-xl border border-[#1B232F] bg-[#06080B] p-4">
        <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400 uppercase pb-2 border-b border-[#141A24]">
          <span>Customer Message Body</span>
          <span className="text-[10px] text-amber-500/80 font-mono">SIMULATION · NOT DELIVERED</span>
        </div>
        {communication.message ? (
          <pre className="mt-3 whitespace-pre-wrap font-sans text-xs text-zinc-200 leading-relaxed">
            {communication.message}
          </pre>
        ) : (
          <p className="mt-3 text-xs text-zinc-500 italic">
            No message body — this action does not trigger customer communication.
          </p>
        )}
      </div>
    </div>
  );
};
