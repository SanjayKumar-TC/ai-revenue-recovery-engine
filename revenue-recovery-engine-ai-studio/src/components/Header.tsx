import React from 'react';
import {
  Activity,
  Menu,
  RotateCcw,
  Search,
  Sparkles,
} from 'lucide-react';
import { PRESET_TRANSACTIONS } from '../data/mockData';
import { TransactionInput } from '../types';

interface HeaderProps {
  onSelectPreset: (preset: TransactionInput) => void;
  onOpenMobileMenu: () => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onResetToDemo: () => void;
  systemStatus: 'ONLINE' | 'PROCESSING' | 'DEGRADED';
}

export const Header: React.FC<HeaderProps> = ({
  onSelectPreset,
  onOpenMobileMenu,
  searchQuery,
  onSearchChange,
  onResetToDemo,
  systemStatus,
}) => {
  return (
    <header
      id="app-header"
      className="sticky top-0 z-30 w-full border-b border-[#1A222D] bg-[#080A0D]/90 backdrop-blur-md px-4 sm:px-6 lg:px-8 py-3.5"
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
        {/* Left: Brand Identity */}
        <div className="flex items-center gap-3">
          <button
            id="mobile-nav-toggle"
            onClick={onOpenMobileMenu}
            aria-label="Open navigation menu"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#1E2530] bg-[#0B0F14] text-zinc-400 hover:text-white hover:border-[#2D3748] lg:hidden transition-colors"
          >
            <Menu className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-3">
            <div className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-[#E8A33D]/40 bg-[#12161E] shadow-[0_0_15px_rgba(232,163,61,0.15)]">
              <Sparkles className="h-4 w-4 text-[#E8A33D]" />
              <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E8A33D] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#E8A33D]"></span>
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-semibold tracking-wider text-white uppercase">
                  Revenue Recovery Engine
                </h1>
                <span className="hidden sm:inline-block rounded border border-[#E8A33D]/30 bg-[#E8A33D]/10 px-1.5 py-0.5 font-mono text-[10px] font-medium tracking-tight text-[#E8A33D]">
                  v2.4 AI
                </span>
              </div>
              <p className="text-[11px] text-zinc-400 hidden sm:block">
                AI-powered recovery decision intelligence
              </p>
            </div>
          </div>
        </div>

        {/* Center: Quick Search / Lookup */}
        <div className="hidden md:flex items-center flex-1 max-w-xs relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
          <input
            id="quick-search-input"
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search txn_... or trace_..."
            className="w-full rounded-lg border border-[#1A222D] bg-[#0B0F14] pl-8 pr-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 transition-colors focus:border-[#E8A33D]/60 focus:bg-[#0E131A] focus:outline-none font-mono"
          />
        </div>

        {/* Right: Presets, Reset & System Status */}
        <div className="flex items-center gap-2.5">
          {/* Quick Presets Dropdown */}
          <div className="relative hidden xl:block">
            <select
              id="header-preset-select"
              aria-label="Load scenario preset"
              value=""
              onChange={(e) => {
                const idx = Number(e.target.value);
                if (!isNaN(idx) && PRESET_TRANSACTIONS[idx]) {
                  onSelectPreset(PRESET_TRANSACTIONS[idx].data);
                }
              }}
              className="rounded-lg border border-[#1E2530] bg-[#0B0F14] px-2.5 py-1.5 text-xs text-zinc-300 transition-colors hover:border-[#2D3748] focus:border-[#E8A33D]/60 focus:outline-none cursor-pointer"
            >
              <option value="" disabled>
                ⚡ Load Scenario Preset...
              </option>
              {PRESET_TRANSACTIONS.map((p, idx) => (
                <option key={idx} value={idx}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          {/* Quick Demo Reset */}
          <button
            id="reset-demo-button"
            onClick={onResetToDemo}
            title="Reset to benchmark demo transaction (txn_7F3K92)"
            className="flex items-center gap-1.5 rounded-lg border border-[#1E2530] bg-[#0B0F14] px-2.5 py-1.5 text-xs text-zinc-300 hover:text-white hover:border-[#2D3748] transition-colors"
          >
            <RotateCcw className="h-3 w-3 text-zinc-400" />
            <span className="hidden sm:inline">Reset Demo</span>
          </button>

          {/* System Online Status Indicator */}
          <div
            id="system-status-indicator"
            className="flex items-center gap-2 rounded-lg border border-[#19241D] bg-[#0C1510] px-3 py-1.5 shadow-sm"
          >
            <span className="relative flex h-2 w-2">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  systemStatus === 'ONLINE'
                    ? 'bg-emerald-400'
                    : systemStatus === 'PROCESSING'
                    ? 'bg-[#E8A33D]'
                    : 'bg-rose-400'
                }`}
              ></span>
              <span
                className={`relative inline-flex rounded-full h-2 w-2 ${
                  systemStatus === 'ONLINE'
                    ? 'bg-emerald-500'
                    : systemStatus === 'PROCESSING'
                    ? 'bg-[#E8A33D]'
                    : 'bg-rose-500'
                }`}
              ></span>
            </span>
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[11px] font-semibold tracking-wider text-emerald-400 uppercase">
                {systemStatus === 'ONLINE' ? 'SYSTEM ONLINE' : systemStatus}
              </span>
              <Activity className="h-3 w-3 text-emerald-500/70 hidden sm:inline" />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
