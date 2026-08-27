export function jsonResponse(status, body) {
  const text =
    body === undefined || body === null ? "" : JSON.stringify(body);
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    text: async () => text,
  });
}

export const ALLOWED_DECIDE_INPUT_NAMES = [
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

export const FORBIDDEN_SETTABLE_NAMES = [
  "action",
  "selected_action",
  "selected_ev",
  "selected_probability",
  "ev",
  "probability",
  "rules_fired",
  "policy_version",
  "model_version",
  "decision_engine_version",
  "allowed_actions",
  "blocked_actions",
  "latent_score",
  "true_prob_HIDDEN",
];

export function controlNames(container) {
  return [...container.querySelectorAll("input, select, textarea")]
    .map((el) => el.name)
    .filter(Boolean);
}

export function fillDecideForm(fireEvent, screen) {
  const form = screen.getByTestId("decide-form");
  const named = (name) => form.querySelector(`[name="${name}"]`);
  fireEvent.change(named("transaction_id"), {
    target: { value: "txn_m9_test" },
  });
  fireEvent.change(named("customer_name"), {
    target: { value: "Test User" },
  });
  fireEvent.change(named("payment_link_url"), {
    target: { value: "https://checkout.example.com/pay/txn_m9_test" },
  });
  fireEvent.change(named("communication_channel"), {
    target: { value: "email" },
  });
}
