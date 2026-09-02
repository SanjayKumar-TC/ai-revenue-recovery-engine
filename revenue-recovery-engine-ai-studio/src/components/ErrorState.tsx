import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorStateProps {
  onRetry: () => void;
  message?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  onRetry,
  message = 'The recovery decision could not be completed.',
}) => {
  return (
    <div
      id="decision-error-container"
      className="rounded-2xl border border-rose-900/40 bg-gradient-to-b from-[#160B0E] to-[#0D080A] p-7 text-center shadow-lg"
    >
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-rose-500/30 bg-rose-500/10 text-rose-400">
        <AlertTriangle className="h-6 w-6" />
      </div>
      <h3 className="mt-4 text-sm font-semibold tracking-wider text-rose-300 uppercase">
        Decision Unavailable
      </h3>
      <p className="mt-1.5 text-xs text-zinc-400 max-w-md mx-auto">
        {message}
      </p>
      <div className="mt-5 flex justify-center">
        <button
          onClick={onRetry}
          className="flex items-center gap-2 rounded-xl border border-rose-600 bg-rose-600/20 px-5 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-600 hover:text-white transition-all cursor-pointer"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>TRY AGAIN</span>
        </button>
      </div>
    </div>
  );
};
