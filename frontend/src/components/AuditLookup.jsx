import { useEffect, useState } from "react";
import { getAudit } from "../api/client.js";

export default function AuditLookup({ prefillTransactionId = "", onLookup }) {
  const [transactionId, setTransactionId] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (prefillTransactionId) {
      setTransactionId(prefillTransactionId);
    }
  }, [prefillTransactionId]);

  async function handleSubmit(event) {
    event.preventDefault();
    const id = transactionId.trim();
    if (!id) {
      return;
    }
    setLoading(true);
    onLookup({ kind: "loading" });
    try {
      const result = await getAudit(id);
      if (result.status === 404) {
        onLookup({ kind: "empty", status: 404, transactionId: id });
      } else if (result.ok && result.status === 200) {
        onLookup({
          kind: "success",
          status: 200,
          transactionId: id,
          body: result.data,
        });
      } else {
        onLookup({ kind: "http-500", status: result.status || 500 });
      }
    } catch {
      onLookup({ kind: "http-500", status: 0 });
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="audit-form" onSubmit={handleSubmit} data-testid="audit-form">
      <label>
        Transaction ID
        <input
          name="audit_transaction_id"
          value={transactionId}
          onChange={(e) => setTransactionId(e.target.value)}
          required
        />
      </label>
      <button type="submit" className="primary-button" disabled={loading}>
        {loading ? "Looking up…" : "Look up audit records"}
      </button>
    </form>
  );
}
