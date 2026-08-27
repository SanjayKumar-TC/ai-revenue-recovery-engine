function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (Array.isArray(value)) {
    return JSON.stringify(value);
  }
  return String(value);
}

function sortNewestFirst(records) {
  return [...records].sort((a, b) => {
    const ta = Date.parse(a.timestamp) || 0;
    const tb = Date.parse(b.timestamp) || 0;
    return tb - ta;
  });
}

const AUDIT_FIELDS = [
  "trace_id",
  "timestamp",
  "transaction_id",
  "selected_action",
  "decision_type",
  "decision_reason",
  "policy_version",
  "model_version",
  "decision_engine_version",
  "rules_fired",
  "escalation_required",
  "terminal",
  "selected_ev",
  "selected_probability",
  "m6_sendable",
  "m6_channel",
  "m6_fallback_used",
];

export default function AuditResult({ lookup }) {
  if (!lookup) {
    return (
      <div className="result-placeholder" data-testid="audit-result-empty">
        Look up a transaction_id to view M7 audit records.
      </div>
    );
  }

  if (lookup.kind === "loading") {
    return (
      <div className="status-banner status-banner--loading" data-testid="audit-loading">
        Loading audit records…
      </div>
    );
  }

  if (lookup.kind === "empty") {
    return (
      <div className="empty-state" data-testid="audit-404">
        No audit records found for transaction_id {lookup.transactionId}.
      </div>
    );
  }

  if (lookup.kind === "http-500") {
    return (
      <div className="status-banner status-banner--500" data-testid="audit-500">
        Server error. Audit lookup could not be completed.
      </div>
    );
  }

  const records = sortNewestFirst(lookup.body?.records || []);

  return (
    <div className="audit-list" data-testid="audit-success">
      <p className="hint">
        transaction_id {lookup.body?.transaction_id || lookup.transactionId} — {records.length}{" "}
        record{records.length === 1 ? "" : "s"} (newest first)
      </p>
      {records.map((record) => (
        <article
          className="result-card"
          key={record.trace_id || record.timestamp}
          data-testid="audit-record"
        >
          <dl className="kv">
            {AUDIT_FIELDS.map((field) => (
              <div key={field}>
                <dt>{field}</dt>
                <dd>{displayValue(record[field])}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </div>
  );
}
