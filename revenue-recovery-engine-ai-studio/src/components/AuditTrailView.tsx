import React, { useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Download,
  FileCheck2,
  Filter,
  Info,
  Layers,
  Search,
  Shield,
  Sparkles,
} from 'lucide-react';
import { AuditRecord, RecoveryAction } from '../types';
import { NumberCounter } from './NumberCounter';

interface AuditTrailViewProps {
  records: AuditRecord[];
  activeTxnId: string;
  onSelectTxn?: (txnId: string) => void;
}

export const AuditTrailView: React.FC<AuditTrailViewProps> = ({
  records,
  activeTxnId,
}) => {
  const [expandedId, setExpandedId] = useState<string | null>(records[0]?.id || null);
  const [filterAction, setFilterAction] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [copiedTrace, setCopiedTrace] = useState<string | null>(null);
  const [isExportedCsv, setIsExportedCsv] = useState(false);

  // Filtered records
  const filteredRecords = records.filter((rec) => {
    const matchesAction =
      filterAction === 'ALL' || rec.action === filterAction;
    const matchesSearch =
      searchQuery === '' ||
      rec.traceId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rec.transactionId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rec.decisionReason.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesAction && matchesSearch;
  });

  // Action distribution counts — all 8 backend action values
  const actionCounts: Record<RecoveryAction, number> = {
    discount:           0,
    retry:              0,
    payment_link:       0,
    reminder:           0,
    wait:               0,
    close:              0,
    escalate:           0,
    no_action_required: 0,
  };
  records.forEach((r) => {
    if (r.action in actionCounts) {
      actionCounts[r.action]++;
    }
  });

  const totalRecords = records.length;
  const latestRecord = records[0];
  const oldestRecord = records[records.length - 1];

  const handleCopyTrace = (traceId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(traceId);
    setCopiedTrace(traceId);
    setTimeout(() => setCopiedTrace(null), 2000);
  };

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  // CSV Export of current audit records
  const handleExportCsv = () => {
    // Determine records to export: if active filters exist and have matches, export filtered; otherwise all records
    const hasFilter = searchQuery.trim() !== '' || filterAction !== 'ALL';
    const dataToExport = hasFilter && filteredRecords.length > 0 ? filteredRecords : records;

    const headers = [
      'Record ID',
      'Trace ID',
      'Transaction ID',
      'Action',
      'Timestamp',
      'Decision Type',
      'Decision Reason',
      'Expected Value (INR)',
      'Recovery Probability (%)',
      'Escalation',
      'Terminal',
      'Customer Segment',
      'Communication Channel',
      'Communication Snippet',
      'Policy Version',
    ];

    const formatCsvValue = (val: unknown): string => {
      if (val === null || val === undefined) return '';
      if (typeof val === 'number') return String(val);
      const str = String(val);
      if (
        str.includes(',') ||
        str.includes('"') ||
        str.includes('\n') ||
        str.includes('\r')
      ) {
        return `"${str.replace(/"/g, '""')}"`;
      }
      return str;
    };

    const rows = dataToExport.map((rec) =>
      [
        formatCsvValue(rec.id),
        formatCsvValue(rec.traceId),
        formatCsvValue(rec.transactionId),
        formatCsvValue(rec.action),
        formatCsvValue(rec.timestamp),
        formatCsvValue(rec.decisionType),
        formatCsvValue(rec.decisionReason),
        formatCsvValue(typeof rec.expectedValue === 'number' ? rec.expectedValue.toFixed(2) : rec.expectedValue),
        formatCsvValue(typeof rec.recoveryProbability === 'number' ? rec.recoveryProbability.toFixed(2) : rec.recoveryProbability),
        formatCsvValue(rec.escalation),
        formatCsvValue(rec.terminal),
        formatCsvValue(rec.customerSegment),
        formatCsvValue(rec.communicationChannel),
        formatCsvValue(rec.communicationSnippet),
        formatCsvValue(rec.policyVersion),
      ].join(',')
    );

    const csvContent = [headers.join(','), ...rows].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const filename = `audit_records_${activeTxnId || 'export'}.csv`;

    if (typeof window.URL?.createObjectURL === 'function') {
      const blobUrl = window.URL.createObjectURL(blob);
      const dlLink = document.createElement('a');
      dlLink.href = blobUrl;
      dlLink.setAttribute('download', filename);
      document.body.appendChild(dlLink);
      dlLink.click();
      document.body.removeChild(dlLink);
      setTimeout(() => {
        window.URL.revokeObjectURL(blobUrl);
      }, 100);
    } else {
      const dataUri = `data:text/csv;charset=utf-8,${encodeURIComponent(csvContent)}`;
      const dlLink = document.createElement('a');
      dlLink.href = dataUri;
      dlLink.setAttribute('download', filename);
      document.body.appendChild(dlLink);
      dlLink.click();
      document.body.removeChild(dlLink);
    }

    setIsExportedCsv(true);
    setTimeout(() => setIsExportedCsv(false), 2000);
  };

  // Returns color config for any of the 8 backend action values.
  // Display labels are title-cased; underlying values remain backend literals.
  const getActionColor = (action: RecoveryAction): { dot: string; badge: string; bar: string; label: string } => {
    switch (action) {
      case 'discount':
        return {
          dot: 'bg-[#E8A33D]',
          badge: 'border-[#E8A33D]/40 bg-[#E8A33D]/10 text-[#F3C06B]',
          bar: 'bg-[#E8A33D]',
          label: 'DISCOUNT',
        };
      case 'retry':
        return {
          dot: 'bg-sky-400',
          badge: 'border-sky-500/40 bg-sky-500/10 text-sky-400',
          bar: 'bg-sky-400',
          label: 'RETRY',
        };
      case 'payment_link':
        return {
          dot: 'bg-cyan-400',
          badge: 'border-cyan-500/40 bg-cyan-500/10 text-cyan-400',
          bar: 'bg-cyan-400',
          label: 'PAYMENT LINK',
        };
      case 'reminder':
        return {
          dot: 'bg-teal-400',
          badge: 'border-teal-500/40 bg-teal-500/10 text-teal-400',
          bar: 'bg-teal-400',
          label: 'REMINDER',
        };
      case 'wait':
        return {
          dot: 'bg-amber-400',
          badge: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
          bar: 'bg-amber-400',
          label: 'WAIT',
        };
      case 'close':
        return {
          dot: 'bg-zinc-500',
          badge: 'border-zinc-600/40 bg-zinc-600/10 text-zinc-400',
          bar: 'bg-zinc-500',
          label: 'CLOSE',
        };
      case 'escalate':
        return {
          dot: 'bg-rose-400',
          badge: 'border-rose-500/40 bg-rose-500/10 text-rose-400',
          bar: 'bg-rose-400',
          label: 'ESCALATE',
        };
      case 'no_action_required':
        return {
          dot: 'bg-rose-800',
          badge: 'border-rose-900/40 bg-rose-900/10 text-rose-300',
          bar: 'bg-rose-800',
          label: 'NO ACTION',
        };
    }
  };

  return (
    <div id="audit-trail-workspace" className="space-y-6">
      {/* 24. Audit Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        <div className="rounded-xl border border-[#1E2530] bg-[#0E131A] p-4">
          <div className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
            Audit Records
          </div>
          <div className="mt-2 text-2xl font-bold text-white font-mono">
            <NumberCounter value={totalRecords} decimals={0} />
          </div>
          <div className="mt-1 text-[10px] text-zinc-400">
            For {activeTxnId}
          </div>
        </div>

        <div className="rounded-xl border border-[#1E2530] bg-[#0E131A] p-4">
          <div className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
            Latest Action
          </div>
          <div className="mt-2 text-xl font-bold text-[#E8A33D] font-mono">
            {latestRecord ? latestRecord.action : 'None'}
          </div>
          <div className="mt-1 text-[10px] text-zinc-400 font-mono">
            {latestRecord ? latestRecord.traceId : '—'}
          </div>
        </div>

        <div className="rounded-xl border border-[#1E2530] bg-[#0E131A] p-4">
          <div className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
            First Recorded
          </div>
          <div className="mt-2 text-xl font-bold text-zinc-200 font-mono">
            {oldestRecord ? oldestRecord.timestamp : '—'}
          </div>
          <div className="mt-1 text-[10px] text-zinc-400">
            Initial transaction ingest
          </div>
        </div>

        <div className="rounded-xl border border-[#1E2530] bg-[#0E131A] p-4">
          <div className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
            Latest Recorded
          </div>
          <div className="mt-2 text-xl font-bold text-zinc-200 font-mono">
            {latestRecord ? latestRecord.timestamp : '—'}
          </div>
          <div className="mt-1 text-[10px] text-emerald-400 font-mono">
            Audit store synchronized
          </div>
        </div>
      </div>

      {/* 23. Action Distribution Visualization */}
      <div className="rounded-2xl border border-[#1E2530] bg-[#0C1017] p-5 lg:p-6 shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1A222D] pb-3.5">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-[#E8A33D]" />
            <h3 className="text-xs font-semibold tracking-wider text-white uppercase">
              Action Distribution
            </h3>
            <span className="text-[11px] text-zinc-400">
              ({totalRecords} decisions recorded)
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                const dataStr =
                  'data:text/json;charset=utf-8,' +
                  encodeURIComponent(JSON.stringify(records, null, 2));
                const dlAnchor = document.createElement('a');
                dlAnchor.setAttribute('href', dataStr);
                dlAnchor.setAttribute(
                  'download',
                  `audit_trail_${activeTxnId}.json`
                );
                dlAnchor.click();
              }}
              className="flex items-center gap-1.5 rounded-lg border border-[#1E2530] bg-[#0B0F14] px-2.5 py-1 text-xs text-zinc-300 hover:text-white hover:border-[#2D3748] transition-colors cursor-pointer"
              title="Export audit records as JSON"
            >
              <Download className="h-3 w-3" />
              <span>Export JSON</span>
            </button>
          </div>
        </div>

        {/* Animated Horizontal Bar Chart — all 8 backend actions */}
        <div className="mt-4 space-y-3">
          {(
            [
              'discount',
              'retry',
              'payment_link',
              'reminder',
              'wait',
              'close',
              'escalate',
              'no_action_required',
            ] as RecoveryAction[]
          ).map((action) => {
            const count = actionCounts[action];
            const pct =
              totalRecords > 0
                ? Math.round((count / totalRecords) * 100)
                : 0;
            const style = getActionColor(action);

            return (
              <div key={action} className="space-y-1">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="flex items-center gap-2 text-zinc-300 font-medium">
                    <span className={`h-2 w-2 rounded-full ${style.dot}`} />
                    <span>{style.label}</span>
                  </span>
                  <span className="text-zinc-400">
                    <span className="font-bold text-white mr-1.5">{count}</span>
                    <span className="text-zinc-400">({pct}%)</span>
                  </span>
                </div>
                <div className="h-2 w-full rounded-full bg-[#141A23] overflow-hidden">
                  <div
                    className={`h-full rounded-full ${style.bar} transition-all duration-700 ease-out`}
                    style={{ width: `${Math.max(pct, count > 0 ? 6 : 0)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 21. Audit Records Table with 22. Smooth Expansion */}
      <div className="rounded-2xl border border-[#1E2530] bg-[#0C1017] p-5 lg:p-6 shadow-md">
        {/* Header & Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#1A222D] pb-4">
          <div className="flex items-center gap-2">
            <FileCheck2 className="h-4 w-4 text-[#E8A33D]" />
            <h3 className="text-xs font-semibold tracking-wider text-white uppercase">
              Immutable Trace Logs
            </h3>
            <span className="font-mono text-xs text-zinc-400">
              ({filteredRecords.length} records)
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Search Filter */}
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-3 w-3 text-zinc-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter trace or reason..."
                className="rounded-lg border border-[#1E2530] bg-[#070A0E] pl-7 pr-3 py-1.5 text-xs text-white placeholder-zinc-500 focus:border-[#E8A33D] focus:outline-none font-mono"
              />
            </div>

            {/* Action Filter Pills — all 8 backend actions + ALL */}
            <div className="flex flex-wrap items-center gap-0.5 rounded-lg border border-[#1E2530] bg-[#070A0E] p-0.5 text-[10px] font-mono">
              {(['ALL', 'discount', 'retry', 'payment_link', 'reminder', 'wait', 'close', 'escalate', 'no_action_required'] as const).map((act) => (
                <button
                  key={act}
                  onClick={() => setFilterAction(act)}
                  className={`rounded-md px-2 py-1 font-medium transition-colors ${
                    filterAction === act
                      ? 'bg-[#E8A33D] text-black font-bold'
                      : 'text-zinc-400 hover:text-white'
                  }`}
                >
                  {act === 'ALL' ? 'ALL' : getActionColor(act as RecoveryAction).label}
                </button>
              ))}
            </div>

            {/* Export Data Button */}
            <button
              id="export-data-btn"
              data-testid="export-data-btn"
              onClick={handleExportCsv}
              className="flex items-center gap-1.5 rounded-lg border border-[#1E2530] bg-[#0E131A] px-3 py-1.5 text-xs font-medium text-zinc-200 hover:text-white hover:border-[#E8A33D]/50 hover:bg-[#151D28] transition-all cursor-pointer shadow-sm active:scale-[0.98]"
              title="Export current audit records as CSV"
              aria-label="Export Data"
            >
              {isExportedCsv ? (
                <Check className="h-3.5 w-3.5 text-emerald-400" />
              ) : (
                <Download className="h-3.5 w-3.5 text-[#E8A33D]" />
              )}
              <span>Export Data</span>
            </button>
          </div>
        </div>

        {/* Record Rows */}
        <div className="mt-4 divide-y divide-[#171F2B]">
          {filteredRecords.length === 0 ? (
            /* 28. Empty State */
            <div className="py-12 text-center">
              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl border border-zinc-800 bg-[#0A0D12] text-zinc-500">
                <FileCheck2 className="h-5 w-5" />
              </div>
              <h4 className="mt-3 text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                No Audit Records Found
              </h4>
              <p className="mt-1 text-xs text-zinc-500 max-w-sm mx-auto">
                No decision trace matching the current filters. Run a recovery
                decision or clear your search criteria.
              </p>
            </div>
          ) : (
            filteredRecords.map((record) => {
              const isExpanded = expandedId === record.id;
              const style = getActionColor(record.action);

              return (
                <div
                  key={record.id}
                  id={`audit-row-${record.id}`}
                  className="py-3 transition-colors"
                >
                  {/* Collapsed Row Summary */}
                  <div
                    onClick={() => toggleExpand(record.id)}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 p-2 rounded-xl hover:bg-[#111722] cursor-pointer transition-colors group"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
                      <span
                        className={`rounded-md border px-2 py-0.5 font-mono text-[11px] font-bold ${style.badge}`}
                      >
                        {style.label}
                      </span>
                      <button
                        onClick={(e) => handleCopyTrace(record.traceId, e)}
                        className="flex items-center gap-1 font-mono text-xs text-zinc-400 hover:text-white transition-colors"
                      >
                        <span>{record.traceId}</span>
                        {copiedTrace === record.traceId ? (
                          <Check className="h-3 w-3 text-emerald-400" />
                        ) : (
                          <Copy className="h-3 w-3 text-zinc-500 group-hover:text-zinc-300" />
                        )}
                      </button>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-4 text-xs">
                      <div className="flex items-center gap-1 font-mono text-zinc-300">
                        <span className="text-[10px] text-zinc-400">EV:</span>
                        <span className="font-semibold text-[#F3C06B]">
                          {record.expectedValue !== null
                            ? `₹${record.expectedValue.toLocaleString()}`
                            : '—'}
                        </span>
                      </div>

                      <div className="font-mono text-zinc-400 text-[11px] flex items-center gap-1">
                        <Clock className="h-3 w-3 text-zinc-400" />
                        <span>{record.timestamp}</span>
                      </div>

                      <div className="text-zinc-500 group-hover:text-zinc-300 transition-colors">
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 22. Smooth Content Expansion */}
                  {isExpanded && (
                    <div
                      id={`audit-detail-${record.id}`}
                      className="mt-2 ml-2 sm:ml-5 mr-2 rounded-xl border border-[#1E2734] bg-[#070A0E] p-4 text-xs space-y-3 animate-fadeIn"
                    >
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 border-b border-[#151D28] pb-3 text-[11px] font-mono">
                        <div>
                          <div className="text-zinc-400 uppercase text-[9px]">
                            Decision Type
                          </div>
                          <div className="mt-0.5 font-medium text-white truncate">
                            {record.decisionType}
                          </div>
                        </div>
                        <div>
                          <div className="text-zinc-400 uppercase text-[9px]">
                            Recovery Probability
                          </div>
                          <div className="mt-0.5 font-bold text-sky-400">
                            {record.recoveryProbability !== null
                              ? `${record.recoveryProbability}%`
                              : '—'}
                          </div>
                        </div>
                        <div>
                          <div className="text-zinc-400 uppercase text-[9px]">
                            Escalation
                          </div>
                          <div
                            className={`mt-0.5 font-semibold ${
                              record.escalation === 'Not Required'
                                ? 'text-emerald-400'
                                : 'text-rose-400'
                            }`}
                          >
                            {record.escalation}
                          </div>
                        </div>
                        <div>
                          <div className="text-zinc-400 uppercase text-[9px]">
                            Policy Version
                          </div>
                          <div className="mt-0.5 text-zinc-300">
                            {record.policyVersion}
                          </div>
                        </div>
                      </div>

                      <div>
                        <span className="text-[10px] font-semibold text-zinc-400 uppercase font-mono">
                          Decision Reasoning
                        </span>
                        <p className="mt-1 text-zinc-300 leading-relaxed">
                          {record.decisionReason}
                        </p>
                      </div>

                      <div className="pt-2 border-t border-[#151D28] flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[11px]">
                        <div className="text-zinc-400 font-mono truncate max-w-md">
                          <span className="text-zinc-400 mr-1.5 uppercase text-[9px]">
                            Customer Snippet:
                          </span>
                          <span className="text-zinc-300 italic">
                            "{record.communicationSnippet}"
                          </span>
                        </div>
                        <span className="rounded bg-zinc-900 border border-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-400 shrink-0">
                          Channel: {record.communicationChannel}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
