import { useState } from "react";
import { postDecide } from "../api/client.js";

const INITIAL_FORM = {
  transaction_id: "",
  failure_type: "temporary_bank_decline",
  amount: "2000",
  attempt_number: "1",
  risk_score: "0.15",
  contact_fatigue: "0.1",
  hours_since_failure: "6",
  current_discount_percent: "10",
  customer_segment: "b2c_new",
  already_recovered: false,
  customer_name: "",
  communication_channel: "",
  payment_link_url: "",
};

const REQUEST_FIELDS = [
  "transaction_id",
  "failure_type",
  "amount",
  "attempt_number",
  "risk_score",
  "contact_fatigue",
  "hours_since_failure",
  "current_discount_percent",
  "customer_segment",
  "already_recovered",
  "customer_name",
  "communication_channel",
  "payment_link_url",
];

function buildPayload(form) {
  const payload = {
    transaction_id: form.transaction_id.trim(),
    failure_type: form.failure_type.trim(),
    amount: Number(form.amount),
    attempt_number: Number.parseInt(form.attempt_number, 10),
    risk_score: Number(form.risk_score),
    contact_fatigue: Number(form.contact_fatigue),
    hours_since_failure: Number(form.hours_since_failure),
    current_discount_percent: Number(form.current_discount_percent),
    customer_segment: form.customer_segment,
    already_recovered: Boolean(form.already_recovered),
  };

  const name = form.customer_name.trim();
  if (name) {
    payload.customer_name = name;
  }

  if (form.communication_channel) {
    payload.communication_channel = form.communication_channel;
  }

  const link = form.payment_link_url.trim();
  if (link) {
    payload.payment_link_url = link;
  }

  return payload;
}

export default function DecideForm({ onOutcome, onSuccess }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const payload = buildPayload(form);
    setSubmitting(true);
    onOutcome({ kind: "loading" });
    try {
      const result = await postDecide(payload);
      if (result.status === 200 && result.ok) {
        onSuccess?.(payload, result.data);
        onOutcome({ kind: "success", status: 200, body: result.data });
      } else if (result.status === 422) {
        onOutcome({ kind: "http-422", status: 422 });
      } else if (result.status === 400) {
        onOutcome({ kind: "http-400", status: 400 });
      } else {
        onOutcome({ kind: "http-500", status: result.status || 500 });
      }
    } catch {
      onOutcome({ kind: "http-500", status: 0 });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={handleSubmit} data-testid="decide-form">
      <div className="field-grid">
        <label>
          Transaction ID
          <input
            name="transaction_id"
            required
            value={form.transaction_id}
            onChange={(e) => update("transaction_id", e.target.value)}
          />
        </label>
        <label>
          Failure type
          <input
            name="failure_type"
            required
            list="failure-type-options"
            value={form.failure_type}
            onChange={(e) => update("failure_type", e.target.value)}
          />
          <datalist id="failure-type-options">
            <option value="temporary_bank_decline" />
            <option value="network_timeout" />
            <option value="card_expired" />
            <option value="risk_block" />
            <option value="customer_abandoned" />
            <option value="subscription_mandate_fail" />
            <option value="insufficient_funds" />
          </datalist>
        </label>
        <label>
          Amount
          <input
            name="amount"
            type="number"
            required
            step="any"
            value={form.amount}
            onChange={(e) => update("amount", e.target.value)}
          />
        </label>
        <label>
          Attempt number
          <input
            name="attempt_number"
            type="number"
            required
            step="1"
            min="1"
            value={form.attempt_number}
            onChange={(e) => update("attempt_number", e.target.value)}
          />
        </label>
        <label>
          Risk score
          <input
            name="risk_score"
            type="number"
            required
            step="any"
            min="0"
            max="1"
            value={form.risk_score}
            onChange={(e) => update("risk_score", e.target.value)}
          />
        </label>
        <label>
          Contact fatigue
          <input
            name="contact_fatigue"
            type="number"
            required
            step="any"
            min="0"
            max="1"
            value={form.contact_fatigue}
            onChange={(e) => update("contact_fatigue", e.target.value)}
          />
        </label>
        <label>
          Hours since failure
          <input
            name="hours_since_failure"
            type="number"
            required
            step="any"
            min="0"
            value={form.hours_since_failure}
            onChange={(e) => update("hours_since_failure", e.target.value)}
          />
        </label>
        <label>
          Current discount percent
          <input
            name="current_discount_percent"
            type="number"
            required
            step="any"
            value={form.current_discount_percent}
            onChange={(e) => update("current_discount_percent", e.target.value)}
          />
        </label>
        <label>
          Customer segment
          <select
            name="customer_segment"
            required
            value={form.customer_segment}
            onChange={(e) => update("customer_segment", e.target.value)}
          >
            <option value="b2c_new">b2c_new</option>
            <option value="b2c_returning">b2c_returning</option>
            <option value="b2b">b2b</option>
          </select>
        </label>
        <label className="checkbox-row">
          <input
            name="already_recovered"
            type="checkbox"
            checked={form.already_recovered}
            onChange={(e) => update("already_recovered", e.target.checked)}
          />
          Already recovered
        </label>
        <label>
          Customer name (optional)
          <input
            name="customer_name"
            value={form.customer_name}
            onChange={(e) => update("customer_name", e.target.value)}
          />
        </label>
        <label>
          Communication channel (optional)
          <select
            name="communication_channel"
            value={form.communication_channel}
            onChange={(e) => update("communication_channel", e.target.value)}
          >
            <option value="">(omit)</option>
            <option value="email">email</option>
            <option value="sms">sms</option>
            <option value="whatsapp">whatsapp</option>
            <option value="none">none</option>
          </select>
        </label>
        <label className="full-width">
          Payment link URL (optional)
          <input
            name="payment_link_url"
            value={form.payment_link_url}
            onChange={(e) => update("payment_link_url", e.target.value)}
          />
        </label>
      </div>

      <button type="submit" className="primary-button" disabled={submitting}>
        {submitting ? "Submitting…" : "Submit decision request"}
      </button>
      <p className="hint">Sends only the locked POST /decide fields. No action is chosen here.</p>
      <span data-testid="decide-field-names" hidden>
        {REQUEST_FIELDS.join(",")}
      </span>
    </form>
  );
}
