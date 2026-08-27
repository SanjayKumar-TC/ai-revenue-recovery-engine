import { useState } from "react";
import HealthIndicator from "./components/HealthIndicator.jsx";
import DecideForm from "./components/DecideForm.jsx";
import DecisionResult from "./components/DecisionResult.jsx";
import AuditLookup from "./components/AuditLookup.jsx";
import AuditResult from "./components/AuditResult.jsx";

export default function App() {
  const [decideResult, setDecideResult] = useState(null);
  const [auditPrefill, setAuditPrefill] = useState("");
  const [auditLookup, setAuditLookup] = useState(null);

  function handleDecideSuccess(payload, responseBody) {
    setDecideResult({ kind: "success", status: 200, body: responseBody });
    setAuditPrefill(payload.transaction_id);
  }

  function handleDecideOutcome(outcome) {
    setDecideResult(outcome);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">M9 operator console</p>
          <h1>Revenue Recovery Engine</h1>
          <p className="lede">
            Decisions are made only by the M8 pipeline. This dashboard submits
            context and displays the returned result.
          </p>
        </div>
        <HealthIndicator />
      </header>

      <main className="layout">
        <section className="panel" aria-labelledby="decide-heading">
          <h2 id="decide-heading">Decide</h2>
          <DecideForm
            onOutcome={handleDecideOutcome}
            onSuccess={handleDecideSuccess}
          />
          <DecisionResult result={decideResult} />
        </section>

        <section className="panel" aria-labelledby="audit-heading">
          <h2 id="audit-heading">Audit lookup</h2>
          <AuditLookup
            prefillTransactionId={auditPrefill}
            onLookup={setAuditLookup}
          />
          <AuditResult lookup={auditLookup} />
        </section>
      </main>
    </div>
  );
}
