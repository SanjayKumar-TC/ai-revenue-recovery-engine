# Revenue Recovery Engine
### AI-Powered Recovery Decision Intelligence — FinTech Operations Prototype

A high-performance standalone dashboard prototype for evaluating failed payment transactions and recommending the most effective financial recovery action.

---

## 🎯 Product Workflow & Visual Narrative

```text
TRANSACTION
      ↓
RISK & CONTEXT
      ↓
RECOVERY DECISION (Hero: DISCOUNT / RETRY / WAIT / ESCALATE)
      ↓
FINANCIAL IMPACT (Expected Net Value & Recovery Probability)
      ↓
CUSTOMER COMMUNICATION (Prepared Personalized Outreach)
      ↓
AUDIT TRAIL (Immutable Records, Action Distribution, & Trace Explorer)
```

---

## 🌟 Key Functional Features & Screens

1. **Top Summary Metrics**:
   - **Expected Value**: `₹512.77` with dynamic count-up animation and benchmark lift vs unassisted retries.
   - **Recovery Probability**: `28.49%` with visual confidence bar.
   - **Transaction Amount**: `₹2,000` with attempt and ID badges.
   - **Current Discount**: `10%` with fee concession indicators.

2. **Decision Hero (Primary Focal Point)**:
   - Dominant visual hierarchy with gold/amber accent (`#E8A33D`).
   - Selected action highlights: `DISCOUNT`, `RETRY`, `WAIT`, `ESCALATE`.
   - Inset financial metric widgets with numeric interpolation.
   - AI Reasoning breakdown: "Why This Decision?" with contextual factors (positive/neutral/negative).

3. **Transaction Parameters Form**:
   - Structured into 3 clear visual groups:
     - **Transaction Context**: Transaction ID, Failure Type, Amount, Attempt Number.
     - **Risk & Recovery Context**: Risk Score (with meter), Contact Fatigue, Hours Since Failure, Discount %, Customer Segment, Settlement toggle.
     - **Customer Communication**: Customer Name, Channel, Payment Link URL.
   - Primary action: **RUN RECOVERY DECISION** with loading spinner and `⌘ + Enter` keyboard shortcut.

4. **Staged Processing Animation**:
   - Simulated 650ms analysis with live checklist (`Transaction context ✓`, `Risk assessment ✓`, `Recovery evaluation ●`, `Preparing recommendation ...`).

5. **Customer Communication Panel**:
   - Delivery metadata: Sendable, Channel, Fallback status.
   - Copyable message body with instant tactile feedback.
   - Interactive "Test Dispatch" simulator.

6. **Audit Trail & Immutable Logs**:
   - **Action Distribution**: Animated bar chart showing proportion of recovery actions.
   - **Summary Metrics**: Total Audit Records, Latest Action, First/Latest Recorded timestamps.
   - **Expandable Rows**: Smooth accordion reveal of Decision Type, Reason, Expected Value, Probability, Escalation, Terminal status, Policy Version (`v2.4.1-rc3`), and Trace ID (`trace_7F3A91`).
   - **Search & Filter**: Real-time filtering by action or trace ID.
   - **Export**: Instant JSON export of authoritative audit trail records.

7. **System Status & Telemetry**:
   - Subsystem operational health: Decision Core, Audit Service, Corridor Proxy, Comm Broker.
   - Session Activity timeline of live operator interactions.
   - Quick Action triggers (Run Decision, Copy Txn/Trace ID, Simulate Error).

---

## 🛠️ Technology Stack

- **Framework**: React 19 + TypeScript
- **Styling**: Tailwind CSS v4 with dark fintech palette (`#080A0D` base, `#E8A33D` amber accent)
- **Typography**: Inter + JetBrains Mono (monospaced tabular currency & trace codes)
- **Icons**: Lucide React
- **Animations**: CSS transitions + requestAnimationFrame easing for smooth count-ups

---

## 🚀 Local Development

```bash
# Install dependencies
npm install

# Start development server on port 3000
npm run dev

# Build for production
npm run build
```
