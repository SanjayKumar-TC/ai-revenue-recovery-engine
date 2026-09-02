import React from 'react';
import {
  BrainCircuit,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileCheck2,
  Layers,
  Server,
  Sparkles,
  X,
} from 'lucide-react';
import { PRESET_TRANSACTIONS } from '../data/mockData';
import { ActiveTab, TransactionInput } from '../types';

interface SidebarProps {
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  onSelectPreset: (preset: TransactionInput) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  totalAuditCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  onSelectPreset,
  isCollapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
  totalAuditCount,
}) => {
  const navItems = [
    {
      id: 'decision' as ActiveTab,
      label: 'Decision Center',
      sublabel: 'Active Evaluation',
      icon: BrainCircuit,
      badge: 'Live',
    },
    {
      id: 'audit' as ActiveTab,
      label: 'Audit Trail',
      sublabel: 'Trace & Records',
      icon: FileCheck2,
      badge: `${totalAuditCount}`,
    },
    {
      id: 'system' as ActiveTab,
      label: 'System',
      sublabel: 'Health & Policies',
      icon: Server,
      badge: 'v2.4',
    },
  ];

  const content = (
    <div className="flex h-full flex-col justify-between py-4">
      {/* Top Section */}
      <div className="space-y-6">
        {/* Navigation Items */}
        <div className="px-3">
          <div className={`mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 ${isCollapsed ? 'hidden' : 'block'}`}>
            Workspace
          </div>
          <nav className="space-y-1.5" aria-label="Main Navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  id={`nav-item-${item.id}`}
                  onClick={() => {
                    onTabChange(item.id);
                    onCloseMobile();
                  }}
                  title={item.label}
                  className={`group relative flex w-full items-center rounded-xl px-3 py-2.5 text-xs font-medium transition-all ${
                    isActive
                      ? 'border border-[#E8A33D]/30 bg-[#141A24] text-white shadow-[0_0_12px_rgba(232,163,61,0.08)]'
                      : 'border border-transparent text-zinc-400 hover:border-[#1E2530] hover:bg-[#0E131A] hover:text-zinc-200'
                  }`}
                >
                  {/* Active Indicator Bar */}
                  {isActive && (
                    <span className="absolute left-0 top-2 bottom-2 w-1 rounded-r bg-[#E8A33D]" />
                  )}

                  <Icon
                    className={`h-4 w-4 shrink-0 transition-colors ${
                      isActive
                        ? 'text-[#E8A33D]'
                        : 'text-zinc-400 group-hover:text-zinc-300'
                    } ${isCollapsed ? 'mx-auto' : 'mr-3'}`}
                  />

                  {!isCollapsed && (
                    <div className="flex flex-1 items-center justify-between overflow-hidden">
                      <div className="text-left truncate">
                        <div className="font-semibold truncate">{item.label}</div>
                        <div className="text-[10px] text-zinc-400 truncate">
                          {item.sublabel}
                        </div>
                      </div>
                      {item.badge && (
                        <span
                          className={`ml-2 rounded-md px-1.5 py-0.5 font-mono text-[10px] font-medium ${
                            isActive
                              ? 'bg-[#E8A33D]/20 text-[#E8A33D]'
                              : 'bg-[#161D27] text-zinc-400'
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Demo Scenarios Section */}
        {!isCollapsed && (
          <div className="px-3">
            <div className="mb-2 flex items-center justify-between px-3">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                Demo Scenarios
              </span>
              <Sparkles className="h-3 w-3 text-[#E8A33D]" />
            </div>

            <div className="space-y-1">
              {PRESET_TRANSACTIONS.slice(0, 4).map((preset, idx) => (
                <button
                  key={idx}
                  id={`sidebar-preset-${idx}`}
                  onClick={() => {
                    onSelectPreset(preset.data);
                    onTabChange('decision');
                    onCloseMobile();
                  }}
                  className="w-full text-left rounded-lg border border-transparent p-2 transition-all hover:border-[#1F2937] hover:bg-[#0F141C] group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium text-zinc-300 group-hover:text-white truncate">
                      {preset.label}
                    </span>
                    <span className="font-mono text-[10px] text-zinc-400 shrink-0">
                      ₹{preset.data.amount >= 1000 ? `${(preset.data.amount / 1000).toFixed(0)}k` : preset.data.amount}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[10px] text-zinc-400 truncate">
                    {preset.desc}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Section: Compact System Summary & Collapse Toggle */}
      <div className="space-y-3 px-3">
        {!isCollapsed && (
          <div className="rounded-xl border border-[#161E28] bg-[#0A0E13] p-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                Telemetry
              </span>
              <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-mono">
                <CheckCircle2 className="h-2.5 w-2.5" /> 99.98%
              </span>
            </div>
            <div className="mt-2 space-y-1 text-[11px]">
              <div className="flex justify-between text-zinc-400">
                <span>Model Latency</span>
                <span className="font-mono text-zinc-300">~620ms</span>
              </div>
              <div className="flex justify-between text-zinc-400">
                <span>Rule Engine</span>
                <span className="font-mono text-[#E8A33D]">Active</span>
              </div>
            </div>
          </div>
        )}

        {/* Desktop Collapse Toggle */}
        <button
          id="sidebar-collapse-button"
          onClick={onToggleCollapse}
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="hidden lg:flex w-full items-center justify-center rounded-lg border border-[#1A222D] bg-[#0B0F14] py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:border-[#2D3748] transition-colors"
        >
          {isCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <div className="flex items-center gap-2">
              <ChevronLeft className="h-3.5 w-3.5" />
              <span className="text-[11px]">Collapse Rail</span>
            </div>
          )}
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside
        id="desktop-sidebar"
        className={`hidden lg:block shrink-0 border-r border-[#161E29] bg-[#090C10] transition-all duration-300 ${
          isCollapsed ? 'w-18' : 'w-64'
        }`}
      >
        {content}
      </aside>

      {/* Mobile Drawer Overlay */}
      {mobileOpen && (
        <div
          id="mobile-drawer-backdrop"
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
        >
          <div
            id="mobile-drawer"
            className="fixed inset-y-0 left-0 w-72 border-r border-[#1E2530] bg-[#090C10] p-2 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-3 border-b border-[#161E29]">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-[#E8A33D]" />
                <span className="text-xs font-semibold uppercase tracking-wider text-white">
                  Navigation
                </span>
              </div>
              <button
                onClick={onCloseMobile}
                className="rounded-lg p-1 text-zinc-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {content}
          </div>
        </div>
      )}
    </>
  );
};
