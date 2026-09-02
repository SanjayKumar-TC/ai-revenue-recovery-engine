import React, { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react';

interface ProcessingOverlayProps {
  isVisible: boolean;
  onComplete?: () => void;
}

export const ProcessingOverlay: React.FC<ProcessingOverlayProps> = ({
  isVisible,
}) => {
  const [stepIndex, setStepIndex] = useState(0);

  const steps = [
    { label: 'Transaction context', status: 'validating' },
    { label: 'Risk assessment', status: 'scoring' },
    { label: 'Recovery evaluation', status: 'optimizing' },
    { label: 'Preparing recommendation', status: 'finalizing' },
  ];

  useEffect(() => {
    if (!isVisible) {
      setStepIndex(0);
      return;
    }

    // Step 0 -> 1 -> 2 -> 3 over 650ms
    const timer1 = setTimeout(() => setStepIndex(1), 150);
    const timer2 = setTimeout(() => setStepIndex(2), 340);
    const timer3 = setTimeout(() => setStepIndex(3), 520);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
    };
  }, [isVisible]);

  if (!isVisible) return null;

  return (
    <div
      id="processing-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 transition-opacity duration-200"
    >
      <div className="w-full max-w-md rounded-2xl border border-[#263140] bg-[#0C1017] p-6 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-[#1A222D] pb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-[#E8A33D]/40 bg-[#161C26]">
            <Sparkles className="h-4 w-4 text-[#E8A33D] animate-spin" />
          </div>
          <div>
            <h3 className="text-xs font-bold tracking-widest text-white uppercase font-mono">
              Analyzing Transaction
            </h3>
            <p className="text-[11px] text-zinc-400">
              Evaluating recovery yield under policy v2.4.1
            </p>
          </div>
        </div>

        <div className="mt-5 space-y-3 font-mono text-xs">
          {steps.map((step, idx) => {
            const isFinished = stepIndex > idx;
            const isCurrent = stepIndex === idx;

            return (
              <div
                key={idx}
                className={`flex items-center justify-between rounded-lg p-2.5 transition-all ${
                  isCurrent
                    ? 'border border-[#E8A33D]/30 bg-[#141B26] text-white'
                    : isFinished
                    ? 'text-zinc-300 bg-[#0A0D12]'
                    : 'text-zinc-600 bg-transparent'
                }`}
              >
                <span className="text-[11px]">{step.label}</span>
                <span className="flex items-center gap-1.5 text-[11px]">
                  {isFinished ? (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span>Ready</span>
                    </span>
                  ) : isCurrent ? (
                    <span className="text-[#E8A33D] flex items-center gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      <span>Evaluating</span>
                    </span>
                  ) : (
                    <span className="text-zinc-600">Pending</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>

        <div className="mt-5 pt-3 border-t border-[#171E28] flex justify-between items-center text-[10px] text-zinc-500 font-mono">
          <span>Engine: Decision Core v2.4</span>
          <span className="text-[#E8A33D]">Simulated Latency: ~650ms</span>
        </div>
      </div>
    </div>
  );
};
