import React, { useEffect, useState } from 'react';
import {
  AuditTrailView,
} from './components/AuditTrailView';
import { CustomerCommunication } from './components/CustomerCommunication';
import { DecisionHero } from './components/DecisionHero';
import { ErrorState } from './components/ErrorState';
import { Header } from './components/Header';
import { ProcessingOverlay } from './components/ProcessingOverlay';
import { Sidebar } from './components/Sidebar';
import { SummaryMetrics } from './components/SummaryMetrics';
import { SystemTelemetryView } from './components/SystemTelemetryView';
import { TransactionForm } from './components/TransactionForm';
import {
  DEFAULT_TRANSACTION,
  INITIAL_SESSION_ACTIVITY,
} from './data/mockData';
import { requestDecision, ApiError } from './api/recoveryClient';
import {
  ActiveTab,
  AuditRecord,
  DecisionResult,
  SessionActivityItem,
  TransactionInput,
} from './types';

export default function App() {
  // Main state
  const [transactionInput, setTransactionInput] =
    useState<TransactionInput>(DEFAULT_TRANSACTION);

  // Dashboard starts in standby — no auto-decision, no mock data
  const [decision, setDecision] = useState<DecisionResult | null>(null);

  // Audit records come only from GET /audit/{transaction_id} — never fabricated
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);

  const [sessionActivity, setSessionActivity] =
    useState<SessionActivityItem[]>(INITIAL_SESSION_ACTIVITY);

  const [activeTab, setActiveTab] = useState<ActiveTab>('decision');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  // API error state — holds the error message to display, or null when clean
  const [apiError, setApiError] = useState<string | null>(null);

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState<boolean>(false);
  const [globalSearch, setGlobalSearch] = useState<string>('');

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage((current) => (current === msg ? null : current));
    }, 2400);
  };

  /**
   * handleRunDecision — the ONLY decision flow path.
   * Calls POST /decide via recoveryClient.requestDecision().
   * No mocks. No fallbacks. No setTimeout-simulated decisions.
   */
  const handleRunDecision = async (customInput?: TransactionInput) => {
    const targetInput = customInput || transactionInput;
    setIsProcessing(true);
    setApiError(null);

    try {
      const newDecision = await requestDecision(targetInput);
      setDecision(newDecision);

      // Append to session activity log
      const evDisplay = newDecision.expectedValue !== null
        ? `EV ₹${newDecision.expectedValue.toFixed(2)}`
        : 'EV N/A';
      const probDisplay = newDecision.recoveryProbability !== null
        ? `(${newDecision.recoveryProbability.toFixed(1)}%)`
        : '';

      const newActivity: SessionActivityItem = {
        id: `act_${Date.now()}`,
        timestamp: newDecision.timestamp,
        title: `Recovery decision evaluated`,
        detail: `${newDecision.action} · ${evDisplay} ${probDisplay}`.trim(),
        type: 'decision',
      };
      setSessionActivity((prev) => [newActivity, ...prev.slice(0, 15)]);

      showToast(`Decision: ${newDecision.action.toUpperCase()} — ${newDecision.reasoning.slice(0, 60)}…`);
    } catch (err) {
      // Surface a clean error message — never leak raw tracebacks
      let message = 'The recovery decision could not be completed.';
      if (err instanceof ApiError) {
        if (err.status === 400) {
          message = `Invalid request: ${err.detail}`;
        } else if (err.status === 422) {
          message = `Validation error: the request did not pass backend schema checks.`;
        } else if (err.status === 500) {
          message = `Server error: the backend could not process this request. Please try again.`;
        } else {
          message = `Request failed (HTTP ${err.status}). Please check the backend and try again.`;
        }
      } else if (err instanceof TypeError) {
        // Network failure (backend offline, CORS, etc.)
        message = `Network error: could not reach the backend. Is the server running on port 8000?`;
      }
      setApiError(message);
      setDecision(null);
      showToast('Decision failed — see error details');
    } finally {
      setIsProcessing(false);
    }
  };

  // Keyboard shortcut: Cmd+Enter or Ctrl+Enter to trigger decision
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        if (!isProcessing) {
          handleRunDecision();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [transactionInput, isProcessing]);

  // Preset scenario selection
  const handleSelectPreset = (preset: TransactionInput) => {
    setTransactionInput(preset);
    setApiError(null);
    showToast(`Loaded: ${preset.customerSegment} · ${preset.transactionId}`);
    // Immediately run the decision with the newly loaded preset
    handleRunDecision(preset);
  };

  // Reset to default standby state
  const handleResetToDemo = () => {
    setTransactionInput(DEFAULT_TRANSACTION);
    setDecision(null);
    setApiError(null);
    showToast('Reset to default — submit to evaluate');
  };

  // Random ID generator
  const handleGenerateRandomId = () => {
    const chars = '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ';
    let res = '';
    for (let i = 0; i < 6; i++) {
      res += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    const newId = `txn_${res}`;
    setTransactionInput((prev) => ({
      ...prev,
      transactionId: newId,
      paymentLinkUrl: `https://pay.engine.io/rec/${res}`,
    }));
    showToast(`Generated ID: ${newId}`);
  };

  // Quick Action Handler
  const handleQuickAction = (action: string) => {
    switch (action) {
      case 'RUN_DECISION':
        setActiveTab('decision');
        handleRunDecision();
        break;
      case 'VIEW_AUDIT':
        setActiveTab('audit');
        break;
      case 'COPY_TXN':
        navigator.clipboard.writeText(transactionInput.transactionId);
        showToast(`Copied ${transactionInput.transactionId}`);
        break;
      case 'COPY_TRACE':
        if (decision) {
          navigator.clipboard.writeText(decision.traceId);
          showToast(`Copied ${decision.traceId}`);
        }
        break;
      case 'SIMULATE_ERROR':
        setActiveTab('decision');
        setApiError('Manually triggered error state for UI testing.');
        showToast('Showing error state');
        break;
    }
  };

  return (
    <div className="min-h-screen bg-[#080A0D] text-[#E5E9F0] flex flex-col font-sans">
      {/* Header */}
      <Header
        onSelectPreset={handleSelectPreset}
        onOpenMobileMenu={() => setMobileMenuOpen(true)}
        searchQuery={globalSearch}
        onSearchChange={(q) => {
          setGlobalSearch(q);
          if (q.trim().length > 0 && activeTab !== 'audit') {
            setActiveTab('audit');
          }
        }}
        onResetToDemo={handleResetToDemo}
        systemStatus={
          isProcessing
            ? 'PROCESSING'
            : apiError
            ? 'DEGRADED'
            : 'ONLINE'
        }
      />

      {/* Main Workspace with Sidebar */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onSelectPreset={handleSelectPreset}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          mobileOpen={mobileMenuOpen}
          onCloseMobile={() => setMobileMenuOpen(false)}
          totalAuditCount={auditRecords.length}
        />

        {/* Main Content Area */}
        <main
          id="main-dashboard-canvas"
          className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-8 py-6"
        >
          <div className="mx-auto max-w-7xl">
            {/* Top Summary Metrics */}
            <SummaryMetrics
              input={transactionInput}
              decision={decision}
            />

            {/* TAB 1: DECISION CENTER */}
            {activeTab === 'decision' && (
              <div id="decision-center-view" className="space-y-6">
                {apiError ? (
                  /* Real API error state */
                  <ErrorState
                    message={apiError}
                    onRetry={() => {
                      setApiError(null);
                      handleRunDecision();
                    }}
                  />
                ) : (
                  <>
                    {/* Recovery Decision HERO */}
                    <DecisionHero
                      decision={decision}
                      isLoading={isProcessing}
                      onRunDecision={() => handleRunDecision()}
                    />

                    {/* Customer Communication Panel */}
                    <CustomerCommunication
                      decision={decision}
                      onDispatchTest={() => {
                        showToast('DRY RUN: Test dispatch simulated — no real message sent');
                      }}
                    />

                    {/* Transaction Input Form */}
                    <TransactionForm
                      input={transactionInput}
                      onChange={(updates) =>
                        setTransactionInput((prev) => ({ ...prev, ...updates }))
                      }
                      onSubmit={() => handleRunDecision()}
                      isLoading={isProcessing}
                      onGenerateRandomId={handleGenerateRandomId}
                    />
                  </>
                )}
              </div>
            )}

            {/* TAB 2: AUDIT TRAIL */}
            {activeTab === 'audit' && (
              <AuditTrailView
                records={auditRecords}
                activeTxnId={transactionInput.transactionId}
              />
            )}

            {/* TAB 3: SYSTEM & TELEMETRY */}
            {activeTab === 'system' && (
              <SystemTelemetryView
                activityLog={sessionActivity}
                onTriggerQuickAction={handleQuickAction}
                activeTxnId={transactionInput.transactionId}
                latestTraceId={decision ? decision.traceId : null}
              />
            )}
          </div>
        </main>
      </div>

      {/* Processing State Overlay */}
      <ProcessingOverlay isVisible={isProcessing} />

      {/* Floating Action Toast */}
      {toastMessage && (
        <div
          id="floating-action-toast"
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-xl border border-[#E8A33D]/40 bg-[#0E141D] px-4 py-2.5 text-xs text-white shadow-2xl transition-all duration-300 animate-fadeIn"
        >
          <span className="h-2 w-2 rounded-full bg-[#E8A33D]" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}
