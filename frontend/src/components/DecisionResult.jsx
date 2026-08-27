function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

export default function DecisionResult({ result }) {
  if (!result) {
    return (
      <div className="result-placeholder" data-testid="decide-result-empty">
        Submit a transaction to see the pipeline result.
      </div>
    );
  }

  if (result.kind === "loading") {
    return (
      <div className="status-banner status-banner--loading" data-testid="decide-loading">
        Requesting decision from M8…
      </div>
    );
  }

  if (result.kind === "http-422") {
    return (
      <div className="status-banner status-banner--422" data-testid="decide-422">
        Malformed request (422). The body did not match the locked contract.
      </div>
    );
  }

  if (result.kind === "http-400") {
    return (
      <div className="status-banner status-banner--400" data-testid="decide-400">
        Unknown failure_type (400).
      </div>
    );
  }

  if (result.kind === "http-500") {
    return (
      <div className="status-banner status-banner--500" data-testid="decide-500">
        Server error. The decision could not be returned.
      </div>
    );
  }

  const body = result.body || {};
  const communication = body.communication || {};

  return (
    <div className="result-split" data-testid="decide-success">
      <div className="result-card">
        <h3>Decision</h3>
        <dl className="kv">
          <div>
            <dt>transaction_id</dt>
            <dd>{displayValue(body.transaction_id)}</dd>
          </div>
          <div>
            <dt>trace_id</dt>
            <dd>{displayValue(body.trace_id)}</dd>
          </div>
          <div>
            <dt>selected_action</dt>
            <dd>{displayValue(body.selected_action)}</dd>
          </div>
          <div>
            <dt>decision_type</dt>
            <dd>{displayValue(body.decision_type)}</dd>
          </div>
          <div>
            <dt>decision_reason</dt>
            <dd>{displayValue(body.decision_reason)}</dd>
          </div>
          <div>
            <dt>escalation_required</dt>
            <dd>{displayValue(body.escalation_required)}</dd>
          </div>
          <div>
            <dt>terminal</dt>
            <dd>{displayValue(body.terminal)}</dd>
          </div>
          <div>
            <dt>selected_ev</dt>
            <dd>{displayValue(body.selected_ev)}</dd>
          </div>
          <div>
            <dt>selected_probability</dt>
            <dd>{displayValue(body.selected_probability)}</dd>
          </div>
          <div>
            <dt>policy_version</dt>
            <dd>{displayValue(body.policy_version)}</dd>
          </div>
        </dl>
      </div>
      <div className="result-card result-card--comm">
        <h3>Communication</h3>
        <dl className="kv">
          <div>
            <dt>sendable</dt>
            <dd>{displayValue(communication.sendable)}</dd>
          </div>
          <div>
            <dt>channel</dt>
            <dd>{displayValue(communication.channel)}</dd>
          </div>
          <div>
            <dt>fallback_used</dt>
            <dd>{displayValue(communication.fallback_used)}</dd>
          </div>
        </dl>
        <p className="message-label">message_body</p>
        <pre className="message-body">{displayValue(communication.message_body)}</pre>
      </div>
    </div>
  );
}
